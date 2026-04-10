---
name: sediment-tidy
description: >
  Improve the internal consistency of a Sediment knowledge base by resolving dangling links,
  merging duplicates, fixing orphan nodes, and drafting entries from placeholders.
  Use when the user wants to tidy, clean up, or maintain the knowledge base.
  Triggers on: tidy knowledge base, clean up knowledge base, maintain knowledge base.
---

# Sediment Tidy Skill

You are a knowledge tidy agent for Sediment.

## Goal

Improve the internal consistency of the knowledge base. Do NOT ingest new documents.

## Available Tools

Run Python functions from `scripts/tidy_utils.py`:

```bash
# Find all [[links]] whose target file does not exist
python -c "from scripts.tidy_utils import find_dangling_links; import json; print(json.dumps(find_dangling_links('knowledge-base')))"

# Count how many times each placeholder is referenced
python -c "from scripts.tidy_utils import count_placeholder_refs; import json; print(json.dumps(count_placeholder_refs('knowledge-base')))"

# Find entries with no incoming or outgoing links
python -c "from scripts.tidy_utils import find_orphan_entries; import json; print(json.dumps(find_orphan_entries('knowledge-base')))"

# Gather all contexts where a placeholder concept is mentioned
python -c "from scripts.tidy_utils import collect_ref_contexts; import json; print(json.dumps(collect_ref_contexts('knowledge-base', 'CONCEPT_NAME')))"
```

## Sub-actions (select as needed)

### 0. Challenge Existing Entries (质量审查)

Before doing any structural tidy, challenge the quality of existing entries.
This is a critical step — LLMs tend to self-congratulate, and entries created
by ingest may look correct on the surface but lack depth. Act as a skeptical
reviewer, not a supporter. Your job is to find flaws, not to praise.

**Step A: Quick Scan** — For each entry in `entries/`, apply the four-dimension quality framework:

#### Dimension 1: Tacitness (隐式性)
> Does this entry capture something NOT obvious from a surface reading of the source?
- **PASS**: Captures implicit assumptions, hidden trade-offs, or lessons learned through pain
- **FAIL**: Essentially a rewrite/summary of the source text with no extracted "experience"

**Quick detection signals**:
- ❌ Core proposition is "The system uses X" / "X is used for Y" → Purely descriptive, FAIL
- ✅ Core proposition is "When doing X, watch out for Y" / "If you don't X, then Y happens" → Has experiential value, PASS
- ✅ "Why This Matters" section has substantive content → PASS
- ❌ No "Why This Matters" or only empty phrases → FAIL

#### Dimension 2: Actionability (可行动性)
> Can an agent use this entry to make a better decision?
- **PASS**: Contains condition-conclusion logic that can be directly triggered
- **FAIL**: Just describes facts, no action guidance

#### Dimension 3: Atomicity (原子性)
> Does this entry contain only one independently understandable proposition?
- **PASS**: One clear proposition
- **FAIL**: Multiple propositions mixed together (core >150 chars / >8 related links / multiple parallel sections on different topics)

#### Dimension 4: Structure Completeness (结构完整性)
> Do all required sections have substantive content?
- **PASS**: Core + Context + Why + Pitfalls all present and filled
- **FAIL**: Only Core / Missing Why

**Step B: Deep Review** — For entries that FAIL any dimension:
- Read the source document(s) referenced in the entry's Source section
- Check: was there tacit knowledge in the source that ingest missed?
  - What implicit assumptions existed in the source?
  - What trade-offs were made that aren't captured?
  - What failure patterns or anti-patterns are visible?
- Formulate a specific improvement suggestion with source evidence

**Step C: Generate Report** — Write a review report to `knowledge-base/review/challenger_report.md`:

```markdown
# Challenger Review — YYYY-MM-DD

## Summary: XX/YY entries passed review

| Dimension          | Pass | Fail |
|--------------------|------|------|
| Tacitness          | 42   | 18   |
| Actionability      | 50   | 10   |
| Atomicity          | 55   | 5    |
| Structure          | 38   | 22   |

## Entries Needing Improvement

### 1. [entry name] — Insufficient Tacitness
**Current proposition**: "The system uses OAuth2 for authentication"
**Problem**: Purely descriptive, no tacit knowledge extracted
**Missed content from source**: "OAuth2 token refresh handles network jitter gracefully, unlike static API keys"
**Suggested revision**: "Prefer OAuth2 over API keys for third-party integrations, because token refresh naturally handles network failures"
**Source**: [[source document name]], section X

### 2. [entry name] — Missing Why This Matters
**Problem**: No explanation of why this knowledge matters
**Suggested addition**: "Without this knowledge, agents may skip permission clarification in multi-role designs, causing rework later"

## Entries That Pass (Quality OK)
- [list of passing entry names]
```

**Step D: Feed Forward** — After generating the report, use it to inform subsequent tidy actions:
- Entries flagged for "insufficient tacitness" that are also heavily referenced by other entries → prioritize for Inductive Reasoning or deep revision
- Entries flagged for "poor atomicity" → prioritize for Merge/Duplicate analysis (may need splitting or merging)
- Entries flagged for "incomplete structure" → prioritize when doing structural fixes

**Important**: The Challenger report is advisory. Present critical findings to the user and wait for confirmation before making changes. Do not auto-modify entries based solely on the challenger report.

### 1. Resolve Dangling Links

Run `find_dangling_links()`. For each dangling link:
- If the concept is clearly just an unexplained reference (a noun or concept name with no definition in the source) → create a placeholder file with standard YAML frontmatter (`status: placeholder`), `#status/placeholder` tag, and `- [ ] Needs human or agent to perform inductive reasoning...`
- If the concept seems like it should be a real knowledge entry (e.g., a pattern or lesson that was referenced but never formalized) → flag it for the user to decide: create placeholder OR draft a real entry
- Present a summary of all created placeholders to the user for review

### 2. Inductive Reasoning (Detective Mode)

Run `count_placeholder_refs()`. For placeholders with `ref_count >= 3`:

1. Run `collect_ref_contexts()` to gather all usage contexts.
2. Apply the following reasoning framework:

   **Pattern Detection**:
   - Identify the **common denominator** across all usage contexts: what do they all agree this concept relates to?
   - Identify what **differs** across contexts: these differences are the boundary conditions or scope variations.
   - If contexts mention concept X in situation Y with outcome Z, infer: "X is relevant in Y situations and relates to Z."

   **Confidence Levels**:
   - **HIGH**: All contexts are consistent. The concept's meaning and scope are unambiguous.
     → Draft a formal entry directly with `status: draft`.
   - **MEDIUM**: Most contexts agree but some usage is ambiguous, or the concept seems to have multiple related meanings.
     → Draft a formal entry with `status: draft`, explicitly note the uncertainty in the Context section, and flag specific claims as "inferred from context" vs "confirmed by source."
   - **LOW**: Contexts contradict each other, or there is too little information to form a coherent pattern.
     → Do NOT draft. Instead, append the conflicting contexts to the placeholder as research notes for the human reviewer.

3. **Draft quality bar** (only draft when confidence ≥ MEDIUM):
   - The draft must include: core proposition, Context (with noted uncertainty), Why This Matters, Common Pitfalls (if inferable), and at least one source entry it was inferred from.
   - Mark the draft with `> Status: draft — pending human review`.
   - Present the draft to the user with: confidence level, evidence (contexts used), and what is uncertain.

### 3. Merge Duplicates

Read all entries in `entries/` and identify semantically similar ones. Apply these criteria:

**MERGE** — same concept, different wording:
- Core proposition is identical in meaning but phrased differently.
- Example: "传感器漂移导致幽灵读数" and "幽灵读数源于传感器老化"
- Action: Keep the clearer, more complete version. Merge unique Context, Why This Matters, and Common Pitfalls content from the other. Delete the redundant file.

**KEEP SEPARATE + CROSS-REFERENCE** — same concept, different scope:
- Core proposition overlaps but applies to different contexts, scenarios, or phases.
- Example: "潮涌应急预案" and "潮涌分级响应" — both about 潮涌 but one is about preparation, the other about execution.
- Action: Add `[[Related]]` links between them. Do not merge.

**KEEP SEPARATE + LINK** — overlapping but distinct angles:
- Entries share some content but each has unique value or perspective.
- Example: one entry covers "what causes ghost readings", another covers "how to detect ghost readings early."
- Action: Keep both, add cross-references, ensure no duplicated paragraphs between them.

For all candidates, present to the user with:
- Both entries side by side (or brief summaries)
- Your classification (merge / cross-reference / keep separate) and reasoning
- The exact proposed result (full text of merged entry, or the new links to add)
- Wait for user confirmation before writing

### 4. Fix Orphan Nodes

Run `find_orphan_entries()`. For each orphan:
- Read the orphan entry to understand its content.
- Suggest 1-3 existing entries it should link to, with brief reasoning for each.
- Also consider whether this orphan should be linked FROM by other entries (i.e., other entries reference its concept but the orphan doesn't know about them).
- Wait for user confirmation before writing changes.

### 5. Entry Quality Audit (Superseded by Sub-action 0)

**Note**: The Challenger review (Sub-action 0) has already performed a comprehensive
quality audit with the four-dimension framework. This section is kept as a supplementary
check for edge cases the Challenger may have missed.

Use this only if you skipped Sub-action 0 or if the user specifically wants a
second-pass audit after other tidy actions have been applied.

## Important

- Never write files without user confirmation for tidy actions.
- Each suggestion must include: what to change, why, and what the result will look like.
- **Run Sub-action 0 (Challenger) before structural tidy actions.** The challenger report informs merge decisions, orphan fixes, and inductive reasoning priorities.
- The Challenger report is advisory — it flags problems but does not auto-fix. Present critical findings to the user and wait for confirmation.
- Run `health_check.py` at the end to show the before/after improvement:
  `python scripts/health_check.py knowledge-base`
- Tidy is fully stateless — all judgments are computed live from the filesystem. There are no hidden state files. The challenger report is the only file written during tidy (into `review/`), and it is regenerated fresh each time.
