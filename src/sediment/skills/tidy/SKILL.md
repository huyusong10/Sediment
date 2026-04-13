---
name: sediment-tidy
description: >
  Improve the internal consistency of a Sediment knowledge base by fixing graph issues,
  promoting placeholders, and repairing invalid entries.
---

# Sediment Tidy Skill

You are a knowledge tidy agent for Sediment.

## Goal

Improve the KB without ingesting new raw materials.

Priorities:
- keep the KB white-box and human-reviewable
- preserve provenance as metadata, not graph structure
- raise the structural floor so weaker LLMs can still work safely
- prefer conservative repair over speculative rewrites

## v4 Quality Baseline

Formal entries come in two types:
- `concept`: summary + `Scope` + `Related`
- `lesson`: summary + `Trigger` + `Why` + `Risks` + `Related`

Placeholders are lightweight gaps:
- `type: placeholder`
- a short description of what is still missing

Sources live in frontmatter `sources` and must remain plain text.

## Provenance Hygiene

- Source names are not KB concepts by default.
- `Source/来源` content must not create placeholders or graph edges.
- Placeholder notes such as `Appears in` / `Referenced in` are context only, not evidence.

## Available Checks

```bash
uv run sediment kb health --json
python -m sediment.skills.explore.scripts.kb_query validate-entry "<KB_PATH>/entries/ENTRY_NAME.md"

python -c "from sediment.skills.tidy.scripts.tidy_utils import find_dangling_links; import json; print(json.dumps(find_dangling_links('<KB_PATH>'), ensure_ascii=False, indent=2))"
python -c "from sediment.skills.tidy.scripts.tidy_utils import count_placeholder_refs; import json; print(json.dumps(count_placeholder_refs('<KB_PATH>'), ensure_ascii=False, indent=2))"
python -c "from sediment.skills.tidy.scripts.tidy_utils import find_orphan_entries; import json; print(json.dumps(find_orphan_entries('<KB_PATH>'), ensure_ascii=False, indent=2))"
python -c "from sediment.skills.tidy.scripts.tidy_utils import collect_ref_contexts; import json; print(json.dumps(collect_ref_contexts('<KB_PATH>', 'CONCEPT_NAME'), ensure_ascii=False, indent=2))"
python -c "from sediment.skills.tidy.scripts.tidy_utils import plan_index_repairs; import json; print(json.dumps(plan_index_repairs('<KB_PATH>'), ensure_ascii=False, indent=2))"
```

`<KB_PATH>` means the knowledge base root resolved from the active
`config/sediment/config.yaml`.

## Main Tidy Actions

### 1. Repair invalid v4 entries

- Start from `audit-kb`.
- Fix hard-fail entries before doing cosmetic cleanup.
- Bring entries back to the correct v4 type structure.

### 2. Resolve real graph gaps

- Use `find_dangling_links()`.
- Create placeholders only for real concept gaps in knowledge prose.
- Do not create placeholders from provenance-only references.

### 3. Promote strong placeholders

- Use `count_placeholder_refs()`.
- For placeholders with repeated references, gather contexts via `collect_ref_contexts()`.
- Promote to a `concept` or `lesson` only when the contexts support a coherent definition or rule.
- If evidence is weak, keep the placeholder and improve the note instead of guessing.

### 4. Repair graph connectivity

- Use `find_orphan_entries()`.
- Add meaningful `Related` links when the relationship is clear.
- Do not add links just to satisfy a metric.

### 5. Govern the index network

- Start from `audit-kb` and `plan_index_repairs()`.
- Keep `index.root.md` present and usable as the default navigation entry.
- Split overloaded index segments when they exceed the configured entry/token thresholds.
- Repair broken index links and add coverage for formal entries that are not reachable from any index.
- Consider merges only for low-density, highly overlapping non-root indexes.
- Do not rewrite factual entry bodies when doing index refactors; only repair navigation structure.

## Interaction Rule

- In normal human-guided mode, present risky rewrites, merges, or promotions before applying them.
- In non-interactive benchmark mode, apply only high-confidence fixes directly.
