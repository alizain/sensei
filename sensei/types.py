"""Type definitions for Sensei.

This module contains:
- Exception hierarchy for structured error handling
- Result types for tool return values
- Domain models shared across layers
- Value objects for normalization
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

import tldextract
from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Exceptions
# =============================================================================


class SenseiError(Exception):
    """Base for all Sensei errors."""

    pass


class BrokenInvariant(SenseiError):
    """Setup/config error - cannot continue (e.g., missing API key)."""

    pass


class TransientError(SenseiError):
    """Temporary failure - retry may succeed (e.g., network timeout)."""

    pass


class ToolError(SenseiError):
    """Tool failed - try a different approach."""

    pass


# =============================================================================
# Crawler Warnings (expected skips, not errors)
# =============================================================================


class ContentTypeWarning(Exception):
    """Document skipped due to wrong content-type (e.g., HTML instead of markdown).

    This is expected behavior - llms.txt files often link to non-markdown pages.
    """

    def __init__(self, url: str, content_type: str | None) -> None:
        self.url = url
        self.content_type = content_type
        super().__init__(f"Wrong content-type '{content_type}': {url}")


# =============================================================================
# Result Types
# =============================================================================

T = TypeVar("T")


@dataclass
class Success(Generic[T]):
    """Tool returned data successfully."""

    data: T


@dataclass
class NoResults:
    """Tool executed successfully but found no results."""

    pass


# =============================================================================
# Value Objects
# =============================================================================


@dataclass(frozen=True, eq=False)
class Domain:
    """Domain value object preserving subdomains, comparing by registrable domain.

    Stores the full hostname (subdomains preserved) but compares using the
    registrable domain (eTLD+1) for "same-site" semantics.

    Examples:
        Domain("fastcore.fast.ai").value -> "fastcore.fast.ai"
        Domain("www.example.com").value -> "www.example.com"
        Domain("fastcore.fast.ai") == Domain("docs.fast.ai") -> True (same site)
        Domain("example.com") == Domain("other.com") -> False
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self._extract_hostname(self.value)
        object.__setattr__(self, "value", normalized)

    @staticmethod
    def _extract_hostname(raw: str) -> str:
        """Extract and lowercase the full hostname (preserving subdomains)."""
        extracted = tldextract.extract(raw)
        # Reconstruct full hostname: subdomain.domain.suffix
        parts = [p for p in [extracted.subdomain, extracted.domain, extracted.suffix] if p]
        if parts:
            return ".".join(parts).lower()
        # Fallback for invalid input
        return raw.lower()

    @property
    def registrable_domain(self) -> str:
        """The registrable domain (eTLD+1) for same-site comparison."""
        extracted = tldextract.extract(self.value)
        registrable = extracted.top_domain_under_public_suffix
        return registrable.lower() if registrable else self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Domain):
            return NotImplemented
        return self.registrable_domain == other.registrable_domain

    def __hash__(self) -> int:
        return hash(self.registrable_domain)

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_url(cls, url: str) -> "Domain":
        """Create Domain from a full URL."""
        return cls(url)


# =============================================================================
# Domain Models
# =============================================================================


class QueryResult(BaseModel):
    """Result of a query operation."""

    query_id: UUID = Field(..., description="Unique identifier for this query")
    markdown: str = Field(..., description="Markdown documentation with code examples")


class Rating(BaseModel):
    """Rating for a query response."""

    query_id: UUID = Field(..., description="The query ID to rate")
    correctness: int = Field(..., ge=1, le=5, description="Is the information/code correct? (1-5)")
    relevance: int = Field(..., ge=1, le=5, description="Did it answer the question? (1-5)")
    usefulness: int = Field(..., ge=1, le=5, description="Did it help solve the problem? (1-5)")
    reasoning: str | None = Field(None, description="Why these ratings? What changed from last time?")
    agent_model: str | None = Field(None, description="Model identifier")
    agent_system: str | None = Field(None, description="Agent system name")
    agent_version: str | None = Field(None, description="Agent system version")


class CacheHit(BaseModel):
    """Cached query with computed age for API responses.

    Mirrors Query model fields plus computed age_days.
    """

    model_config = ConfigDict(from_attributes=True)

    # Query model fields
    id: UUID
    query: str
    language: str | None = None
    library: str | None = None
    version: str | None = None
    output: str
    messages: str | None = None
    parent_id: UUID | None = None
    inserted_at: datetime
    updated_at: datetime

    # Computed field
    age_days: int


class SubSenseiResult(BaseModel):
    """Result from spawning a sub-sensei."""

    query_id: UUID
    response_markdown: str
    from_cache: bool
    age_days: int | None = None


class DocumentContent(BaseModel):
    """Content to save for a crawled document.

    Used by the tome crawler to pass document data to storage layer.
    Keeps the domain model as single source of truth.
    """

    domain: str = Field(..., description="Source domain (e.g., 'llmstext.org')")
    url: str = Field(..., description="Full URL of the document")
    path: str = Field(..., description="Path portion of the URL")
    content: str = Field(..., description="Markdown content")
    content_hash: str = Field(..., description="Hash for change detection")
    depth: int = Field(..., ge=0, description="Crawl depth (0 = llms.txt, 1+ = linked)")


class IngestResult(BaseModel):
    """Result of ingesting a domain's llms.txt documentation.

    Returned by the tome crawler after crawling a domain's llms.txt
    and its linked documents. Uses generation-based crawling where
    all documents are inserted fresh each crawl.

    Error categorization:
    - warnings: Expected skips (wrong content-type, 404 dead links)
    - failures: Unexpected errors (DNS, timeout, 5xx, decode errors)

    Any non-empty failures list = overall crawl failure.
    """

    model_config = {"arbitrary_types_allowed": True}

    domain: str = Field(..., description="The domain that was crawled")
    documents_added: int = Field(default=0, ge=0, description="Number of documents added in this generation")
    warnings: list[Exception] = Field(default_factory=list, description="Expected skips (wrong content-type, 404s)")
    failures: list[Exception] = Field(default_factory=list, description="Unexpected errors (network, 5xx, decode)")


class SearchResult(BaseModel):
    """A full-text search result from section-based search.

    Returned by search_sections_fts() for tome_search functionality.
    """

    url: str = Field(..., description="Full URL of the matching document")
    path: str = Field(..., description="Path portion of the URL")
    snippet: str = Field(..., description="Text snippet with search terms highlighted")
    rank: float = Field(..., description="Relevance score from ts_rank")
    heading_path: str = Field(default="", description="Breadcrumb path like 'API > Hooks > useState'")


@dataclass
class SectionData:
    """Intermediate type for chunking algorithm output.

    Represents a section extracted from markdown content. Used by the chunker
    to return hierarchical sections that will be flattened for storage.
    """

    heading: str | None  # Null for intro/root content before first heading
    level: int  # 0=root, 1=h1, 2=h2, etc.
    content: str  # This section's markdown content
    children: list["SectionData"]  # Child sections for building hierarchy


@dataclass
class TOCEntry:
    """Table of contents entry for tome_toc().

    Represents a heading in the document hierarchy for navigation.
    """

    heading: str
    level: int
    children: list["TOCEntry"]
