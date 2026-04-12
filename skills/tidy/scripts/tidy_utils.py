"""
tidy_utils.py — Stateless helper functions for Sediment knowledge base analysis.

All functions read directly from the filesystem on every call — no caching.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$")
PROVENANCE_HEADINGS = {"Source"}
PROVENANCE_LINE_PREFIXES = (
    "> Appears in:",
    "> Referenced in:",
    "Appears in:",
    "Referenced in:",
)
SECTION_ALIASES = {
    "source": "Source",
    "来源": "Source",
    "related": "Related",
    "相关": "Related",
    "scope": "Scope",
    "context": "Scope",
    "上下文": "Scope",
    "trigger": "Trigger",
    "触发": "Trigger",
    "when to apply": "Trigger",
    "why": "Why",
    "why this matters": "Why",
    "evidence / reasoning": "Why",
    "evidence/reasoning": "Why",
    "risks": "Risks",
    "common pitfalls": "Risks",
    "风险": "Risks",
}


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not match:
        return {}, text
    payload = yaml.safe_load(match.group(1)) or {}
    if not isinstance(payload, dict):
        payload = {}
    return payload, text[match.end() :]


def normalize_section_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip()
    if not cleaned:
        return cleaned
    return SECTION_ALIASES.get(cleaned.casefold(), cleaned)


def split_sections(body: str) -> tuple[dict[str, str], str]:
    current = "__preamble__"
    buckets: dict[str, list[str]] = defaultdict(list)
    for line in body.splitlines():
        heading = HEADING_PATTERN.match(line.strip())
        if heading:
            current = normalize_section_name(heading.group(1))
            continue
        buckets[current].append(line)

    preamble = "\n".join(buckets.pop("__preamble__", [])).strip()
    sections = {name: "\n".join(lines).strip() for name, lines in buckets.items()}
    return sections, preamble


def extract_wikilinks(text: str) -> list[str]:
    links = []
    for raw in LINK_PATTERN.findall(text):
        target = raw.split("|")[0].split("#")[0].strip()
        if target:
            links.append(target)
    return list(dict.fromkeys(links))


def _graph_relevant_lines(text: str, *, kind: str) -> list[str]:
    """Return only the lines that should participate in the KB graph."""
    _, body = split_frontmatter(text)
    lines: list[str] = []
    current_section = None

    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        heading = HEADING_PATTERN.match(stripped)
        if heading:
            current_section = normalize_section_name(heading.group(1))
            if current_section in PROVENANCE_HEADINGS:
                continue
            lines.append(raw_line)
            continue

        if current_section in PROVENANCE_HEADINGS:
            continue

        if kind == "placeholder" and any(
            stripped.startswith(prefix) for prefix in PROVENANCE_LINE_PREFIXES
        ):
            continue

        lines.append(raw_line)

    return lines


def graph_relevant_text(text: str, *, kind: str) -> str:
    return "\n".join(_graph_relevant_lines(text, kind=kind))


def graph_links_from_text(text: str, *, kind: str) -> list[str]:
    """Extract graph links while ignoring provenance-only surfaces."""
    return extract_wikilinks(graph_relevant_text(text, kind=kind))


def _get_all_md_files(kb_path: str) -> list[Path]:
    """Return all .md files under entries/ and placeholders/."""
    root = Path(kb_path)
    files = []
    for subdir in ("entries", "placeholders"):
        current = root / subdir
        if current.is_dir():
            files.extend(current.glob("*.md"))
    return files


def _file_exists_in_kb(kb_path: str, name: str) -> bool:
    """Check if a named entry exists in either entries/ or placeholders/."""
    root = Path(kb_path)
    return (
        (root / "entries" / f"{name}.md").exists()
        or (root / "placeholders" / f"{name}.md").exists()
    )


def find_dangling_links(kb_path: str) -> list[dict]:
    """
    扫描 entries/ 和 placeholders/ 下所有 .md 文件中的 [[链接]]。
    返回目标文件不存在的链接列表。
    """
    root = Path(kb_path)
    results = []

    for md_file in _get_all_md_files(kb_path):
        kind = "placeholder" if md_file.parent.name == "placeholders" else "formal"
        try:
            rel = md_file.relative_to(root)
        except ValueError:
            rel = md_file

        lines = _graph_relevant_lines(md_file.read_text(encoding="utf-8"), kind=kind)
        for line in lines:
            for target in extract_wikilinks(line):
                if not _file_exists_in_kb(kb_path, target):
                    results.append(
                        {
                            "link": target,
                            "source_file": str(rel),
                            "context": line.strip(),
                        }
                    )

    return results


def count_placeholder_refs(kb_path: str) -> list[dict]:
    """
    统计 placeholders/ 下每个占位文件被引用的次数。
    被引用 = 在 entries/ 或 placeholders/ 的任意 .md 文件中出现 [[文件名]]。
    """
    root = Path(kb_path)
    placeholders_dir = root / "placeholders"

    if not placeholders_dir.is_dir():
        return []

    placeholder_names = [path.stem for path in placeholders_dir.glob("*.md")]
    ref_map: dict[str, list[str]] = {name: [] for name in placeholder_names}

    for md_file in _get_all_md_files(kb_path):
        kind = "placeholder" if md_file.parent.name == "placeholders" else "formal"
        try:
            rel = str(md_file.relative_to(root))
        except ValueError:
            rel = str(md_file)

        content = md_file.read_text(encoding="utf-8")
        for target in graph_links_from_text(content, kind=kind):
            if target in ref_map:
                ref_map[target].append(rel)

    results = [
        {
            "placeholder": name,
            "ref_count": len(files),
            "referenced_by": files,
        }
        for name, files in ref_map.items()
    ]
    results.sort(key=lambda item: item["ref_count"], reverse=True)
    return results


def find_orphan_entries(kb_path: str) -> list[str]:
    """
    检测 entries/ 下没有任何入链且没有出链的条目。
    """
    root = Path(kb_path)
    entries_dir = root / "entries"

    if not entries_dir.is_dir():
        return []

    file_outlinks: dict[str, set[str]] = {}
    for md_file in _get_all_md_files(kb_path):
        kind = "placeholder" if md_file.parent.name == "placeholders" else "formal"
        content = md_file.read_text(encoding="utf-8")
        links = set(graph_links_from_text(content, kind=kind))
        try:
            rel = str(md_file.relative_to(root))
        except ValueError:
            rel = str(md_file)
        file_outlinks[rel] = links

    orphans = []
    for entry_file in entries_dir.glob("*.md"):
        try:
            rel = str(entry_file.relative_to(root))
        except ValueError:
            rel = str(entry_file)

        name = entry_file.stem
        has_outlinks = bool(file_outlinks.get(rel))
        has_inlinks = any(
            name in links for file_rel, links in file_outlinks.items() if file_rel != rel
        )
        if not has_outlinks and not has_inlinks:
            orphans.append(rel)

    return sorted(orphans)


def collect_ref_contexts(kb_path: str, placeholder_name: str) -> list[str]:
    """
    收集指定占位概念在所有条目中被引用的上下文片段。
    只保留知识正文，不包含 provenance 区域。
    """
    root = Path(kb_path)
    results = []
    target_pattern = re.compile(r"\[\[" + re.escape(placeholder_name) + r"(?:[|#][^\]]*)?\]\]")

    for md_file in _get_all_md_files(kb_path):
        kind = "placeholder" if md_file.parent.name == "placeholders" else "formal"
        filtered_lines = _graph_relevant_lines(md_file.read_text(encoding="utf-8"), kind=kind)

        try:
            rel = str(md_file.relative_to(root))
        except ValueError:
            rel = str(md_file)

        for index, line in enumerate(filtered_lines):
            if not target_pattern.search(line):
                continue
            start = max(0, index - 3)
            end = min(len(filtered_lines), index + 4)
            context = "\n".join(filtered_lines[start:end])
            results.append(f"来源：{rel}\n上下文：\n{context}")

    return results
