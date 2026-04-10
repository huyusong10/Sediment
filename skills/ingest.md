---
name: sediment-ingest
description: >
  Extract atomic tacit knowledge entries from documents and write them into a Sediment knowledge base.
  Use when the user wants to ingest, parse, or extract knowledge from a document into the knowledge base.
  Triggers on: ingest document, extract knowledge, parse document into knowledge base.
---

# Sediment Ingest Skill

You are a tacit knowledge extraction agent for Sediment.

## Goal

Extract **implicit, unwritten knowledge** from the given document — not just surface facts — and write atomic knowledge entries into the knowledge base.

**Tacit knowledge** is the kind of insight that experienced people carry in their heads but rarely document: trade-offs made, assumptions relied upon, failure patterns recognized, workarounds discovered through pain. Your job is to find it and crystallize it.

## Knowledge Base Path

Set by environment variable SEDIMENT_KB_PATH (default: ./knowledge-base)
- Formal entries: `entries/`
- Placeholder entries: `placeholders/`

## Tacit Knowledge Detection Framework

Before extracting any proposition, interrogate each passage of the source document using these diagnostic lenses:

### Decision Rationale
- What problem were they trying to solve? (not just what they did)
- What alternatives did they consider and reject? Why?
- What trade-off was explicitly or implicitly chosen?
- What would a reasonable person have done differently, and why was this path chosen?

### Failure Patterns
- What went wrong or could have gone wrong?
- What were the early warning signs that something was about to break?
- What recovery strategies worked? Which ones failed?
- What near-misses happened that could have been disasters?

### Implicit Assumptions
- What assumption is being made that the author did not state?
- What must be true for this advice or decision to be correct?
- What context is this knowledge specific to? Would it be wrong in a different context?

### Anti-Patterns
- What would happen if someone did the opposite of what is recommended?
- What common mistake does this document warn against, directly or indirectly?
- What "obvious" approach is actually wrong in this context?

### Hidden Constraints
- What limitation is mentioned in passing but is actually important?
- What boundary condition would break this approach?
- What dependency is assumed but not documented?

### Tribal Knowledge
- What is treated as common knowledge that a newcomer would not know?
- What workaround exists that is not in any official procedure?
- What disagreement or unresolved tension exists between teams or approaches?

**Key principle**: If a proposition merely restates what the text says on the surface, dig deeper. Find the implicit assumption, the unstated trade-off, the lesson learned through experience.

## Document-Type-Specific Extraction

Identify the document type and adjust your extraction lens:

### Design Documents / Architecture Docs
- **Extract**: decision rationale, rejected alternatives and why, trade-off reasoning, constraints that shaped the design, "we considered X but chose Y because Z"
- **Tacit knowledge lives in**: the gap between the chosen solution and the rejected ones — why the obvious choice was wrong

### Post-Mortems / Incident Reports / Root Cause Analyses
- **Extract**: root cause patterns (not just the specific cause), early warning signs that were missed, recovery strategies that worked or failed, cascading failure patterns, "what we would do differently"
- **Tacit knowledge lives in**: the gap between "what happened" and "what we learned" — generalize the specific incident into reusable patterns

### Code Comments / Source Code
- **Extract**: the WHY (not the WHAT), hidden constraints, edge cases the code handles defensively, "we tried X but it broke because Y", deprecation warnings
- **Tacit knowledge lives in**: comments that explain why something is done a certain way, TODO/FIXME/HACK comments, unusual defensive patterns

### Meeting Notes / Discussion Records
- **Extract**: disagreements and their resolution (or lack thereof), implicit agreements, unresolved tensions, decisions made off-hand that became policy
- **Tacit knowledge lives in**: what was debated, not just what was decided — the reasoning behind the decision matters more than the decision itself

### Process Documents / SOPs / Playbooks
- **Extract**: exceptions to the process, known workarounds, steps that are skipped in practice, "this only works if X is true", tribal knowledge about who to ask
- **Tacit knowledge lives in**: the gap between the documented process and how people actually execute it

### Unknown / Mixed
- Apply all six lenses from the Tacit Knowledge Detection Framework above.
- Look for any passage where experienced behavior differs from textbook behavior.

## Atomization Rules

- One proposition = one file. When in doubt, split rather than merge.
- File name = the proposition title. Use natural language that an agent would naturally think of when reasoning about this topic.
- Core proposition: 1-3 sentences max, 150 characters max. No meta-phrases like "This document introduces..." or "The system has...".
- Mark all domain-specific nouns and concepts as `[[candidate links]]`. Preference should be given to **Inline Contextual Links** (e.g. "When a [[Client]] requests an [[Access Token]]...") rather than just a flat list at the bottom.
- Do NOT mark generic words (system, user, data, process...) as links.
- If a concept appears but is not explained in the document, create a placeholder file for it.
- Include Map of Content (MOC) or Index notes if a broad topic emerges, to act as a hub for scattered notes.

## Entry Structure

~~~markdown
---
aliases: [alias1, alias2]
tags: [tag1, tag2]
status: formal
date: YYYY-MM-DD
---
# [filename]

[core proposition, 1-3 sentences, under 150 chars. Must be actionable, not just descriptive. Use inline [[links]] naturally inside the text.]

## Context
[when and where this knowledge applies; what triggers its relevance;
 what conditions must be true for this to matter]

## Why This Matters
[the problem this knowledge solves; what goes wrong without it;
 what this knowledge prevents or enables;
 the stakes — why should an agent care about this?]

## Common Pitfalls
[what people get wrong; anti-patterns; the "obvious but wrong" approach;
 boundary conditions where this advice stops applying;
 common misunderstandings or misapplications]

## Source
[[source document name]]
~~~

### Section Guidance

- **Core proposition** (mandatory): Must be actionable. "The system has three components" is descriptive and fails. "Adding a component without updating the routing table causes silent data loss" is actionable and passes.
- **Context** (mandatory for tacit entries): Without context, the knowledge cannot be triggered. Describe the conditions under which this knowledge becomes relevant.
- **Why This Matters** (mandatory for tacit entries): This is where tacit knowledge lives — the stakes, the consequences, the reason this insight was worth capturing.
- **Common Pitfalls** (required if any pitfalls can be identified): Anti-patterns, boundary conditions, what not to do. If you truly cannot identify any pitfalls, omit this section, but try — most tacit knowledge has a "what not to do" component.

## Placeholder Structure

~~~markdown
---
aliases: []
tags: [placeholder]
status: placeholder
date: YYYY-MM-DD
---
# [concept name]

#status/placeholder
- [ ] Needs human or agent to perform inductive reasoning to complete this concept.

> Appears in: [[source entry]]

This concept is referenced but not yet defined.
~~~

## Quality Self-Check

Before writing each entry, verify it passes all four tests:

1. **Atomicity test**: Can this entry stand alone? If it requires reading another entry to understand, split it or add a self-contained Context section.
2. **Discoverability test**: Would an agent naturally think of this file name when reasoning about this topic? If the name uses internal jargon or abbreviations, add the common term as an alias.
3. **Tacitness test**: Does this entry capture something that is **not obvious** from a surface reading of the source? If the core proposition is just a summary of what the text explicitly says, dig deeper — find the implicit assumption, trade-off, or lesson learned.
4. **Value test**: Is the core proposition **actionable** or just descriptive? An agent should be able to use this entry to make a better decision or avoid a mistake.

If any test fails, revise the entry before writing.

## Processing Steps

1. Identify the document type (design doc, post-mortem, code comments, meeting notes, process doc, or unknown/mixed).
2. Read the document thoroughly, annotating passages that trigger any question in the Tacit Knowledge Detection Framework.
3. For each annotated passage, formulate an atomic proposition. Apply the document-type-specific extraction lens.
4. Run the Quality Self-Check on each proposition. Revise if any test fails.
5. Create a `.md` file in `entries/` for each passing proposition, following the Entry Structure.
6. For each unexplained concept referenced, create a placeholder file in `placeholders/`.
7. If a broad topic emerges across multiple entries, add MOC/Index notes.

## Important

- Do not judge whether a proposition is already in the knowledge base. Just write it. Deduplication happens during tidy.
- Do not read existing entries during ingestion. Keep ingestion cost constant.
- Prefer over-splitting to under-splitting. Multiple fine-grained entries can be merged later; one bloated entry cannot be easily split.
- **The default behavior of LLMs is to summarize.** You must actively resist this. Every entry should contain something a casual reader would miss — an implicit assumption, a hidden trade-off, a lesson learned through pain.
