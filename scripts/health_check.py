#!/usr/bin/env python3
"""
Health check script for Sediment knowledge base.

Usage: python scripts/health_check.py <kb_path>
"""

import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for importing tidy_utils
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from scripts.tidy_utils import (
    find_dangling_links,
    count_placeholder_refs,
    find_orphan_entries,
)


def count_entries(kb_path: str) -> tuple[int, int, int]:
    """
    Count total entries, formal entries, and placeholders.
    Returns (total, formal_count, placeholder_count).
    """
    formal = 0
    placeholder = 0
    for subdir in ("entries", "placeholders"):
        dir_path = Path(kb_path) / subdir
        if not dir_path.exists():
            continue
        count = len(list(dir_path.glob("*.md")))
        if subdir == "entries":
            formal = count
        else:
            placeholder = count
    return formal + placeholder, formal, placeholder


def generate_recommendation(
    dangling_count: int,
    orphan_count: int,
    high_ref_placeholders: list,
    medium_ref_placeholders: list,
    low_ref_placeholders: list,
) -> str:
    """Generate recommendation based on health metrics."""
    parts = []

    if high_ref_placeholders:
        count = len(high_ref_placeholders)
        parts.append(
            f"Run tidy with induction mode. Focus on {count} high-ref placeholder(s)."
        )
    if orphan_count > 0:
        parts.append(
            f"Run tidy to add missing links for {orphan_count} orphan entries."
        )
    if dangling_count > 0:
        parts.append(f"Run tidy to resolve {dangling_count} dangling link(s).")

    if not parts:
        return "Knowledge base looks healthy. Consider ingesting more documents."

    return " ".join(parts)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/health_check.py <kb_path>")
        sys.exit(1)

    kb_path = sys.argv[1]

    # Gather metrics
    total, formal, placeholders = count_entries(kb_path)
    dangling = find_dangling_links(kb_path)
    placeholder_refs = count_placeholder_refs(kb_path)
    orphans = find_orphan_entries(kb_path)

    # Categorize placeholder refs
    high_ref = [p for p in placeholder_refs if p["ref_count"] >= 5]
    medium_ref = [p for p in placeholder_refs if 2 <= p["ref_count"] <= 4]
    low_ref = [p for p in placeholder_refs if p["ref_count"] == 1]

    # Generate recommendation
    recommendation = generate_recommendation(
        len(dangling),
        len(orphans),
        high_ref,
        medium_ref,
        low_ref,
    )

    # Print report
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("Sediment Knowledge Base — Health Report")
    print("=" * 40)
    print(f"Generated: {now}")
    print()
    print("SUMMARY")
    print("-" * 7)
    print(
        f"Total entries:       {total}  (formal: {formal}, placeholders: {placeholders})"
    )
    print()
    print("PLACEHOLDER REFS")
    print("-" * 16)
    print(f"High (>=5):    {len(high_ref)}")
    print(f"Medium (2-4):  {len(medium_ref)}")
    for p in medium_ref:
        print(f"  - {p['placeholder']} ({p['ref_count']} refs)")
    print(f"Low (1):       {len(low_ref)}")
    for p in low_ref:
        print(f"  - {p['placeholder']} ({p['ref_count']} refs)")
    print()
    print("ORPHAN ENTRIES")
    print("-" * 14)
    print(f"Count: {len(orphans)}")
    print()
    print("DANGLING LINKS")
    print("-" * 14)
    print(f"Count: {len(dangling)}")
    print()
    print("RECOMMENDATION")
    print("-" * 14)
    print(recommendation)


if __name__ == "__main__":
    main()
