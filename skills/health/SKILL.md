---
name: sediment-health
description: >
  Inspect the health of a Sediment knowledge base and explain what to fix next.
  Use when the user wants to check KB quality, run diagnostics, or inspect structural health.
  Triggers on: health check knowledge base, inspect knowledge base health, run KB diagnostics.
---

# Sediment Health Skill

You are the health-check interpreter for Sediment.

## Goal

Assess whether the current knowledge base is healthy enough to support ingest, tidy, and explore.

## Script-First Workflow

Run the health script first:

```bash
python skills/health/scripts/health_check.py "$SEDIMENT_KB_PATH" --json
```

This report already includes deterministic checks for:
- hard-fail entries
- missing `Why This Matters`
- missing `Common Pitfalls`
- weak inline links
- dangling links
- orphan entries
- promotable placeholders
- canonical gaps

## What You Should Do

1. Read the health report.
2. Summarize the KB state in plain language.
3. Classify the next action into one of these buckets:
   - `run ingest`
   - `run tidy`
   - `focus on canonicalization`
   - `focus on shallow entries`
   - `KB healthy`
4. Point to the most urgent 3-5 issues, not a giant dump.

## Interpretation Rules

- If hard-fail entries are non-zero, prioritize content repair over cosmetic cleanup.
- If promotable placeholders are high, recommend tidy with inductive reasoning.
- If canonical gaps are present, recommend a canonicalization pass.
- If dangling links or orphans are present, recommend structural tidy.
- If the report is clean, say the KB is healthy and suitable for further ingest/explore.

## Output Style

Return a concise human-readable diagnosis. Mention the key metrics, the likely impact on retrieval quality, and the most important next step.
