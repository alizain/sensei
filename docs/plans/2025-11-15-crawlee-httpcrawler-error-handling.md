# Crawlee HttpCrawler Error Handling Deep Dive

> **Source Analysis**: Based on crawlee source code in `.venv/lib/python3.13/site-packages/crawlee/`

## Class Hierarchy

```
BasicCrawler
    └── AbstractHttpCrawler
            └── HttpCrawler
```

- **`BasicCrawler`** (`crawlers/_basic/_basic_crawler.py`): Core crawler with all retry logic, error handling, session management
- **`AbstractHttpCrawler`** (`crawlers/_abstract_http/_abstract_http_crawler.py`): Adds HTTP-specific pipeline (make request → check status → parse response → check blocked)
- **`HttpCrawler`** (`crawlers/_http/_http_crawler.py`): Thin wrapper that uses a `NoParser` (returns raw bytes)

## The Context Pipeline

The pipeline is a chain of async generator middlewares that build up the crawling context:

```python
# AbstractHttpCrawler._create_static_content_crawler_pipeline()
ContextPipeline()
    .compose(self._execute_pre_navigation_hooks)
    .compose(self._make_http_request)           # Can raise SessionError, httpx errors
    .compose(self._handle_status_code_response) # Can raise SessionError, HttpStatusCodeError, HttpClientStatusCodeError
    .compose(self._parse_http_response)
    .compose(self._handle_blocked_request_by_content) # Can raise SessionError
```

The pipeline wraps exceptions that occur:
- **During middleware initialization**: `ContextPipelineInitializationError(wrapped_exception, context)`
- **In the final consumer (your request handler)**: `RequestHandlerError(wrapped_exception, context)`
- **`SessionError`**: Passes through unwrapped (special treatment)
- **`ContextPipelineInterruptedError`**: Passes through unwrapped (signals skip)

## Exception Types and Their Behaviors

### 1. `SessionError` (includes `ProxyError`)

**Source**: `errors.py:33-37`

```python
class SessionError(Exception):
    """Errors of `SessionError` type will trigger a session rotation.

    This error doesn't respect the `max_request_retries` option and has a
    separate limit of `max_session_rotations`.
    """
```

**Behavior**:
- Triggers **session rotation** (not a normal retry)
- Uses separate counter: `max_session_rotations` (default: 10)
- Does NOT count against `max_request_retries`
- Session is retired (marked bad, new session will be used)
- If rotations exhausted → `failed_request_handler` called

**Where raised**:
- `_handle_status_code_response()`: When status code indicates blocked session
- `_handle_blocked_request_by_content()`: When parser detects blocked content
- Your handlers can raise it to force session rotation

### 2. `HttpStatusCodeError`

**Source**: `errors.py:57-63`

```python
class HttpStatusCodeError(Exception):
    """Raised when the response status code indicates an error."""
```

**Behavior**:
- **Server errors (5xx)** or **user-configured error codes**: Retries up to `max_request_retries`
- Goes through normal retry flow → `error_handler` → retry or fail

### 3. `HttpClientStatusCodeError` (subclass of `HttpStatusCodeError`)

**Source**: `errors.py:67-68`

```python
class HttpClientStatusCodeError(HttpStatusCodeError):
    """Raised when the response status code indicates an client error."""
```

**Behavior**:
- **Client errors (4xx)**: **NO RETRY**
- Goes directly to `failed_request_handler`
- Rationale: 4xx errors are client's fault, retrying won't help

**Critical code** (`_should_retry_request`, line 903-918):
```python
def _should_retry_request(self, context: BasicCrawlingContext, error: Exception) -> bool:
    if context.request.no_retry:
        return False
    # Do not retry on client errors.
    if isinstance(error, HttpClientStatusCodeError):
        return False
    if isinstance(error, SessionError):
        return ((context.request.session_rotation_count or 0) + 1) < self._max_session_rotations
    # ... check max_request_retries
```

### 4. `ContextPipelineInterruptedError`

**Source**: `errors.py:108-109`

```python
class ContextPipelineInterruptedError(Exception):
    """May be thrown in the initialization phase of a middleware to signal
    that the request should not be processed."""
```

**Behavior**:
- Request is marked as handled (removed from queue)
- **NO retry, NO `failed_request_handler`**
- Used for legitimate "skip this request" scenarios (e.g., redirect outside allowed domain)
- Just logs at debug level and moves on

### 5. `ContextPipelineInitializationError`

**Source**: `errors.py:82-92`

Wraps exceptions from middleware initialization (before your handler runs).

**Behavior**:
- Goes through normal retry flow via `_handle_request_error()`
- Extracts the `wrapped_exception` for retry logic

### 6. `RequestHandlerError`

**Source**: `errors.py:72-78`

Wraps exceptions from your request handler.

**Behavior**:
- Goes through normal retry flow via `_handle_request_error()`
- Extracts `wrapped_exception` and `crawling_context`

### 7. `UserDefinedErrorHandlerError`

**Source**: `errors.py:28-29`

```python
class UserDefinedErrorHandlerError(Exception):
    """Wraps an exception thrown from an user-defined error handler."""
```

**Behavior**:
- If your `error_handler` or `failed_request_handler` raises an exception
- Sets request state to `ERROR`
- Re-raises (propagates up) - can terminate crawling

## The Main Error Handling Flow

**Location**: `BasicCrawler.__run_task_function()` (lines 1349-1491)

```python
try:
    # Run the context pipeline and your handler
    await self._run_request_handler(context=context)

    # Success path: commit results, mark handled
    await self._commit_request_handler_result(context)
    await request_manager.mark_request_as_handled(context.request)

except RequestCollisionError:
    # Session bound to request is no longer available
    context.request.no_retry = True  # Force no retry
    await self._handle_request_error(context, error)

except RequestHandlerError as primary_error:
    # Exception from your handler - normal retry flow
    await self._handle_request_error(
        primary_error.crawling_context,
        primary_error.wrapped_exception
    )

except SessionError as session_error:
    # Session rotation path (separate from normal retries)
    if self._error_handler:
        await self._error_handler(context, session_error)

    if self._should_retry_request(context, session_error):
        context.session.retire()
        context.request.session_rotation_count += 1
        await request_manager.reclaim_request(request)
    else:
        await request_manager.mark_request_as_handled(context.request)
        await self._handle_failed_request(context, session_error)

except ContextPipelineInterruptedError:
    # Skip this request - no retry, no failure
    await request_manager.mark_request_as_handled(context.request)

except ContextPipelineInitializationError:
    # Error during pipeline setup - retry via normal flow
    await self._handle_request_error(context, error.wrapped_exception)
```

## `_handle_request_retries()` - The Retry Decision Point

**Location**: Lines 1089-1130

```python
async def _handle_request_retries(self, context, error):
    if self._abort_on_error:
        self._failed = True  # Will terminate crawling

    if self._should_retry_request(context, error):
        # WILL RETRY
        request.retry_count += 1
        await self._statistics.error_tracker.add(error=error, context=context)

        if self._error_handler:
            try:
                new_request = await self._error_handler(context, error)
            except Exception as e:
                raise UserDefinedErrorHandlerError(...) from e
            else:
                if new_request is not None:
                    request = new_request  # Use modified request for retry

        await request_manager.reclaim_request(request)  # Put back in queue
    else:
        # EXHAUSTED RETRIES - will not retry
        await request_manager.mark_request_as_handled(context.request)
        await self._handle_failed_request(context, error)
        self._statistics.record_request_processing_failure(request.unique_key)
```

## `error_handler` Callback

**Signature**:
```python
ErrorHandler = Callable[[TCrawlingContext, Exception], Awaitable[Request | None]]
```

**When called**:
- BEFORE a retry attempt (not after final failure)
- For both normal errors AND session errors

**Return values**:
- `None`: Use the original request for retry (default)
- `Request`: Use this modified request instead for retry

**What you can do**:
1. **Return `None`**: Normal retry with original request
2. **Return a new `Request`**: Retry with modified request (e.g., different URL, headers)
3. **Raise an exception**: Wrapped in `UserDefinedErrorHandlerError`, terminates

**Example use cases**:
- Log the error for debugging
- Modify request headers before retry
- Store error info in request's `user_data`

## `failed_request_handler` Callback

**Signature**:
```python
FailedRequestHandler = Callable[[TCrawlingContext, Exception], Awaitable[None]]
```

**When called**:
- AFTER all retries exhausted
- Request will NOT be retried after this

**What you can do**:
1. **Return normally**: Error is logged, crawling continues
2. **Raise an exception**: Wrapped in `UserDefinedErrorHandlerError`, terminates

**Example use cases**:
- Record the failure in a dataset
- Send notification about failed URL
- Clean up resources

## Complete Error Handling Decision Tree

```
Exception occurs
│
├─► SessionError?
│   ├─► error_handler() called (if defined)
│   ├─► session_rotation_count < max_session_rotations?
│   │   ├─► YES: Retire session, reclaim request (will retry with new session)
│   │   └─► NO: Mark handled, failed_request_handler(), continue crawling
│   └─► (Session is marked bad either way)
│
├─► HttpClientStatusCodeError (4xx)?
│   └─► NO RETRY → Mark handled, failed_request_handler(), continue crawling
│
├─► ContextPipelineInterruptedError?
│   └─► Mark handled, NO failed_request_handler, continue crawling
│
├─► RequestCollisionError?
│   └─► Set no_retry=True, go through normal error flow (will fail immediately)
│
├─► Other errors (HttpStatusCodeError, RequestHandlerError, etc.)?
│   ├─► retry_count < max_request_retries AND not no_retry?
│   │   ├─► YES:
│   │   │   ├─► Increment retry_count
│   │   │   ├─► error_handler() called (if defined)
│   │   │   │   ├─► Returns Request? Use it for retry
│   │   │   │   ├─► Returns None? Use original request
│   │   │   │   └─► Raises? UserDefinedErrorHandlerError, TERMINATES
│   │   │   └─► Reclaim request (will retry)
│   │   └─► NO: Mark handled, failed_request_handler(), continue crawling
```

## Key Behavioral Insights for Your Code

### Scenario 1: Error should retry, but failure should be recorded

```python
@crawler.error_handler
async def handle_error(context, error):
    # Called before each retry
    logger.warning(f"Retry {context.request.retry_count + 1} for {context.request.url}")
    return None  # Use original request

@crawler.failed_request_handler
async def handle_failure(context, error):
    # Called after all retries exhausted
    await record_failure(context.request.url, str(error))
    # Return normally - crawling continues
```

### Scenario 2: Error should NOT retry and should stop crawling

```python
# Option A: Use abort_on_error=True in crawler config
crawler = HttpCrawler(abort_on_error=True)

# Option B: Raise from failed_request_handler
@crawler.failed_request_handler
async def handle_failure(context, error):
    if is_critical_error(error):
        raise RuntimeError("Critical error, stopping crawl") from error
```

### Scenario 3: Error should NOT retry but continue crawling

```python
# Option A: Set no_retry on the request
request = Request.from_url(url, no_retry=True)

# Option B: Raise ContextPipelineInterruptedError (skips without failure)
# (This is for middleware-level skipping)

# Option C: Just let it fail naturally - 4xx errors don't retry automatically
```

### Scenario 4: Force session rotation on specific errors

```python
@crawler.router.default_handler
async def handler(context):
    if "captcha" in response.text:
        raise SessionError("Captcha detected, need new session")
```

## Configuration Options Summary

| Option | Default | Effect |
|--------|---------|--------|
| `max_request_retries` | 3 | Max retry attempts per request |
| `max_session_rotations` | 10 | Max session changes per request (for `SessionError`) |
| `abort_on_error` | False | Stop crawling on first error |
| `request.no_retry` | False | Skip retries for this specific request |
| `request.max_retries` | None | Per-request retry limit (overrides global) |
| `additional_http_error_status_codes` | [] | Extra status codes to treat as errors (trigger retry) |
| `ignore_http_error_status_codes` | [] | Status codes to NOT treat as errors |

## Handler Behavior Summary Table

| Action in Handler | Effect |
|-------------------|--------|
| **error_handler returns None** | Retry with original request |
| **error_handler returns Request** | Retry with modified request |
| **error_handler raises** | `UserDefinedErrorHandlerError` → state=ERROR, propagates |
| **failed_request_handler returns** | Failure recorded, crawling continues |
| **failed_request_handler raises** | `UserDefinedErrorHandlerError` → state=ERROR, propagates |
| **Neither defined** | Default behavior: retry → log failure → continue |

## Important: SessionError Special Path

`SessionError` has a **completely separate code path** from other errors:

```python
except SessionError as session_error:
    if not context.session:
        raise RuntimeError(...)

    if self._error_handler:
        await self._error_handler(context, session_error)  # Note: ALWAYS called

    if self._should_retry_request(context, session_error):
        context.session.retire()
        context.request.session_rotation_count = (count or 0) + 1
        await request_manager.reclaim_request(request)
        await self._statistics.error_tracker_retry.add(...)
    else:
        await request_manager.mark_request_as_handled(...)
        await self._handle_failed_request(context, session_error)
```

Key differences:
1. Uses `session_rotation_count` instead of `retry_count`
2. Retires the session (marks it bad)
3. Tracked in separate `error_tracker_retry` stats
4. `error_handler` is ALWAYS called (but can't modify the retry decision here)
