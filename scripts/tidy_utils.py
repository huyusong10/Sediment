"""
Tidy utility functions for Sediment knowledge base maintenance.

All functions are stateless and compute results from the filesystem on every call.
"""

import os
import re
from pathlib import Path


def _scan_md_files(kb_path: str) -> dict[str, str]:
    """
    Scan entries/ and placeholders/ directories for .md files.
    Returns a dict mapping filename (without .md) to relative path.
    """
    result = {}
    for subdir in ("entries", "placeholders"):
        dir_path = Path(kb_path) / subdir
        if not dir_path.exists():
            continue
        for f in dir_path.glob("*.md"):
            result[f.stem] = f"{subdir}/{f.name}"
    return result


def _extract_links(content: str) -> list[str]:
    """Extract all [[link]] targets from markdown content."""
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def find_dangling_links(kb_path: str) -> list[dict]:
    """
    Scan all .md files in entries/ and placeholders/ for [[links]].
    Return links whose target files do not exist.
    """
    all_files = _scan_md_files(kb_path)
    dangling = []

    for name, rel_path in all_files.items():
        full_path = Path(kb_path) / rel_path
        content = full_path.read_text(encoding="utf-8")
        links = _extract_links(content)

        for link in links:
            # Check if the link target exists in entries/ or placeholders/
            target_entries = Path(kb_path) / "entries" / f"{link}.md"
            target_placeholders = Path(kb_path) / "placeholders" / f"{link}.md"
            if not target_entries.exists() and not target_placeholders.exists():
                # Find the context line
                for line in content.splitlines():
                    if f"[[{link}]]" in line:
                        dangling.append(
                            {
                                "link": link,
                                "source_file": rel_path,
                                "context": line.strip(),
                            }
                        )
                        break

    return dangling


def count_placeholder_refs(kb_path: str) -> list[dict]:
    """
    Count how many times each placeholder file is referenced.
    A reference = [[filename]] appearing in any .md file in entries/ or placeholders/.
    """
    all_files = _scan_md_files(kb_path)
    placeholder_files = {
        name: rel_path
        for name, rel_path in all_files.items()
        if rel_path.startswith("placeholders/")
    }

    # Initialize counts
    placeholder_data = {}
    for name in placeholder_files:
        placeholder_data[name] = {
            "placeholder": name,
            "ref_count": 0,
            "referenced_by": [],
        }

    # Scan all files for references
    for name, rel_path in all_files.items():
        full_path = Path(kb_path) / rel_path
        content = full_path.read_text(encoding="utf-8")
        links = _extract_links(content)

        for link in links:
            if link in placeholder_data:
                placeholder_data[link]["ref_count"] += 1
                placeholder_data[link]["referenced_by"].append(rel_path)

    # Sort by ref_count descending
    result = sorted(
        placeholder_data.values(),
        key=lambda x: x["ref_count"],
        reverse=True,
    )
    return result


def find_orphan_entries(kb_path: str) -> list[str]:
    """
    Detect entries in entries/ that have no inbound links and no outbound links.
    """
    all_files = _scan_md_files(kb_path)
    entry_files = {
        name: rel_path
        for name, rel_path in all_files.items()
        if rel_path.startswith("entries/")
    }

    # Build sets of outbound and inbound links
    has_outbound = set()
    inbound_counts = {}  # name -> count of files linking to it

    for name, rel_path in all_files.items():
        full_path = Path(kb_path) / rel_path
        content = full_path.read_text(encoding="utf-8")
        links = _extract_links(content)

        if links and name in entry_files:
            has_outbound.add(name)

        for link in links:
            if link in entry_files:
                inbound_counts[link] = inbound_counts.get(link, 0) + 1

    orphans = []
    for name, rel_path in entry_files.items():
        has_inbound = name in inbound_counts
        has_out = name in has_outbound
        if not has_inbound and not has_out:
            orphans.append(rel_path)

    return orphans


def collect_ref_contexts(kb_path: str, placeholder_name: str) -> list[str]:
    """
    Collect context snippets where a placeholder concept is referenced across entries.
    Returns list of formatted context strings with surrounding lines.
    """
    all_files = _scan_md_files(kb_path)
    results = []

    for name, rel_path in all_files.items():
        full_path = Path(kb_path) / rel_path
        lines = full_path.read_text(encoding="utf-8").splitlines()

        for i, line in enumerate(lines):
            if f"[[{placeholder_name}]]" in line:
                # Collect context: the line itself plus up to 3 lines before and after
                start = max(0, i - 3)
                end = min(len(lines), i + 4)
                context_lines = lines[start:end]
                context = "\n".join(context_lines)
                results.append(f"来源：{rel_path}\n上下文：{context}")

    return results
