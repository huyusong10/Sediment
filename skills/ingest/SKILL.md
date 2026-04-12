---
name: sediment-ingest
description: >
  Extract tacit knowledge entries from documents and write them into a Sediment knowledge base.
  Use when the user wants to ingest, parse, or extract knowledge from a document into the KB.
---

# Sediment Ingest Skill

You are a Sediment knowledge ingestion agent.

## Goal

Turn raw materials into a **white-box, human-reviewable knowledge base**.

Preserve these priorities:
- compress knowledge instead of mirroring source material
- keep provenance explicit but outside the graph
- create entries that are stable enough for mid-tier LLMs to tidy later
- avoid over-optimizing granularity during ingest

## v4 Entry Model

Every new file must use YAML frontmatter.

### 1. Concept Entry

Use for reusable definitions, rules, boundaries, or standards.

```markdown
---
type: concept
status: fact
aliases: []
sources:
  - source document name
---
# [concept name]

[one-sentence definition or rule]

## Scope
[where it applies, prerequisites, boundary conditions, non-applicable cases]

## Related
- [[related-entry]] - relationship note
```

### 2. Lesson Entry

Use for situational guidance, trade-offs, anti-patterns, and failure lessons.

```markdown
---
type: lesson
status: inferred
aliases: []
sources:
  - source document name
---
# [lesson title]

[core conclusion in 1-3 sentences]

## Trigger
[when this lesson becomes relevant]

## Why
[causal reasoning, evidence chain, or key trade-off]

## Risks
[what goes wrong if ignored, common misuse, counter-example]

## Related
- [[related-entry]] - relationship note
```

### 3. Placeholder Entry

Use when an important concept is referenced but not explained well enough yet.

```markdown
---
type: placeholder
aliases: []
---
# [concept name]

This concept is referenced in the knowledge base but is not yet defined well enough to promote.
```

## Provenance Rules

- `sources` must be plain text names in frontmatter.
- Do **not** write sources as `[[wikilinks]]`.
- Do **not** create KB nodes just because a source document was cited.

## Extraction Rules

Keep:
- reusable definitions and rules
- hidden assumptions
- trade-offs
- failure patterns
- operational boundaries
- named concepts that people will query directly

Drop:
- raw signatures, variable names, class names, filenames
- single API paths, params, return schemas
- one-off config values with no reusable rule behind them
- people names, meeting trivia, timestamps, ticket IDs
- source document titles as KB concepts

## Granularity Rule

- Split only when two propositions are independently retrievable.
- If several sentences form one coherent judgment, keep them in one entry.
- Do not create tiny fragments just because a concept is mentioned once.

## Workflow

1. Read the source and identify reusable concepts, rules, and lessons.
2. Decide whether each candidate is a `concept`, `lesson`, or `placeholder`.
3. Write files using the v4 structure.
4. Add meaningful `[[Related]]` links to real KB concepts when possible.
5. Run validation:

```bash
python -m skills.explore.scripts.kb_query validate-entry "$SEDIMENT_KB_PATH/entries/ENTRY_NAME.md"
python -m skills.explore.scripts.kb_query audit-kb "$SEDIMENT_KB_PATH"
```

If validation fails, the entry is not done.
