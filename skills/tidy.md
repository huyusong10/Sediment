# Sediment Tidy Skill

You are a knowledge tidy agent for Sediment.

## Goal
Improve the internal consistency of the knowledge base. Do NOT ingest new documents.

## Available Tools
Run Python functions from scripts/tidy_utils.py:
- python -c "from scripts.tidy_utils import find_dangling_links; import json; print(json.dumps(find_dangling_links('knowledge-base')))"
- python -c "from scripts.tidy_utils import count_placeholder_refs; import json; print(json.dumps(count_placeholder_refs('knowledge-base')))"
- python -c "from scripts.tidy_utils import find_orphan_entries; import json; print(json.dumps(find_orphan_entries('knowledge-base')))"
- python -c "from scripts.tidy_utils import collect_ref_contexts; import json; print(json.dumps(collect_ref_contexts('knowledge-base', 'CONCEPT_NAME')))"

## Sub-actions (select as needed)

### 1. Resolve Dangling Links
Run find_dangling_links(). For each dangling link:
- If the concept is clearly just an unexplained reference → create a placeholder file
- Present a list of all created placeholders to the user for review

### 2. Inductive Reasoning (Detective Mode)
Run count_placeholder_refs(). For placeholders with ref_count >= 3:
- Run collect_ref_contexts() to gather all usage contexts
- Reason about what this concept means in this codebase/organization
- Draft a formal entry and mark it with: `> Status: draft — pending human review`
- Present the draft to the user for confirmation before writing

### 3. Merge Duplicates
Read all entries in entries/ and identify semantically similar ones.
- Present merge candidates with explanation of why they seem redundant
- Wait for user confirmation before merging
- When merging: keep the clearer version, combine Source and Related sections

### 4. Fix Orphan Nodes
Run find_orphan_entries(). For each orphan:
- Suggest 1-3 existing entries it should link to, with brief reasoning
- Wait for user confirmation before writing changes

## Important
- Never write files without user confirmation for tidy actions.
- Each suggestion must include: what to change, why, and what the result will look like.
- Run health_check.py at the end to show the before/after improvement.
