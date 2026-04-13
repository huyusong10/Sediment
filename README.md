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

Sediment is built on a simple bet:

> If AI is going to participate in institutional memory, that memory must remain legible to humans.

That means the knowledge base cannot just be searchable. It has to stay inspectable, diffable, reviewable, and governable over time.

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

### Automatic Mode

For macOS and Linux, the fastest path is a one-command installer:

```bash
curl -fsSL https://raw.githubusercontent.com/huyusong10/Sediment/master/install.sh | bash
```

This installs the `sediment` CLI with `uv`, then leaves you with a normal command on your PATH:

```bash
sediment --help
```

The installer replaces and reinstalls an existing `sediment` CLI by default, so rerunning it works as a reliable upgrade path too.

### Manual Mode

If you prefer to inspect the source and install it yourself:

```bash
git clone https://github.com/huyusong10/Sediment.git
cd Sediment
uv tool install --from . sediment --compile-bytecode
sediment --help
```

This is also the recommended path on Windows.

For local development:

```bash
uv run --project . pytest -q
```

## Quick Start

Initialize a Sediment instance in your workspace:

```bash
mkdir my-sediment-workspace
cd my-sediment-workspace
sediment init
```

`sediment init` opens an interactive setup wizard in a normal terminal. It asks for the instance
name, knowledge name, agent backend, host, and port. Press Enter to accept the suggested default
value for any field.

If you prefer a scriptable path:

```bash
sediment init \
  --instance-name ops-prod \
  --knowledge-name "Ops Knowledge Base" \
  --backend claude-code \
  --host 127.0.0.1 \
  --port 8000 \
  --no-interactive
```

List the known instances and check the current one:

```bash
sediment instance list
sediment doctor
```

Run the platform:

```bash
sediment server run
```

Then open:

- `http://127.0.0.1:8000/portal`
- `http://127.0.0.1:8000/admin`
- `http://127.0.0.1:8000/healthz`

## What Makes It Different

Sediment is not trying to be another black-box retrieval layer wrapped in a pleasant UI.

It treats knowledge as infrastructure:

- Canonical knowledge lives in plain files rather than hidden state.
- Agent work is operationalized, but never allowed to silently become truth.
- Web, CLI, and MCP are not separate products; they are different surfaces over the same backend.
- Enterprise workflow is part of the design, not an afterthought bolted onto a toy demo.

## Core Commands

```bash
sediment init
sediment instance list
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

When you run commands inside an instance root, or inside its `knowledge-base/` directory, Sediment
resolves the local config automatically. In those cases you usually do not need `--instance`.

Use `--instance NAME` when you want to manage an instance from somewhere else:

```bash
sediment --instance ops-prod doctor
sediment --instance ops-prod server start
sediment --instance ops-prod review list
```

If you prefer not to install the CLI yet, you can still run it directly from the repo:

```bash
uv run --project /path/to/Sediment sediment --help
```

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

More broadly, Sediment is optimized for durable clarity, not short-term magic.

- It prefers explicit structure over hidden heuristics.
- It prefers review queues over silent mutation.
- It prefers local, inspectable instances over centralized mystery systems.
- It prefers knowledge that can survive staff turnover, tool churn, and model changes.

## Documentation

- Design docs: [design/README.md](design/README.md)
- Architecture notes: [design/current/platform-architecture.md](design/current/platform-architecture.md)

## License

MIT
