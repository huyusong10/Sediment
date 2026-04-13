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

```bash
export SEDIMENT_KB_PATH=/path/to/your/knowledge-base
export SEDIMENT_CLI=claude
uv run sediment-server
uv run sediment-worker
```

The server hosts three surfaces at once:

- `MCP` via SSE / JSON-RPC
- `Portal` at `/portal`
- `Admin` at `/admin`

The worker is the default execution path for queued `ingest` / `tidy` jobs.
For single-process local debugging you can also set `SEDIMENT_RUN_JOBS_IN_PROCESS=1`
and run only the server, but production deployments should keep the worker
separate.

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `SEDIMENT_KB_PATH` | project `knowledge-base/` | Path to the KB root |
| `SEDIMENT_CLI` | `claude` | CLI command used by `knowledge_ask` and experimental workflow harnesses |
| `SEDIMENT_HOST` | `0.0.0.0` | HTTP bind address |
| `SEDIMENT_PORT` | `8000` | HTTP port |
| `SEDIMENT_SSE_PATH` | `/sediment/` | SSE endpoint path |
| `SEDIMENT_ADMIN_TOKEN` | empty | Optional Bearer token required for `/admin` and admin APIs |
| `SEDIMENT_SESSION_SECRET` | `SEDIMENT_ADMIN_TOKEN` | Optional signing secret for admin session cookies |
| `SEDIMENT_ADMIN_SESSION_COOKIE_NAME` | `sediment_admin_session` | Cookie name for web-admin sessions |
| `SEDIMENT_ADMIN_SESSION_TTL_SECONDS` | `43200` | Admin session lifetime in seconds |
| `SEDIMENT_SECURE_COOKIES` | `0` | Mark admin cookies as `Secure`; enable this behind HTTPS |
| `SEDIMENT_TRUST_PROXY_HEADERS` | `0` | Whether to trust `X-Forwarded-For` / `X-Real-IP` |
| `SEDIMENT_TRUSTED_PROXY_CIDRS` | empty | Comma-separated proxy CIDRs allowed to supply real client IPs |
| `SEDIMENT_SUBMISSION_RATE_LIMIT_COUNT` | `1` | Max submissions per IP inside the rate-limit window |
| `SEDIMENT_SUBMISSION_RATE_LIMIT_WINDOW_SECONDS` | `60` | Submission rate-limit window |
| `SEDIMENT_SUBMISSION_DEDUPE_WINDOW_SECONDS` | `86400` | Exact-duplicate submission dedupe window |
| `SEDIMENT_MAX_TEXT_SUBMISSION_CHARS` | `20000` | Max size of a text submission |
| `SEDIMENT_MAX_UPLOAD_BYTES` | `10485760` | Max uploaded document size |
| `SEDIMENT_STATE_DIR` | `.sediment_state/` | Root directory for platform DB, uploads, and worker workspaces |
| `SEDIMENT_DB_PATH` | `.sediment_state/platform.db` | SQLite path for submissions, jobs, reviews, and audit logs |
| `SEDIMENT_UPLOADS_DIR` | `.sediment_state/uploads/` | Stored uploaded documents |
| `SEDIMENT_WORKSPACES_DIR` | `.sediment_state/workspaces/` | Isolated worker workspaces for ingest/tidy jobs |
| `SEDIMENT_JOB_MAX_ATTEMPTS` | `3` | Automatic retry ceiling for worker jobs |
| `SEDIMENT_JOB_STALE_AFTER_SECONDS` | `900` | Heartbeat timeout before a running job is recovered |
| `SEDIMENT_RUN_JOBS_IN_PROCESS` | `0` | Run jobs in the server process instead of an external worker |

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
- `knowledge_submission_queue`
- `knowledge_job_status`
- `knowledge_review_decide`

REST/admin surfaces now also expose:

- `GET /healthz`
- `GET|POST|DELETE /api/admin/session`
- `GET /api/admin/system/status`
- `GET /api/admin/audit`
- `POST /api/admin/jobs/{id}/retry`
- `POST /api/admin/jobs/{id}/cancel`

## Use The KB

- **Explore**: ask natural-language questions through `knowledge_ask`, or use `knowledge_list` + `knowledge_read`
- **Health**: run `uv run python skills/health/scripts/health_check.py knowledge-base`
- **Ingest (experimental)**: load `skills/ingest/SKILL.md` as a workflow instruction and feed source materials
- **Tidy (experimental)**: load `skills/tidy/SKILL.md` as a workflow instruction to repair graph gaps, invalid entries, and promotable placeholders
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
export SEDIMENT_KB_PATH=/absolute/path/to/knowledge-base
export SEDIMENT_CLI=claude
export SEDIMENT_RUN_JOBS_IN_PROCESS=0
uv run sediment-server
uv run sediment-worker
```

Tests use `tests/fixtures/mock_workflow_cli.py` to simulate the Agent runner, but
real deployments should point `SEDIMENT_CLI` at an actual local coding CLI.

When editing the runtime:
- keep sources in frontmatter `sources`, never as `[[wikilinks]]`
- do not let provenance create graph edges
- keep MCP tool names and `knowledge_ask` response schema stable
- route write paths through the buffered review flow unless you are doing a controlled admin edit

## Production Hardening

Minimum deployment baseline:

- set `SEDIMENT_ADMIN_TOKEN`
- set `SEDIMENT_SESSION_SECRET`
- enable `SEDIMENT_SECURE_COOKIES=1` behind HTTPS
- run `sediment-server` and `sediment-worker` as separate processes
- if you are behind a reverse proxy, enable `SEDIMENT_TRUST_PROXY_HEADERS=1` and restrict `SEDIMENT_TRUSTED_PROXY_CIDRS`
- monitor `/healthz` and the admin system-status panel

The worker now writes job heartbeats, recovers stale `running` jobs after the
configured timeout, supports explicit cancel / retry controls, and leaves a
structured audit trail for session, queue, review, and writeback actions.

## License

[MIT](LICENSE)
