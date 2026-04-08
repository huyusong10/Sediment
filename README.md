<div align="center">

<img src="resources/logo.svg" alt="Sediment Logo" width="450"/>

<br/>

**Tacit knowledge extraction system for AI Agents**

*Turns complex unstructured documents into a structured, human-reviewable knowledge base.*

<br/>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

[![GitHub Stars](https://img.shields.io/github/stars/huyusong10/Sediment?style=social)](https://github.com/huyusong10/Sediment/stargazers)

</div>

---

[🇺🇸 English](README.md) | [🇨🇳 中文](README_zh.md)

---

Sediment helps general users and teams capture and organize **tacit knowledge** — the kind that lives in people's heads, scattered documents, and implicit conventions — into a structured, navigable knowledge base that AI Agents can query and contribute to.

Key capabilities:

| Capability | Description |
|---|---|
| **Ingest** | Parse documents and extract atomic knowledge entries via an AI-powered skill |
| **Tidy** | Resolve dangling links, fill placeholders via inductive reasoning, merge duplicates, fix orphan nodes |
| **Explore** | Let AI Agents autonomously discover and synthesize relevant knowledge via MCP tools |
| **Health Check** | Run a full diagnostic report on the knowledge base at any time |

---

> *"I don't think everything on my own, it happens largely in my slip-box."* — Niklas Luhmann, creator of the Zettelkasten method

Sediment embraces the **Zettelkasten (Slip-box)** philosophy and prioritizes a **white-box architecture**:
- **Atomic & Connected**: Each concept exists as a verifiable, single-proposition Markdown file with explicit `[[WikiLinks]]`.
- **Absolute Transparency**: No hidden backend databases and no opaque vector embeddings. The entire knowledge base is just plain text.
- **Obsidian-Ready**: Because it relies on standard folder structures and markdown links, you can directly open your `knowledge-base` folder using tools like **Obsidian**. This allows humans to visually explore graph relationships, read entries, and manually maintain the data right alongside AI Agents.

---

## Table of Contents

- [Architecture](#architecture)
- [Server-side Deployment](#server-side-deployment)
  - [Prerequisites](#prerequisites)
  - [Install dependencies](#install-dependencies)
  - [Configure and start the MCP Server](#configure-and-start-the-mcp-server)
  - [Connect to an AI Agent host](#connect-to-an-ai-agent-host)
  - [Ingest documents into the knowledge base](#ingest-documents-into-the-knowledge-base)
  - [Run a health check](#run-a-health-check)
  - [Environment variables reference](#environment-variables-reference)
- [User-side Usage](#user-side-usage)
  - [Querying the knowledge base](#querying-the-knowledge-base)
  - [Manual exploration with MCP tools](#manual-exploration-with-mcp-tools)
  - [Tidying the knowledge base](#tidying-the-knowledge-base)
- [Components reference](#components-reference)
- [Development](#development)
- [License](#license)

---

## Architecture

```
sediment/
├── mcp_server/
│   └── server.py           # MCP Server — exposes 3 tools to AI Agents
├── scripts/
│   ├── tidy_utils.py       # Stateless helper functions (dangling links, orphans, etc.)
│   └── health_check.py     # CLI diagnostic report generator
├── skills/
│   ├── ingest.md           # System prompt: AI-powered document ingestion
│   ├── tidy.md             # System prompt: knowledge base maintenance
│   └── explore.md          # System prompt: autonomous exploration protocol
└── knowledge-base/
    ├── entries/            # Formal knowledge entries (.md files)
    ├── placeholders/       # Concepts referenced but not yet defined
    └── sources/
        └── source_map.json # Maps source documents → entry names
```

The MCP Server exposes three tools:

- **`knowledge_list`** — returns all entry names (real-time, no cache)
- **`knowledge_read`** — reads the full content of any entry by name
- **`knowledge_ask`** — answers natural-language questions via an internal sub-agent using `skills/explore.md` as system prompt

---

## Server-side Deployment

> **This section is for administrators** who set up and maintain the Sediment server, ingest documents, and run health checks.

### Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) — the fast Python package manager

```bash
# Install uv (macOS / Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install dependencies

Clone the repository and install:

```bash
git clone https://github.com/huyusong10/Sediment.git
cd Sediment
uv sync
```

This creates a `.venv` virtual environment and installs all dependencies automatically (defined in `pyproject.toml`).

### Configure and start the MCP Server

#### Option A — Direct launch (for testing)

```bash
# Set knowledge base path (optional; defaults to ./knowledge-base)
export SEDIMENT_KB_PATH=/path/to/your/knowledge-base

# Set the CLI used by knowledge_ask (optional; defaults to opencode)
export SEDIMENT_CLI=opencode

# Start the server
uv run python mcp_server/server.py
```

#### Option B — Production launch via entry point

After `uv sync`, the console script is available:

```bash
SEDIMENT_KB_PATH=/path/to/kb uv run sediment-server
```

### Connect to an AI Agent host

**OpenCode** — add to your `opencode.json` MCP configuration:

```json
{
  "mcpServers": {
    "sediment": {
      "command": "uv",
      "args": [
        "run",
        "--project", "/path/to/sediment",
        "python", "mcp_server/server.py"
      ],
      "env": {
        "SEDIMENT_KB_PATH": "/path/to/your/knowledge-base",
        "SEDIMENT_CLI": "opencode"
      }
    }
  }
}
```

**Claude Desktop** — add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sediment": {
      "command": "uv",
      "args": [
        "run",
        "--project", "/path/to/sediment",
        "python", "mcp_server/server.py"
      ],
      "env": {
        "SEDIMENT_KB_PATH": "/path/to/your/knowledge-base"
      }
    }
  }
}
```

> **Security note:** `knowledge_read` rejects filenames containing `/`, `\`, or `..` to prevent path traversal. The MCP Server performs **no write operations** on the knowledge base.

### Ingest documents into the knowledge base

1. In your AI Agent host (e.g., OpenCode), load `skills/ingest.md` as the system prompt.
2. Paste or point to the document you want to ingest.
3. The agent will:
   - Extract atomic knowledge entries → write to `knowledge-base/entries/`
   - Create placeholder files for referenced-but-undefined concepts → `knowledge-base/placeholders/`
   - Update `knowledge-base/sources/source_map.json`

> **Principle:** One proposition = one file. When in doubt, split rather than merge.

### Run a health check

```bash
uv run python scripts/health_check.py knowledge-base
```

Sample output:

```
Sediment Knowledge Base — Health Report
========================================
Generated: 2024-01-15 10:30:00

SUMMARY
-------
Total entries:       12  (formal: 10, placeholders: 2)

PLACEHOLDER REFS
----------------
High (>=5):    0
Medium (2-4):  1
  - some-concept (3 refs)
Low (1):       0

ORPHAN ENTRIES
--------------
Count: 0

DANGLING LINKS
--------------
Count: 0

RECOMMENDATION
--------------
Knowledge base looks healthy. Consider ingesting more documents.
```

Recommendation logic:

| Condition | Recommendation |
|---|---|
| Placeholders with ≥ 5 references | Run tidy with induction mode |
| Orphan entries exist | Run tidy to add missing links |
| Dangling links exist | Run tidy to resolve broken links |
| All clear | Knowledge base looks healthy |

### Environment variables reference

| Variable | Default | Description |
|---|---|---|
| `SEDIMENT_KB_PATH` | `./knowledge-base` | Path to the knowledge base root directory |
| `SEDIMENT_CLI` | `opencode` | CLI command used by `knowledge_ask` sub-agent (can be `claude`, `opencode`, etc.) |

---

## User-side Usage

> **This section is for end users** who query the knowledge base through an AI Agent that has Sediment connected as an MCP server.

### Querying the knowledge base

Once Sediment is connected as an MCP server, simply ask your AI Agent natural-language questions. The agent can use the `knowledge_ask` tool to query the knowledge base:

```
User: What is our API permission control policy?
Agent: [calls knowledge_ask("What is our API permission control policy?")]
       → returns { "answer": "...", "sources": ["entry-name-1", "entry-name-2"] }
```

`knowledge_ask` internally:
1. Reads `skills/explore.md` as a sub-agent system prompt
2. Calls the configured CLI sub-agent to reason over the knowledge base
3. Returns a synthesized answer with source citations

> **Fallback:** If the CLI sub-agent is unavailable, `knowledge_ask` returns a graceful degradation message rather than crashing. You can then use manual exploration (see below).

### Manual exploration with MCP tools

You can also instruct your agent to use the lower-level tools directly:

```
# Step 1 — List all available entries
knowledge_list()
→ ["entry-A", "entry-B", "placeholder-C", ...]

# Step 2 — Read a specific entry
knowledge_read("entry-A")
→ Full Markdown content of the entry

# Step 3 — Follow [[Related]] links to explore connected concepts
```

Load `skills/explore.md` as your agent's system prompt for a guided exploration protocol that goes at least 2 link-levels deep before concluding.

### Tidying the knowledge base

> Tidy operations require **admin access** (ability to write files to the knowledge base). All tidy suggestions are presented for human confirmation before any file is written.

1. Load `skills/tidy.md` as your agent's system prompt.
2. The agent will diagnose the knowledge base and suggest targeted actions:

| Action | Trigger | Effect |
|---|---|---|
| Resolve dangling links | `[[reference]]` points to non-existent file | Create placeholder file |
| Inductive reasoning | Placeholder has ≥ 3 references | Draft a formal entry from usage contexts |
| Merge duplicates | Semantically similar entries found | Propose merge with unified content |
| Fix orphan nodes | Entry has no in-links or out-links | Suggest 1-3 links to existing entries |

3. Review each suggestion, confirm, and the agent writes the changes.
4. Agent runs `health_check.py` at the end to show before/after improvement.

---

## Components reference

| Component | Path | Description |
|---|---|---|
| MCP Server | `mcp_server/server.py` | Exposes `knowledge_list`, `knowledge_read`, `knowledge_ask` |
| Tidy Utils | `scripts/tidy_utils.py` | Stateless KB analysis: dangling links, orphans, placeholder refs, context collection |
| Health Check | `scripts/health_check.py` | CLI diagnostic report |
| Ingest Skill | `skills/ingest.md` | System prompt for AI-powered document ingestion |
| Tidy Skill | `skills/tidy.md` | System prompt for KB maintenance (human-confirmed writes) |
| Explore Skill | `skills/explore.md` | Autonomous exploration protocol; also used as `knowledge_ask` sub-agent prompt |
| Knowledge Base | `knowledge-base/` | Entries, placeholders, and source map |

---

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Run linter
uv run ruff check .

# Run tests
uv run pytest tests/

# Verify tidy utils against example data
uv run python -c "
from scripts.tidy_utils import *
kb = 'knowledge-base'
print('dangling:', find_dangling_links(kb))
print('placeholder refs:', count_placeholder_refs(kb))
print('orphans:', find_orphan_entries(kb))
print('contexts:', collect_ref_contexts(kb, '示例-占位文件说明'))
"
```

---

## License

[MIT](LICENSE)

---
