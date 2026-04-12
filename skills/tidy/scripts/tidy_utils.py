"""
tidy_utils.py — Stateless helper functions for Sediment knowledge base analysis.

The real parsing and graph semantics live in ``mcp_server.kb`` so every runtime
surface shares the same interpretation of entries, provenance, and links.
"""

from __future__ import annotations

from mcp_server.kb import (
    collect_ref_contexts,
    count_placeholder_refs,
    extract_wikilinks,
    find_dangling_links,
    find_orphan_entries,
    graph_links_from_text,
    graph_relevant_text,
    normalize_section_name,
    split_frontmatter,
    split_sections,
)

__all__ = [
    "collect_ref_contexts",
    "count_placeholder_refs",
    "extract_wikilinks",
    "find_dangling_links",
    "find_orphan_entries",
    "graph_links_from_text",
    "graph_relevant_text",
    "normalize_section_name",
    "split_frontmatter",
    "split_sections",
]
