# Sample Workspace

The official `examples/` workspace is meant to let a new user experience more than just search results.

It now includes:

- a canonical knowledge base with segmented indexes
- placeholder gaps that show up in health and graph workflows
- checked-in insight proposals that light up the portal universe and admin insights surface
- `demo-materials/` for text submission and document upload demos
- `scripts/seed_runtime_demo.py` to populate local runtime-only signals, clusters, graph events, and inbox items

## Quick Start

```bash
cd examples
sediment init
uv run --project .. python scripts/seed_runtime_demo.py --workspace .
sediment server run
```

The seed script is idempotent. It only writes into the local `.sediment_state/` runtime area and does not mutate the checked-in Markdown knowledge base.

## What To Try

- Open `/portal` and `/portal/graph-view` to browse the seeded hotspots and insight proposals.
- Open `/admin`, sign in with the one-time token, then inspect `Overview`, `Knowledge Base`, `Files`, and `Inbox`.
- Upload the whole `demo-materials/ingest-batch/` folder to exercise staged document ingestion.
- Paste `demo-materials/text-feedback/图谱体验建议.md` into the text submission form.
- Reuse the prompts in `demo-materials/explore-queries.md` for CLI explore or the admin Explore panel.
