# Sediment

Tacit knowledge extraction system for AI Agents — turns enterprise documents into a structured, human-reviewable knowledge base.

---

## What it does

Sediment helps organizations capture and organize **tacit knowledge** — the kind that lives in people's heads, scattered documents, and implicit conventions — into a structured, navigable knowledge base that AI Agents can query and contribute to.

Key capabilities:
- **Ingest**: Parse documents and extract atomic knowledge entries using an AI-powered ingestion skill
- **Tidy**: Maintain knowledge base consistency — resolve dangling links, fill placeholders via inductive reasoning, merge duplicates, and fix orphan nodes
- **Explore**: Let AI Agents autonomously discover and synthesize relevant knowledge via MCP tools
- **Health Check**: Run a diagnostic report on the knowledge base at any time

---

## Quick Start

> **Requires [uv](https://docs.astral.sh/uv/) — the fast Python package manager.**
> Install it with: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 1. Install dependencies

```bash
uv sync
```

This creates a virtual environment and installs all dependencies automatically.

### 2. Set knowledge base path

```bash
export SEDIMENT_KB_PATH=/path/to/your/knowledge-base
```

### 3. Start MCP Server

```bash
uv run python mcp_server/server.py
```

### 4. Connect from OpenCode

Add to your OpenCode MCP config:
```json
{
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
```

### 5. Ingest documents (admin)

In OpenCode, load `skills/ingest.md` as your system prompt, then provide document paths.

### 6. Query knowledge (users)

Use the `knowledge_ask` MCP tool, or load `skills/explore.md` and use `knowledge_list` + `knowledge_read` directly.

---

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Run linter
uv run ruff check .

# Run tests
uv run pytest tests/
```

---

## Components

| Component | Path | Description |
|-----------|------|-------------|
| MCP Server | `mcp_server/server.py` | Exposes `knowledge_list`, `knowledge_read`, `knowledge_ask` tools |
| Tidy Utils | `scripts/tidy_utils.py` | Stateless helper functions for knowledge base analysis |
| Health Check | `scripts/health_check.py` | CLI diagnostic report generator |
| Ingest Skill | `skills/ingest.md` | System prompt for AI-powered document ingestion |
| Tidy Skill | `skills/tidy.md` | System prompt for knowledge base maintenance |
| Explore Skill | `skills/explore.md` | Autonomous exploration protocol for AI Agents |
| Knowledge Base | `knowledge-base/` | Entries, placeholders, and source map |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SEDIMENT_KB_PATH` | `./knowledge-base` | Path to knowledge base root |
| `SEDIMENT_CLI` | `opencode` | CLI command for `knowledge_ask` sub-agent |

---

## License

MIT
