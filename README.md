<div align="center">

<img src="resources/logo.svg" alt="Sediment Logo" width="450"/>

<br/>

**Tacit knowledge extraction system for AI Agents**

*Turns messy materials into a white-box knowledge base that humans and agents can inspect together.*

<br/>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

</div>

---

[🇺🇸 English](README.md) | [🇨🇳 中文](README_zh.md)

---

Sediment is a white-box tacit-knowledge system for AI agents. It focuses on a
reliable runtime for inspecting, validating, and retrieving a Markdown
knowledge base, and now also ships an enterprise platform layer for submissions,
review, health dashboards, and hosted ingest/tidy execution through a local
Agent runner.

Sediment v4 is built around a few non-negotiable ideas:
- **White-box first**: the knowledge base is just files, not a hidden database
- **Provenance is metadata**: sources stay traceable, but source names are not graph nodes
- **Moderate structure beats fragile freedom**: entries have enough shape for reliable tidy/health checks without becoming heavyweight forms
- **Human review stays easy**: the same files work for agents, scripts, and editors such as Obsidian

See [design/README.md](design/README.md) for the design map. Core principles live in [design/core-principles.md](design/core-principles.md), the current design is split under [design/current/](design/current/overview.md), and historical `v3` / `v4` / `v4.5` documents are retained under [design/evolution/](design/evolution/README.md).

## v4 Entry Model

Sediment formal entries come in two types plus a lightweight placeholder form.

### Concept entry

```markdown
---
type: concept
status: fact
aliases: []
sources:
  - source document name
---
# Heat Backup

Heat backup is the ready-to-take-over backup path used when the primary path cannot be trusted.

## Scope
Use it for systems that require continuity during failover, especially when switching paths must be controlled.

## Related
- [[Failover]] - heat backup is a prerequisite for controlled failover
```

### Lesson entry

```markdown
---
type: lesson
status: inferred
aliases: []
sources:
  - incident review name
---
# Confirm heat backup before draining traffic

Confirm heat backup before draining traffic, or the protective action can create a larger recovery problem.

## Trigger
Use this when traffic is being actively shifted, drained, or throttled during risk mitigation.

## Why
Traffic movement changes the system shape immediately, so backup readiness must be verified before the move.

## Risks
If ignored, the system may survive the original issue but fail during the mitigation path.

## Related
- [[Heat Backup]] - prerequisite capability
```

### Placeholder entry

```markdown
---
type: placeholder
aliases: []
---
# Dark Flow

This concept is referenced in the knowledge base but is not yet defined well enough to promote.
```

## Install

```bash
git clone https://github.com/huyusong10/Sediment.git
cd Sediment
uv sync --dev
```

Built-in runtime code and skill resources live under:

```text
mcp_server/
skills/
  ingest/
  tidy/
  explore/
  health/
```

## Run The Platform

Sediment now loads its runtime configuration from
[`config/sediment/config.yaml`](config/sediment/config.yaml) by default. You can
override it per command with `--config /path/to/config.yaml`.

If that project-local file is absent, Sediment falls back to a user-level config:

- macOS: `~/Library/Application Support/Sediment/config.yaml`
- Windows: `%APPDATA%/Sediment/config.yaml`
- Linux: `$XDG_CONFIG_HOME/sediment/config.yaml` or `~/.config/sediment/config.yaml`

Example:

```bash
cp config/sediment/config.yaml /your/workspace/config/sediment/config.yaml
uv run sediment server run
```

The default config is repository-local and cross-platform. Path fields are
resolved through `paths.workspace_root`, and `agent.command` supports either a
single string or an explicit YAML list to avoid quoting issues on Windows.

For daemon-style control, use the same entrypoint:

```bash
uv run sediment server start
uv run sediment server status
uv run sediment server stop
```

`uv run sediment up` is kept as a short alias for foreground local startup.

The platform hosts three surfaces at once:

- `MCP` via SSE / JSON-RPC
- `Portal` at `/portal`
- `Admin` at `/admin`

Under the hood, queued `ingest` / `tidy` jobs still run through the worker role.
Normal deployments should keep queue execution separate.

Compatibility shims are still available for lower-level debugging:

- `uv run sediment-server`
- `uv run sediment-worker`
- `uv run sediment-up`

Key config sections:

- `paths`: workspace root, knowledge base, state DB, uploads, worker workspaces
- `server`: bind host/port, SSE path, in-process job mode
- `auth`: admin token, session secret, secure cookie settings
- `network`: trusted proxy and real-IP behavior
- `submissions`: rate limits, dedupe window, upload/text size limits
- `jobs`: retry ceiling and stale-job timeout
- `agent`: selected backend plus backend-specific command/model options
- `knowledge`: locale, query-language override, and index contract defaults

Supported `agent.backend` values:

- `claude-code`
- `codex`
- `opencode`

Example agent block:

```yaml
agent:
  backend: codex
  command:
    - codex
  model: gpt-5-codex
  sandbox: workspace-write
  exec_timeout_seconds: 240
```

## Portal And Admin

After the server starts:

- Portal: [http://localhost:8000/portal](http://localhost:8000/portal)
- Admin: [http://localhost:8000/admin](http://localhost:8000/admin)
- Health: [http://localhost:8000/healthz](http://localhost:8000/healthz)

The portal supports:

- full-text search
- graph browsing
- reading entry/index content
- submitting text concepts, lessons, and documents into the review buffer

The admin console supports:

- login via signed same-site admin session cookies
- health issue queues
- system status, queue mode, and runtime limits
- buffered submission triage
- queued/running/reviewable ingest and tidy jobs
- job retry / cancellation / stale-job recovery visibility
- review approval / rejection
- direct online Markdown editing with validation
- recent audit logs

## Public Interfaces

Stable read tools remain:

- `knowledge_list`
- `knowledge_read`
- `knowledge_ask`

New platform tools include:

- `knowledge_submit_text`
- `knowledge_submit_document`
- `knowledge_health_report`
- `knowledge_platform_status`
- `knowledge_submission_queue`
- `knowledge_job_status`
- `knowledge_tidy_request`
- `knowledge_review_decide`

REST/admin surfaces now also expose:

- `GET /healthz`
- `GET|POST|DELETE /api/admin/session`
- `GET /api/admin/system/status`
- `GET /api/admin/audit`
- `POST /api/admin/jobs/{id}/retry`
- `POST /api/admin/jobs/{id}/cancel`

The unified CLI surface is:

- `sediment server ...` for lifecycle control, logs, and daemon status
- `sediment kb ...` for explore, list, read, health, and tidy actions
- `sediment status ...` for platform, daemon, queue, and KB-health summaries
- `sediment doctor` for config, filesystem, and agent-backend health checks

## Use The KB

- **Explore**: ask natural-language questions through `knowledge_ask`, or run `uv run sediment kb explore "your question"`
- **Health**: run `uv run sediment kb health` or `uv run python skills/health/scripts/health_check.py knowledge-base`
- **Inspect status**: run `uv run sediment status`, `uv run sediment status queue`, or `uv run sediment server status`
- **Ingest (experimental)**: load `skills/ingest/SKILL.md` as a workflow instruction and feed source materials
- **Tidy (experimental)**: load `skills/tidy/SKILL.md` as a workflow instruction, or queue a targeted repair with `uv run sediment kb tidy "<entry-name>"`
- **Portal submissions**: send text or documents into the buffered review flow
- **Admin review**: approve/reject queued ingest and tidy patches from the web UI or admin APIs

Benchmark scripts under `testcase/` are internal evaluation harnesses, not part
of Sediment's public runtime surface.

`knowledge_ask` keeps the same public interface:

```json
{
  "answer": "...",
  "sources": ["entry-name-1", "entry-name-2"],
  "confidence": "high",
  "exploration_summary": {
    "entries_scanned": 12,
    "entries_read": 4,
    "links_followed": 3,
    "mode": "definition-driven"
  },
  "gaps": [],
  "contradictions": []
}
```

## Development

```bash
uv sync --dev
uv run ruff check .
uv run pytest
uv build
```

For local end-to-end development:

```bash
uv run sediment server run
```

Useful checks:

```bash
uv run sediment doctor
uv run sediment doctor --json
```

Tests use `tests/fixtures/mock_workflow_cli.py` to simulate the Agent runner.

When editing the runtime:
- keep sources in frontmatter `sources`, never as `[[wikilinks]]`
- do not let provenance create graph edges
- keep MCP tool names and `knowledge_ask` response schema stable
- route write paths through the buffered review flow unless you are doing a controlled admin edit

## Production Hardening

Minimum deployment baseline:

- set `auth.admin_token`
- set `auth.session_secret`
- enable `auth.secure_cookies: true` behind HTTPS
- use `sediment server run` for local/dev convenience
- use `sediment server start|stop|status|logs` for daemon control
- keep `server` and `worker` as separate roles in production, even if you launch them through one `sediment` entrypoint
- if you are behind a reverse proxy, set `network.trust_proxy_headers: true` and restrict `network.trusted_proxy_cidrs`
- monitor `/healthz` and the admin system-status panel

The worker now writes job heartbeats, recovers stale `running` jobs after the
configured timeout, supports explicit cancel / retry controls, and leaves a
structured audit trail for session, queue, review, and writeback actions.

`sediment server run` and `sediment up` are thin launchers around the split
architecture. They start both roles, prefix logs with `[server]` / `[worker]`,
wait for `/healthz`, and shut both children down together when you press `Ctrl+C`.

## License

[MIT](LICENSE)
