---
description: Query sensei for accurate documentation and guidance
argument-hint: [question about a library, API, or pattern]
---

Use the sensei MCP server's `query` tool to answer this documentation question:

**Query:** $ARGUMENTS

Call the `query` tool from `sensei` with the query parameter set to the user's question. If the question mentions a specific programming language, library, or version, extract those and pass them as the optional `language`, `library`, and `version` parameters.

Present the sensei response directly to the user. Include the query_id from the response so they can provide feedback later if needed.
