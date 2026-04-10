---
name: sediment-explore
description: >
  Explore and query a Sediment knowledge base using knowledge_list and knowledge_read MCP tools.
  Use when the user wants to query, search, explore, or find information in the knowledge base.
  Triggers on: query knowledge base, explore knowledge, find information in knowledge base.
---

# Sediment Explore Skill

You have access to a complex knowledge base via these tools:
- `knowledge_list()`: returns all entry names (both formal entries and placeholders)
- `knowledge_read(filename)`: reads the full content of an entry

## Exploration Protocol

### Phase 1: Broad Scan

1. Call `knowledge_list()` to get all entry names.
2. Based on the question, reason about **5-10** semantically relevant entry names.
   File names are natural language — use your semantic understanding for fuzzy matching.
   Example: "interface permission control" semantically matches "clarify-permission-boundaries-before-api-design".
3. Call `knowledge_read()` on each candidate.
4. Classify each entry as: **highly relevant** / **tangentially relevant** / **irrelevant**.

### Phase 2: Deep Dive

5. For **highly relevant** entries: follow their `[[wikilinks]]` 2-3 levels deep.
   Each linked entry may reveal context you did not know to search for.
6. For **tangentially relevant** entries: read once, note any useful links, but do not go deep unless a linked concept seems directly relevant to the original question.
7. If the current keywords yield no results, **rephrase** and try different angles.
   Think about synonyms, related concepts, or the underlying problem the question is really about.

### Exploration Modes

Choose your approach based on the question type:

- **Question-driven** (for "how do I...", "why does...", "what should I do when..."):
  Start with the specific question, follow links that seem to answer it.
  Prioritize entries with strong "Why This Matters" and "Common Pitfalls" sections.

- **Keyword-driven** (for "tell me about X", "what do we know about Y"):
  Start with domain terms, explore broadly to understand the knowledge landscape.
  Use tags and aliases to find entries under different names.

- **Contradiction-seeking** (for "should we do X or Y?", "is A or B the right approach?"):
  Deliberately search for entries that support each side of the question.
  Pay special attention to entries with conflicting "Common Pitfalls" advice.

### When to Stop

- **Diminishing returns**: the last 3 entries you read added no new information to your understanding.
- **Saturation**: you have read all entries tagged with the relevant topic and followed all their links.
- **Answer confidence**: you can articulate a complete answer with sources and are confident nothing major is missing.

## Contradiction Handling

When you find entries that contradict each other:

1. **Do NOT silently pick one.** Report BOTH views with their full context.
2. Try to identify **WHY** they contradict:
   - **Different time periods?** Knowledge may have evolved — the older entry might be outdated.
   - **Different scope?** Advice for context A may not apply to context B.
   - **Different assumptions?** The entries may have different implicit premises.
   - **One is simply wrong?** Infer from source quality, recency, and supporting evidence.
3. Present the contradiction with your analysis of the likely cause.
4. If the contradiction cannot be resolved from the available entries, **flag it** in your output so the user knows to run tidy for resolution.

## Output Format

Return a structured JSON object:

```json
{
  "answer": "synthesized answer in natural language, incorporating insights from multiple entries",
  "sources": ["entry-name-1", "entry-name-2", "entry-name-3"],
  "confidence": "high | medium | low",
  "exploration_summary": {
    "entries_scanned": 42,
    "entries_read": 8,
    "links_followed": 5,
    "mode": "question-driven | keyword-driven | contradiction-seeking"
  },
  "gaps": ["topics that seem relevant to the question but have no entries"],
  "contradictions": [
    {
      "entries": ["entry-a", "entry-b"],
      "conflict": "brief description of the contradiction",
      "analysis": "likely reason for the conflict, or 'unresolved'"
    }
  ]
}
```

## Notes

- **Placeholder entries** (`status: placeholder`) mean the concept exists but is not fully defined. They tell you "people talk about this but haven't formalized the knowledge." Use with caution — the concept is real but the details are missing.
- **`[[Related]]` links are exploration leads** — always go at least 2 levels deep before concluding nothing is relevant. The most valuable insights often live in entries you did not know to search for.
- **If you find contradictory entries**, report the contradiction rather than silently picking one. Analyze the likely cause (different context, different time, different assumptions) and flag for tidy if unresolved.
- **Confidence levels**: "high" means you read all obviously relevant entries and their links. "medium" means you found good coverage but suspect there may be more. "low" means the knowledge base seems sparse on this topic.
