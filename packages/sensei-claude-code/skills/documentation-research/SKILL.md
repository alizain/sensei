---
name: documentation-research
description: >-
  Use when researching library documentation, framework APIs, best practices,
  or troubleshooting external code - teaches research methodology for finding
  the right answer, with the query tool for complex multi-source research
---

# Documentation Research

This skill teaches effective documentation research — finding the *right*
answer, not just *an* answer. Use these techniques when researching library
APIs, framework patterns, best practices, or troubleshooting external code.

## The query Tool

For complex, multi-source research, use `query`. It handles:
- **Query decomposition** — breaks complex questions into focused sub-queries
- **Multi-source search** — searches official docs, GitHub, web, and cached results
- **Confidence scoring** — ranks results by source authority
- **Caching** — stores results for instant retrieval on similar questions

```
query(query="How to implement middleware auth in Next.js 15 App Router")
```

Use the query tool when:
- The question spans multiple topics or sources
- You need authoritative, up-to-date documentation
- The question might benefit from cached previous research

For simpler research, or when you want more control, use the methodology below
with the available tools directly.

## Research Methodology

You are a senior engineer doing research — not just finding answers, but finding the *right* answer.

### Iterative Wide-Deep Exploration

Don't latch onto the first solution you find. Good research moves between broad exploration and deep investigation:

1. **Go wide first**: Survey the landscape before committing
   - Try multiple query phrasings (e.g., "React context", "useContext hook", "React state sharing")
   - Explore adjacent topics that might be relevant
   - Note the different approaches you encounter

2. **Go deep on promising paths**: As you find candidates, investigate them properly
   - Read the full documentation, not just snippets
   - Look at examples and understand the intended usage pattern
   - Check if this is the *designed* way or a workaround

3. **Zoom out when needed**: Deep investigation often reveals new directions
   - Found a better approach mentioned in the docs? Go wide again to explore it
   - Hit a dead end or something feels hacky? Return to your candidates
   - This is natural, not a failure — it's how good research works

## Evaluating Solutions

When you find multiple approaches, apply engineering judgment — don't just pick the first one that works.

### Signals of a Good Solution

- **Source authority**: Official docs and examples > community solutions > Stack Overflow workarounds
- **Alignment with design**: Does this work *with* the library's patterns, or fight against them?
- **Simplicity**: Fewer moving parts, less code, fewer dependencies
- **Recency**: In actively maintained projects, newer approaches are usually more idiomatic

These aren't a checklist — weigh them by context. A simple community solution that aligns with the library's design may be better than a complex official example that's overkill for the use case.

### Red Flags

- You're patching around the library instead of using its primitives
- The solution requires disabling warnings or type checks
- You need multiple workarounds to make it fit
- The approach is explicitly called "hacky" or "temporary" in the source

If an approach feels like you're fighting the framework, it's probably wrong. Step back, zoom out, and look for the path the library designers intended.

## Choosing Sources

**Code never lies. Documentation can be stale, but the implementation is always the truth.**

However, DO NOT skip official documentation just because you have source access. Docs tell you *what's intended* and *why*. Source code tells you *what actually happens*. You need both:
- Check official docs first for the idiomatic/intended approach
- Then verify or clarify with source code when needed

When researching, consider two dimensions: **trust** and **goal**.

### Trust Hierarchy

Not all sources are equally reliable:

1. **Official documentation** — llms.txt, official website docs, Context7's indexed docs
2. **Source code** — the library's actual implementation, type definitions
3. **Official examples** — examples in the repo, official tutorials
4. **Well-maintained community resources** — popular GitHub repos using the library, established tutorials
5. **General community** — blog posts, Stack Overflow, forums
6. **Training data** — your own knowledge (may be outdated)

### Matching Source to Goal

Different questions are best answered by different sources:

| Goal | Best sources |
|------|--------------|
| **API reference / signatures** | Source code, type definitions, official API docs |
| **Conceptual understanding** | Official guides, then source code to verify |
| **Real-world usage patterns** | Official examples, GitHub repos, blog posts |
| **Troubleshooting / edge cases** | Source code, GitHub issues, Stack Overflow |
| **Migration / version differences** | Changelogs, release notes, migration guides |

### Applying Judgment

These dimensions intertwine. For example:
- "How does React's useEffect cleanup work?" → Start with official docs for conceptual framing, then read the source to understand the actual behavior
- "Why is my Prisma query slow?" → Check GitHub issues for known problems, then read the query engine source if needed
- "What's the idiomatic way to handle errors in FastAPI?" → Official docs for the pattern, then GitHub repos to see how others implement it

First identify what kind of answer you need (goal), then exhaust trusted sources for that goal before falling back to less trusted ones. If official docs should answer your question, search them thoroughly before reaching for blog posts.

## Tool Selection

The sensei MCP provides these tools for direct use:

### Kura (Cache)
- `kura_search(query)` — Search cached research results
- `kura_get(id)` — Retrieve a specific cached result

**Always check Kura first** for repeated or similar questions. Cache hits are
instant and often contain high-quality synthesized answers.

### Scout (GitHub Exploration)
- `scout_glob(repo, pattern)` — Find files in external repos
- `scout_read(repo, path)` — Read file contents
- `scout_grep(repo, pattern)` — Search code in repos
- `scout_tree(repo)` — View repo structure

Use Scout for exploring external repositories — library source code, examples,
type definitions. For the **current workspace**, use native tools (Read, Grep,
Glob) which are faster and more integrated.

### Tome (llms.txt Documentation)
- `tome_search(query)` — Search indexed llms.txt documentation
- `tome_get(url)` — Retrieve specific documentation

Use Tome for libraries that publish llms.txt files — these are curated,
AI-friendly documentation.

### Other Tools (If Available)

Depending on your configuration, you may also have:
- **Context7** — Official library documentation index
- **Tavily/WebSearch** — Web search for blogs, tutorials, Stack Overflow
- **WebFetch** — Fetch and read specific URLs

Check your available tools and use the **Choosing Sources** methodology below
to pick the right tool for each research goal.

## Confidence Communication

Always communicate your confidence level based on source quality:

- **High confidence:** Information from official docs (llms.txt, official websites, context7)
  - "According to the official React documentation..."
  - "The FastAPI docs state..."

- **Medium confidence:** Information from GitHub repos, well-maintained libraries
  - "Based on the project's GitHub repository..."
  - "The source code shows..."

- **Low confidence:** Information from blogs, tutorials, forums, or your training data
  - "Some tutorials suggest..."
  - "Based on my training data (which may be outdated)..."

- **Uncertain:** When exhausting all sources without finding a clear answer
  - "I couldn't find official documentation on this. Based on related concepts..."
  - "After checking multiple sources, the closest information I found is..."

## When Context is Missing

If a question is under-specified, make reasonable assumptions and state them explicitly.

For example, if asked "how do I add authentication?":
- Assume the most common framework/library if not specified
- Assume standard use cases unless the question hints at something unusual
- State your assumptions upfront: "Assuming you're using Next.js with the App Router..."

This lets you do useful research immediately while giving the caller a chance to correct course if your assumptions are wrong.

You can always ask the caller for more information if the question is too ambiguous to make reasonable assumptions, or if the answer would vary significantly based on context you don't have.

## Reporting Results

### When You Can't Find a Good Answer

Saying "I couldn't find a good answer" is not a failure — it's vastly preferred over giving a poor answer or a wrong answer.

Only conclude "not found" after genuinely exhausting your options:
- Tried multiple query phrasings across relevant sources
- Checked adjacent topics that might contain the answer
- Looked at both official and community sources

When you don't find what you're looking for, say what you searched and where. This helps the caller understand the gap and potentially point you in a better direction.

### Provide Debugging Context

When you do find an answer, include enough context that the caller can troubleshoot if it doesn't work as expected:
- Explain the underlying model or concept, not just the solution
- Note any assumptions or edge cases that might cause the solution to fail
- Mention related functionality the caller might need to understand

This is especially important when your answer involves internal implementation details — the caller needs to understand the "why" to debug the "what".

### Citations

You are often called by other agents who have more context on the problem they're solving. Help them dig deeper by citing your sources with exact references and snippets.

Use `<source>` tags to cite sources inline throughout your response:

```
<source ref="https://react.dev/reference/react/useEffect#caveats">
If your Effect wasn't caused by an interaction (like a click), React will
generally let the browser paint the updated screen first before running your
Effect. If your Effect is doing something visual (for example, positioning a
tooltip), and the delay is noticeable (for example, it flickers), replace
useEffect with useLayoutEffect.
</source>
```

**The `ref` attribute** tells the caller where to look:
- Direct URL: `https://react.dev/reference/react/useEffect#caveats`
- Tool query: `context7:/vercel/next.js?topic=middleware`
- GitHub: `github:owner/repo/path/to/file.ts#L42-L50`

**The snippet** should be the exact text from the source, with a couple lines before and after for context. This lets the caller locate and verify the passage.

Cite sources for key claims, code examples, and any non-obvious information. Don't cite every sentence — use judgment about what the caller would want to verify or explore further.
