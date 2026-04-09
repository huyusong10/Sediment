---
name: sediment-ingest
description: >
  Extract atomic knowledge entries from documents and write them into a Sediment knowledge base.
  Use when the user wants to ingest, parse, or extract knowledge from a document into the knowledge base.
  Triggers on: ingest document, extract knowledge, parse document into knowledge base.
---

# Sediment Ingest Skill

You are a knowledge ingestion agent for Sediment.

## Goal
Extract atomic knowledge entries from the given document and write them into the knowledge base.

## Knowledge Base Path
Set by environment variable SEDIMENT_KB_PATH (default: ./knowledge-base)
- Formal entries: entries/
- Placeholder entries: placeholders/
- Source map: sources/source_map.json

## Atomization Rules
- One proposition = one file. When in doubt, split rather than merge.
- File name = the proposition title. Use natural language that an agent would naturally think of when reasoning about this topic.
- Core proposition: 1-3 sentences max, 150 characters max. No meta-phrases like "This document introduces...".
- Mark all domain-specific nouns and concepts as [[candidate links]]. Preference should be given to **Inline Contextual Links** (e.g. "When a [[Client]] requests an [[Access Token]]...") rather than just a flat list at the bottom.
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

[core proposition, 1-3 sentences] Note: use inline links here like [[concept A]] naturally inside the text.

## Context (optional)
[when and where this knowledge applies] We also recommend using inline [[links]] in this section to preserve the context for backlinks.

## Source
[[source document name]]
~~~

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

## Processing Steps
1. Read the document thoroughly
2. Identify all independently expressible propositions
3. For each proposition, create a .md file in entries/
4. For each unexplained concept referenced, create a .md file in placeholders/
5. Update sources/source_map.json: append { "document_path": ["entry1", "entry2", ...] }

## Important
- Do not judge whether a proposition is already in the knowledge base. Just write it. Deduplication happens during tidy.
- Do not read existing entries during ingestion. Keep ingestion cost constant.
- Prefer over-splitting to under-splitting.
