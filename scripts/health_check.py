#!/usr/bin/env python3
"""
health_check.py — Sediment Knowledge Base diagnostic report.

Usage: python scripts/health_check.py <kb_path>
"""

import sys
from datetime import datetime
from pathlib import Path

# Allow running from the repo root: python scripts/health_check.py knowledge-base
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.tidy_utils import (
    find_dangling_links,
    count_placeholder_refs,
    find_orphan_entries,
)


def run_health_check(kb_path: str) -> None:
    root = Path(kb_path)

    # Count entries and placeholders
    entries_dir = root / 'entries'
    placeholders_dir = root / 'placeholders'

    entry_files = list(entries_dir.glob('*.md')) if entries_dir.is_dir() else []
    placeholder_files = list(placeholders_dir.glob('*.md')) if placeholders_dir.is_dir() else []

    # Exclude .gitkeep
    entry_files = [f for f in entry_files if f.name != '.gitkeep']
    placeholder_files = [f for f in placeholder_files if f.name != '.gitkeep']

    total_entries = len(entry_files)
    total_placeholders = len(placeholder_files)
    total = total_entries + total_placeholders

    # Compute indicators
    placeholder_refs = count_placeholder_refs(kb_path)
    orphans = find_orphan_entries(kb_path)
    dangling = find_dangling_links(kb_path)

    # Categorise placeholder refs
    high = [p for p in placeholder_refs if p['ref_count'] >= 5]
    medium = [p for p in placeholder_refs if 2 <= p['ref_count'] <= 4]
    low = [p for p in placeholder_refs if p['ref_count'] == 1]

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # ------------------------------------------------------------------ output
    print('Sediment Knowledge Base — Health Report')
    print('========================================')
    print(f'Generated: {now}')
    print()
    print('SUMMARY')
    print('-------')
    print(f'Total entries:       {total}  (formal: {total_entries}, placeholders: {total_placeholders})')
    print()
    print('PLACEHOLDER REFS')
    print('----------------')
    print(f'High (>=5):    {len(high)}')
    print(f'Medium (2-4):  {len(medium)}')
    for p in medium:
        print(f'  - {p["placeholder"]} ({p["ref_count"]} refs)')
    print(f'Low (1):       {len(low)}')
    print()
    print('ORPHAN ENTRIES')
    print('--------------')
    print(f'Count: {len(orphans)}')
    if orphans:
        for o in orphans:
            print(f'  - {o}')
    print()
    print('DANGLING LINKS')
    print('--------------')
    print(f'Count: {len(dangling)}')
    if dangling:
        for d in dangling:
            print(f'  - [{d["link"]}] in {d["source_file"]}')
    print()
    print('RECOMMENDATION')
    print('--------------')

    recommendations = []
    if high:
        recommendations.append(
            f'Run tidy with induction mode. Focus on {len(high)} high-ref placeholder(s).'
        )
    if orphans:
        recommendations.append(
            f'Run tidy to add missing links for {len(orphans)} orphan entr{"y" if len(orphans) == 1 else "ies"}.'
        )
    if dangling:
        recommendations.append(
            f'Run tidy to resolve {len(dangling)} dangling link(s).'
        )

    if recommendations:
        for rec in recommendations:
            print(rec)
    else:
        print('Knowledge base looks healthy. Consider ingesting more documents.')


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python scripts/health_check.py <kb_path>', file=sys.stderr)
        sys.exit(1)

    kb_path = sys.argv[1]
    if not Path(kb_path).is_dir():
        print(f'ERROR: {kb_path!r} is not a directory.', file=sys.stderr)
        sys.exit(1)

    run_health_check(kb_path)


if __name__ == '__main__':
    main()
