# Sensei

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.5.1-green.svg)](https://github.com/803/sensei)

**The documentation agent for coding agents.**

Sensei searches multiple authoritative sources, cross-validates, and synthesizes accurate answers so your AI writes working code on the first try.

[Try it live →](https://sensei.eightzerothree.co)

## Install

### Claude Code

```bash
claude plugin marketplace add 803/sensei
claude plugin install --scope user sensei@sensei-marketplace
```

### Other MCP Clients

**Remote (recommended):**
```
https://api.sensei.eightzerothree.co/mcp
```

**Local:**
```bash
uvx sensei-ai --help
```

### API

```bash
curl -X POST https://api.sensei.eightzerothree.co/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I authenticate with OAuth?",
    "language": "python",
    "library": "fastapi"
  }'
```

## Why Sensei

### 20x more context efficiency

Other tools paste raw docs into your context window—100,000 to 300,000 tokens of unfiltered content. Sensei reads, validates, and synthesizes. You get 2,000-10,000 focused tokens. Your agent's context stays clean for the actual work.

### Optimized research methodology

Sensei researches like a senior engineer. It goes wide first to survey options, then deep on promising paths. It follows a trust hierarchy—official docs → source code → real implementations → community content—and matches sources to goals. Complex questions get decomposed into parts, researched separately, and synthesized into one answer you can trust.

### Continuous improvement

Your agent gives feedback to Sensei. Did the code work? Was the guidance correct? Every outcome is a verified reward signal. We fine-tune the model from real results. Success reinforces what works. Failure refines what doesn't.

## The Tools

Alongside third-party tools like Context7 and Tavily, Sensei includes three purpose-built tools:

**Kura** — Knowledge cache. First query: thorough research across all sources. Every query after: instant. Complex questions get decomposed into parts—and each part gets cached as a reusable building block. Future questions that share parts get faster, more accurate answers.

**Scout** — Source code exploration. Glob, grep, and tree any public repository at any tag, branch, or commit SHA. Local clones created on-demand. When docs are unclear, read what the code actually does.

**Tome** — llms.txt ingestion. llms.txt is the future of AI-readable documentation. Tome ingests on-demand from any domain and saves for future use. Official docs, formatted for agents, always available.

## For Teams

**Bring your own sources.** Internal wikis. Private repos. Proprietary APIs. Connect them via MCP, and Sensei searches them alongside everything else.

**Self-host the full stack.** Sensei runs on your infrastructure. Your queries stay on your network. Complete control when you need it.

**Open source.** Inspect it. Fork it. Trust it.

## Contributing

```bash
uv sync --group dev
uv run pre-commit install
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

MIT

---

Built with [PydanticAI](https://github.com/pydantic/pydantic-ai) and [FastMCP](https://github.com/jlowin/fastmcp)
