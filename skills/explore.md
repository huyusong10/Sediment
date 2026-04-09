---
name: sediment-explore
description: >
  Explore and query a Sediment knowledge base using knowledge_list and knowledge_read MCP tools.
  Use when the user wants to query, search, explore, or find information in the knowledge base.
  Triggers on: query knowledge base, explore knowledge, find information in knowledge base.
---

# Sediment Explore Skill

You have access to a complex knowledge base via these tools:
- knowledge_list(): returns all entry names
- knowledge_read(filename): reads the full content of an entry

## Exploration Protocol

1. Call knowledge_list() to get all entry names.
2. Based on the question, reason about 2-5 semantically relevant entry names.
   File names are natural language — use semantic understanding for fuzzy matching.
   Example: "interface permission control" semantically matches "clarify-permission-boundaries-before-api-design".
3. Call knowledge_read() on each candidate.
4. Assess relevance. If relevant, look at the [[Related]] section and continue reading linked concepts.
5. If the current keywords yield no results, rephrase and try different angles.
6. Synthesize all relevant entries into a complete answer.
   Always list the source entry names you drew from.

## Output Format (for knowledge_ask)
Return a JSON object:
{
  "answer": "synthesized answer in natural language",
  "sources": ["entry-name-1", "entry-name-2"]
}

## Notes
- Placeholder entries (Status: placeholder) mean the concept exists but is not fully defined. Use with caution.
- [[Related]] links are exploration leads — always go at least 2 levels deep before concluding nothing is relevant.
- If you find contradictory entries, report the contradiction rather than silently picking one.
