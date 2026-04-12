---
name: sediment-health
description: >
  Inspect the health of a Sediment knowledge base and explain what to fix next.
---

# Sediment Health Skill

You interpret the v4 health report for humans.

## Workflow

Run the health script first:

```bash
python skills/health/scripts/health_check.py "$SEDIMENT_KB_PATH" --json
```

The report includes deterministic checks for:
- invalid formal entries
- missing `Scope`
- missing `Trigger`
- missing `Why`
- missing `Risks`
- weak `Related` sections
- dangling links
- orphan entries
- promotable placeholders
- concept gaps

## Your Job

1. Summarize the KB state in plain language.
2. Explain the impact on retrieval and tidy quality.
3. Recommend the next action:
   - `run ingest`
   - `run tidy`
   - `focus on structure repair`
   - `focus on concept coverage`
   - `KB healthy`
4. Highlight the 3-5 most important issues, not a giant dump.

## Interpretation Rules

- If hard-fail entries are non-zero, structure repair comes first.
- If promotable placeholders are high, recommend tidy with inductive reasoning.
- If concept gaps are present, recommend a concept coverage pass.
- If dangling links or orphans are present, recommend graph repair.
- If the report is clean, say the KB is healthy and suitable for further ingest/explore.
