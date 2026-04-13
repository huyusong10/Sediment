<div align="center">

<img src="src/sediment/assets/logo.svg" alt="Sediment Logo" width="360" />

# Sediment

**A white-box knowledge base for AI agents and the teams behind them.**

Turn messy materials into a Markdown knowledge base that stays reviewable, searchable, and governable.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

[English](README.md) | [中文](README_zh.md)

</div>

## Why Sediment

Most internal knowledge systems fail in one of two ways:

- They are too opaque: the retrieval works until no one can explain why.
- They are too loose: anyone can write anything and the knowledge base slowly rots.

Sediment aims for the middle ground:

- White-box knowledge: the canonical source of truth is plain files.
- Agent-assisted workflows: ingest, tidy, search, and health checks are built in.
- Human review first: submissions and edits flow through review instead of silently mutating the knowledge base.
- Multi-surface runtime: the same system powers CLI, MCP, and web interfaces.

## What It Includes

- A Python package with a standard `src/` layout
- A local-instance CLI: `sediment`
- MCP server plus web portal and admin console
- Hosted `ingest` / `tidy` job workflow with review queues
- Support for multiple agent CLIs:
  - Claude Code CLI
  - Codex CLI
  - OpenCode CLI

## Install

```bash
git clone https://github.com/huyusong10/Sediment.git
cd Sediment
uv run --project . sediment --help
```

For local development:

```bash
uv run --project . pytest -q
```

## Quick Start

Initialize a Sediment instance in your workspace:

```bash
mkdir my-sediment-workspace
cd my-sediment-workspace
uv run --project /path/to/Sediment sediment init \
  --instance-name ops-prod \
  --knowledge-name "Ops Knowledge Base"
```

Check the instance:

```bash
uv run --project /path/to/Sediment sediment doctor
```

Run the platform:

```bash
uv run --project /path/to/Sediment sediment server run
```

Then open:

- `http://127.0.0.1:8000/portal`
- `http://127.0.0.1:8000/admin`
- `http://127.0.0.1:8000/healthz`

## Core Commands

```bash
sediment init
sediment doctor
sediment status
sediment server start
sediment server stop
sediment kb explore "What is heat backup?"
sediment review list
sediment logs tail
```

Sediment stores runtime configuration per instance in:

```text
./config/sediment/config.yaml
```

That keeps instances local to each workspace while still allowing global instance management through the CLI.

## Project Layout

```text
src/sediment/      Python package, MCP runtime, web UI, built-in skills
tests/             automated test suite
scripts/           helper scripts
benchmarks/        internal evaluation harness
design/            deeper design documents
```

## Philosophy

Sediment is opinionated about a few things:

- Knowledge should be inspectable.
- Structure should be strong enough for validation.
- Agent output should be reviewable before it becomes canonical.
- Enterprise workflows should not require editing the knowledge base host by hand.

## Documentation

- Design docs: [design/README.md](design/README.md)
- Architecture notes: [design/current/platform-architecture.md](design/current/platform-architecture.md)

## License

MIT
