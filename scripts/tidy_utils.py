"""
tidy_utils.py — Stateless helper functions for Sediment knowledge base analysis.

All functions read directly from the filesystem on every call — no caching.
"""

import re
from pathlib import Path


_LINK_PATTERN = re.compile(r'\[\[([^\]]+)\]\]')


def _get_all_md_files(kb_path: str) -> list[Path]:
    """Return all .md files under entries/ and placeholders/."""
    root = Path(kb_path)
    files = []
    for subdir in ('entries', 'placeholders'):
        d = root / subdir
        if d.is_dir():
            files.extend(d.glob('*.md'))
    return files


def _get_entry_name(p: Path) -> str:
    """Return the stem (filename without .md) of a Path."""
    return p.stem


def _file_exists_in_kb(kb_path: str, name: str) -> bool:
    """Check if a named entry exists in either entries/ or placeholders/."""
    root = Path(kb_path)
    return (
        (root / 'entries' / f'{name}.md').exists()
        or (root / 'placeholders' / f'{name}.md').exists()
    )


def find_dangling_links(kb_path: str) -> list[dict]:
    """
    扫描 entries/ 和 placeholders/ 下所有 .md 文件中的 [[链接]]。
    返回目标文件不存在的链接列表。

    返回格式：
    [
        {
            "link": "概念名",
            "source_file": "entries/某条目.md",
            "context": "包含该链接的那一行文本"
        },
        ...
    ]

    实现要点：
    - 用正则 r'\\[\\[([^\\]]+)\\]\\]' 提取所有链接目标
    - 链接目标对应文件：在 entries/{name}.md 或 placeholders/{name}.md 中查找
    - 两个位置都不存在则为 dangling link
    - 去重：同一个 link 在多个文件中出现，每次出现单独记录
    """
    root = Path(kb_path)
    results = []

    for md_file in _get_all_md_files(kb_path):
        # Build the relative path label (e.g. "entries/foo.md")
        try:
            rel = md_file.relative_to(root)
        except ValueError:
            rel = md_file

        lines = md_file.read_text(encoding='utf-8').splitlines()
        for line in lines:
            for match in _LINK_PATTERN.finditer(line):
                link_name = match.group(1)
                if not _file_exists_in_kb(kb_path, link_name):
                    results.append({
                        'link': link_name,
                        'source_file': str(rel),
                        'context': line.strip(),
                    })

    return results


def count_placeholder_refs(kb_path: str) -> list[dict]:
    """
    统计 placeholders/ 下每个占位文件被引用的次数。
    被引用 = 在 entries/ 或 placeholders/ 的任意 .md 文件中出现 [[文件名]]。

    返回格式（按引用次数降序排列）：
    [
        {
            "placeholder": "概念名",
            "ref_count": 7,
            "referenced_by": ["entries/条目A.md", "entries/条目B.md", ...]
        },
        ...
    ]
    """
    root = Path(kb_path)
    placeholders_dir = root / 'placeholders'

    if not placeholders_dir.is_dir():
        return []

    placeholder_names = [p.stem for p in placeholders_dir.glob('*.md')]

    # Build a map: placeholder_name -> list of source_file strings
    ref_map: dict[str, list[str]] = {name: [] for name in placeholder_names}

    all_files = _get_all_md_files(kb_path)
    for md_file in all_files:
        try:
            rel = str(md_file.relative_to(root))
        except ValueError:
            rel = str(md_file)

        content = md_file.read_text(encoding='utf-8')
        for link_name in _LINK_PATTERN.findall(content):
            if link_name in ref_map:
                ref_map[link_name].append(rel)

    results = [
        {
            'placeholder': name,
            'ref_count': len(files),
            'referenced_by': files,
        }
        for name, files in ref_map.items()
    ]

    results.sort(key=lambda x: x['ref_count'], reverse=True)
    return results


def find_orphan_entries(kb_path: str) -> list[str]:
    """
    检测 entries/ 下没有任何入链（被别人引用）且没有出链（引用别人）的条目。

    返回格式：
    ["entries/孤立条目A.md", "entries/孤立条目B.md", ...]

    实现要点：
    - 出链：该文件内容中包含 [[任何链接]]
    - 入链：其他文件内容中包含 [[该文件名]]
    - 两者都没有才算孤立
    """
    root = Path(kb_path)
    entries_dir = root / 'entries'

    if not entries_dir.is_dir():
        return []

    entry_files = list(entries_dir.glob('*.md'))

    # Collect all links from ALL files (entries + placeholders) by source
    all_files = _get_all_md_files(kb_path)

    # For each file, compute its outgoing links (by name)
    file_outlinks: dict[str, set[str]] = {}
    for md_file in all_files:
        content = md_file.read_text(encoding='utf-8')
        links = set(_LINK_PATTERN.findall(content))
        try:
            rel = str(md_file.relative_to(root))
        except ValueError:
            rel = str(md_file)
        file_outlinks[rel] = links

    orphans = []
    for entry_file in entry_files:
        try:
            rel = str(entry_file.relative_to(root))
        except ValueError:
            rel = str(entry_file)

        name = entry_file.stem

        # Does this entry have out-links?
        has_outlinks = bool(file_outlinks.get(rel))

        # Does any other file link to this entry?
        has_inlinks = any(
            name in links
            for file_rel, links in file_outlinks.items()
            if file_rel != rel
        )

        if not has_outlinks and not has_inlinks:
            orphans.append(rel)

    return sorted(orphans)


def collect_ref_contexts(kb_path: str, placeholder_name: str) -> list[str]:
    """
    收集指定占位概念在所有条目中被引用的上下文片段。
    用于归纳推理时给 LLM 提供材料。

    参数：placeholder_name 是概念名，不含路径和 .md 后缀

    返回格式：
    [
        "来源：entries/条目A.md\\n上下文：...包含[[概念名]]的前后3行...",
        "来源：entries/条目B.md\\n上下文：...包含[[概念名]]的前后3行...",
        ...
    ]
    """
    root = Path(kb_path)
    results = []
    target_pattern = re.compile(r'\[\[' + re.escape(placeholder_name) + r'\]\]')

    for md_file in _get_all_md_files(kb_path):
        content = md_file.read_text(encoding='utf-8')
        lines = content.splitlines()

        try:
            rel = str(md_file.relative_to(root))
        except ValueError:
            rel = str(md_file)

        for i, line in enumerate(lines):
            if target_pattern.search(line):
                # Grab up to 3 lines before and after
                start = max(0, i - 3)
                end = min(len(lines), i + 4)
                context_lines = lines[start:end]
                context = '\n'.join(context_lines)
                results.append(f'来源：{rel}\n上下文：\n{context}')

    return results
