# Sediment

Tacit knowledge extraction system for AI Agents — turns enterprise documents into a structured, human-reviewable knowledge base.

## What it does

Sediment ingests enterprise documents, extracts atomic knowledge propositions, and organizes them into a structured knowledge base that AI agents can explore and query through an MCP server.

## Quick Start

### 1. Install

```bash
pip install -r mcp_server/requirements.txt
```

### 2. Set knowledge base path

```bash
export SEDIMENT_KB_PATH=/path/to/your/knowledge-base
```

### 3. Start MCP Server

```bash
python mcp_server/server.py
```

### 4. Connect from OpenCode

Add to your OpenCode MCP config:

```json
{
  "sediment": {
    "command": "python",
    "args": ["/path/to/sediment/mcp_server/server.py"],
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

## Components

- **MCP Server** — Exposes `knowledge_list`, `knowledge_read`, and `knowledge_ask` tools
- **Skills** — Ingest, Tidy, and Explore skill definitions for AI agents
- **Scripts** — Health check and tidy utilities for knowledge base maintenance
- **Knowledge Base** — Structured Markdown entries with link-based navigation

## License

MIT
