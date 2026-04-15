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
aliases: [alias-1, alias-2]
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

**Aliases**: Every concept must have at least 2 aliases (unless it truly has none). Include:
- Common abbreviations or shorthand used in the materials
- Alternative phrasings that mean the same thing
- Related compound terms that contain this concept (e.g. if concept is "嗡鸣度", alias might include "嗡鸣度指标")
- The concept name suffixed with common nouns from context (e.g. "系统", "协议", "设备")
- Descriptive phrases that users might query instead of the exact concept name
- Aliases must stay same-entity: do not add neighboring teams, incidents, or co-occurring concepts as aliases just because they appear in the same sentence

### 2. Lesson Entry

Use for situational guidance, trade-offs, anti-patterns, and failure lessons.

```markdown
---
type: lesson
status: inferred
aliases: [alias-1, alias-2]
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

**Aliases**: Same rules as concept entries — include alternative phrasings and shorthand that appear in source materials.

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

**Aliases**: Include any known alternative names or shorthand mentioned in materials, even for placeholders.

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
- code-derived operational taxonomies, such as exception classes, failure states, retry/backoff rules, and TODO-backed implementation gaps
- process checklists and runbooks when they define stable step sequences that users may ask for directly
- multi-signal diagnostic chains when the material explicitly ties symptoms to likely causes or actions

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

## Canonical Bare-Term Coverage

When a concept has a short, standalone name that users will query directly (e.g. "潮涌", "嗡鸣度", "暗流"):
- The entry title MUST be that exact bare term — do not add suffixes like "机制", "现象", "操作" unless the term itself includes them.
- The first sentence of the entry body must be a direct, self-contained definition of that term. Do not assume the reader already knows what the term means.
- If the concept appears as part of a compound phrase in materials (e.g. "潮涌事故", "嗡鸣度指标"), create the bare-term entry and list the compound as an alias.
- If the source title wraps a canonical subject in packaging words such as "管理", "标准", or "指南", project the queryable subject into the KB (`谐振腔生命周期管理` -> `谐振腔生命周期`) instead of preserving the wrapper as the primary entry title.
- If a stable capability only appears embedded inside a longer sentence (`内置了定海针算法`, `由渡鸦团队介入调查`), still promote the bare public subject (`定海针`, `渡鸦团队`) rather than storing the whole sentence fragment as a title.
- If a structural wrapper only exists to describe the canonical subject (`驿站节点`, `隐身衣技术`, `嗡鸣度数据质量`, `管理谐振腔的完整生命周期`), project it back to the bare or canonical target (`驿站`, `隐身衣`, `嗡鸣度`, `谐振腔生命周期`) and keep the wrapper as alias / support evidence instead of a competing shallow entry.

## Definition Quality

Every concept entry must have a definition that could stand alone as an answer to "What is X?".
- Start with the most essential characterization (category + distinguishing feature).
- Include quantitative bounds when materials provide them (e.g. thresholds, ranges).
- Do not defer the definition to Scope or Related sections — the body text itself must define the concept.

## Structured Surface Promotion

When the material exposes a stable public surface such as a config file, route table, protocol definition, schedule, topology, or metric schema:
- Promote the reusable fact into a formal KB entry instead of leaving it buried in prose.
- Keep the canonical entry human-facing (`信使路由策略`, `旋涡协议消息类型`, `部署拓扑`), but preserve the stable artifact name as an alias when users may query it directly (`信使路由表`, `旋涡协议报文定义`, `deployment_topology.json`).
- Put quantitative facts that answer real operational questions in the first sentence when they are central: ranges, units, counts, periods, thresholds, or routing types.
- Do not keep the raw wrapper title as a competing formal entry when a clearer canonical subject is known; the wrapper should survive as alias / provenance, not as a second low-signal node.
- If a wrapper or section title is only supporting an existing canonical subject (`启明执行`, `潮涌处理流程`, `听风者周报模板`, `账房审计系统`), merge its facts back into the canonical entry instead of keeping a parallel shallow node.
- Report templates, scorecards, and ops tables must backfill canonical metric entries with quality criteria (`底噪`, `峰谷差`, `毛刺`, `覆盖率`, `达标率`) rather than producing generic nodes like `指标` or `核心指标`.

When the material exposes stable code or workflow surfaces:
- Promote exception families and failure taxonomies into formal entries (`谐振腔故障类型`, `旋涡协议异常处理`) instead of leaving them buried in class names.
- Promote TODO / not-yet-implemented notes into an auditable entry only when they describe real product gaps that operators or reviewers may query.
- Promote named procedures from headings, checklists, tables, and step lists into canonical bare-term entries or directly queryable procedure entries.
- Promote explicit symptom -> cause -> action chains into formal entries or high-signal `Scope` content, so later explore can answer diagnostic questions without reading raw source materials.
- Preserve stronger existing summaries during tidy; do not let generic bare-term backfills overwrite a more specific canonical definition that was already grounded in the KB.
- When multiple support lines mention the same canonical subject, keep the highest-signal ones in `Scope`: thresholds, trigger conditions, deployment locations, range boundaries, quality criteria, audit findings, and cross-document causal links should outrank generic first mentions.

## Fragment Rejection

Do not emit formal entries whose title is just a structural fragment or a generic workflow word.
- Reject titles like bare “建议”, “执行”, “以下”, “事件编号”, or sentence fragments led by pronouns.
- If a sentence is only supporting evidence for another concept, keep it in `Scope` instead of turning it into its own entry.

## Workflow

1. Read the source and identify reusable concepts, rules, and lessons.
2. Decide whether each candidate is a `concept`, `lesson`, or `placeholder`.
3. Write files using the v4 structure.
4. Add meaningful `[[Related]]` links to real KB concepts when possible.
5. Run validation:

```bash
python -m sediment.skills.explore.scripts.kb_query validate-entry "<KB_PATH>/entries/ENTRY_NAME.md"
uv run sediment kb health --json
```

`<KB_PATH>` means the knowledge base root resolved from the active
`config/sediment/config.yaml`.

If validation fails, the entry is not done.
