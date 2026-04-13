from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from mcp_server.i18n import kb_localized_aliases, kb_sentence_markers
from mcp_server.settings import load_settings

FORMAL_ENTRY_TYPES = {"concept", "lesson"}
VALID_STATUSES = {"fact", "inferred", "disputed"}

LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
TITLE_PATTERN = re.compile(r"^#\s+(.+?)\s*$")
SECTION_PATTERN = re.compile(r"^##\s+(.+?)\s*$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PROVENANCE_HEADINGS = {"Source"}
PROVENANCE_LINE_PREFIXES = (
    "> Appears in:",
    "> Referenced in:",
    "Appears in:",
    "Referenced in:",
)
SECTION_ALIASES = {
    "source": "Source",
    "sources": "Source",
    "related": "Related",
    "scope": "Scope",
    "context": "Scope",
    "trigger": "Trigger",
    "when to apply": "Trigger",
    "why": "Why",
    "why this matters": "Why",
    "evidence / reasoning": "Why",
    "evidence/reasoning": "Why",
    "risks": "Risks",
    "common pitfalls": "Risks",
}
SECTION_ALIASES.update(kb_localized_aliases())
SENTENCE_STYLE_MARKERS = kb_sentence_markers()
INDEX_DEFAULTS = {
    "max_entries": 120,
    "max_tokens": 8000,
    "root_file": "index.root.md",
    "segment_glob": "index*.md",
}


@dataclass(slots=True)
class ParsedEntry:
    name: str
    path: Path | None
    kind: str
    entry_type: str
    status: str
    title: str
    aliases: tuple[str, ...]
    sources: tuple[str, ...]
    summary: str
    sections: dict[str, str]
    body: str
    preamble: str
    graph_links: tuple[str, ...]
    provenance_text: str
    provenance_links: tuple[str, ...]
    search_text: str
    knowledge_lines: tuple[str, ...]
    inbound_count: int = 0

    @property
    def is_canonical(self) -> bool:
        return self.entry_type == "concept"

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path) if self.path else None,
            "kind": self.kind,
            "entry_type": self.entry_type,
            "status": self.status,
            "title": self.title,
            "aliases": list(self.aliases),
            "sources": list(self.sources),
            "summary": self.summary,
            "links": list(self.graph_links),
            "graph_links": list(self.graph_links),
            "body": self.body,
            "preamble": self.preamble,
            "sections_map": dict(self.sections),
            "sections": list(self.sections.keys()),
            "provenance_text": self.provenance_text,
            "provenance_links": list(self.provenance_links),
            "search_text": self.search_text,
            "is_canonical": self.is_canonical,
            "inbound_count": self.inbound_count,
        }


@dataclass(slots=True)
class FormalEntry(ParsedEntry):
    pass


@dataclass(slots=True)
class PlaceholderEntry(ParsedEntry):
    pass


@dataclass(slots=True)
class RetrievalCandidate:
    name: str
    kind: str
    entry_type: str
    status: str
    score: int
    matched_terms: tuple[str, ...]
    matched_fields: tuple[str, ...]
    selection_reason: str
    summary: str
    is_canonical: bool

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "entry_type": self.entry_type,
            "status": self.status,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "matched_fields": list(self.matched_fields),
            "selection_reason": self.selection_reason,
            "summary": self.summary,
            "is_canonical": self.is_canonical,
        }


@dataclass(slots=True)
class SelectedPassage:
    name: str
    kind: str
    entry_type: str
    status: str
    section: str
    text: str
    score: int
    selection_reason: str

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "entry_type": self.entry_type,
            "status": self.status,
            "section": self.section,
            "text": self.text,
            "score": self.score,
            "selection_reason": self.selection_reason,
        }


@dataclass(slots=True)
class ParsedIndex:
    name: str
    path: Path
    kind: str
    title: str
    summary: str
    links: tuple[str, ...]
    entry_count: int
    estimated_tokens: int
    is_root: bool
    segment: str
    last_tidied_at: str

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "links": list(self.links),
            "entry_count": self.entry_count,
            "estimated_tokens": self.estimated_tokens,
            "is_root": self.is_root,
            "segment": self.segment,
            "last_tidied_at": self.last_tidied_at,
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
    parsed = _split_body_structure(body)
    return parsed["sections"], parsed["preamble"]


def extract_wikilinks(text: str) -> list[str]:
    links = []
    for raw in LINK_PATTERN.findall(text):
        target = raw.split("|")[0].split("#")[0].strip()
        if target:
            links.append(target)
    return list(dict.fromkeys(links))


def graph_relevant_text(text: str, *, kind: str) -> str:
    _, body = split_frontmatter(text)
    parsed = _split_body_structure(body, kind=kind)
    return "\n".join(parsed["knowledge_lines"])


def graph_links_from_text(text: str, *, kind: str) -> list[str]:
    return extract_wikilinks(graph_relevant_text(text, kind=kind))


def inventory(kb_path: str | Path) -> dict[str, Any]:
    root = Path(kb_path)
    entry_objects: dict[str, ParsedEntry] = {}
    alias_map: dict[str, list[str]] = defaultdict(list)
    index_objects: dict[str, ParsedIndex] = {}

    for kind, subdir in (("formal", "entries"), ("placeholder", "placeholders")):
        current = root / subdir
        if not current.is_dir():
            continue

        for path in sorted(current.glob("*.md")):
            if path.name == ".gitkeep":
                continue

            entry = parse_entry(path=path, kind=kind)
            entry_objects[entry.name] = entry
            for alias in entry.aliases:
                alias_map[alias].append(entry.name)

    inbound_counts: dict[str, int] = defaultdict(int)
    for entry in entry_objects.values():
        for target in entry.graph_links:
            if target in entry_objects:
                inbound_counts[target] += 1

    docs: dict[str, dict[str, Any]] = {}
    for name, entry in entry_objects.items():
        entry.inbound_count = inbound_counts.get(name, 0)
        docs[name] = entry.to_record()

    entries = sorted(name for name, entry in entry_objects.items() if entry.kind == "formal")
    placeholders = sorted(
        name for name, entry in entry_objects.items() if entry.kind == "placeholder"
    )
    canonical_entries = sorted(
        name
        for name, entry in entry_objects.items()
        if entry.kind == "formal" and entry.is_canonical
    )
    for path in _index_paths(root):
        parsed_index = parse_index(path)
        index_objects[parsed_index.name] = parsed_index

    return {
        "kb_path": str(root),
        "index_config": index_config(),
        "entries": entries,
        "placeholders": placeholders,
        "aliases": {alias: sorted(set(names)) for alias, names in alias_map.items()},
        "canonical_entries": canonical_entries,
        "entry_objects": entry_objects,
        "indexes": sorted(index_objects.keys()),
        "index_objects": index_objects,
        "index_docs": {name: item.to_record() for name, item in index_objects.items()},
        "docs": docs,
    }


def index_config() -> dict[str, Any]:
    settings = load_settings()["knowledge"]["index"]
    max_entries = int(settings.get("max_entries", INDEX_DEFAULTS["max_entries"]))
    max_tokens = int(settings.get("max_tokens", INDEX_DEFAULTS["max_tokens"]))
    root_file = str(settings.get("root_file", INDEX_DEFAULTS["root_file"])).strip()
    segment_glob = str(settings.get("segment_glob", INDEX_DEFAULTS["segment_glob"])).strip()
    return {
        "max_entries": max_entries,
        "max_tokens": max_tokens,
        "root_file": root_file or INDEX_DEFAULTS["root_file"],
        "segment_glob": segment_glob or INDEX_DEFAULTS["segment_glob"],
    }


def resolve_kb_document_path(kb_path: str | Path, filename: str) -> Path | None:
    root = Path(kb_path)
    candidates = [
        root / "entries" / f"{filename}.md",
        root / "placeholders" / f"{filename}.md",
        root / index_config()["root_file"],
    ]
    for path in _index_paths(root):
        if path.stem == filename:
            candidates.append(path)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file() and candidate.stem == filename:
            return candidate
    return None


def parse_entry(
    *,
    path: str | Path | None = None,
    text: str | None = None,
    name: str | None = None,
    kind: str | None = None,
) -> ParsedEntry:
    if path is None and text is None:
        raise ValueError("parse_entry requires either path or text")

    source_path = Path(path) if path is not None else None
    if source_path is not None:
        text = source_path.read_text(encoding="utf-8")
        if kind is None:
            kind = "placeholder" if source_path.parent.name == "placeholders" else "formal"
        if name is None:
            name = source_path.stem

    assert text is not None
    entry_name = name or "UNKNOWN"
    frontmatter, body = split_frontmatter(text)
    parsed = _split_body_structure(body, kind=kind or "formal")
    entry_type = _infer_entry_type(
        frontmatter=frontmatter,
        fallback_kind=kind or "formal",
        title=parsed["title"] or entry_name,
        sections=parsed["sections"],
    )
    actual_kind = "placeholder" if entry_type == "placeholder" else "formal"
    aliases = _normalize_list(frontmatter.get("aliases"))
    sources = _normalize_list(frontmatter.get("sources"))
    summary = _extract_summary(parsed["preamble"], kind=actual_kind)
    graph_text = "\n".join(parsed["knowledge_lines"]).strip()
    title = parsed["title"] or entry_name
    search_text = "\n".join(part for part in (title, graph_text) if part).strip()

    payload: dict[str, Any] = {
        "name": entry_name,
        "path": source_path,
        "kind": actual_kind,
        "entry_type": entry_type,
        "status": str(frontmatter.get("status", "")).strip(),
        "title": title,
        "aliases": tuple(aliases),
        "sources": tuple(sources),
        "summary": summary,
        "sections": parsed["sections"],
        "body": body,
        "preamble": parsed["preamble"],
        "graph_links": tuple(extract_wikilinks(graph_text)),
        "provenance_text": "\n".join(parsed["provenance_lines"]).strip(),
        "provenance_links": tuple(extract_wikilinks("\n".join(parsed["provenance_lines"]))),
        "search_text": search_text,
        "knowledge_lines": tuple(parsed["knowledge_lines"]),
    }
    if actual_kind == "placeholder":
        return PlaceholderEntry(**payload)
    return FormalEntry(**payload)


def validate_entry(
    *,
    path: str | Path | None = None,
    text: str | None = None,
    name: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    entry = parse_entry(path=path, text=text, name=name, kind=kind)
    hard_failures = []
    warnings = []

    frontmatter = {}
    if path is not None:
        frontmatter, _ = split_frontmatter(Path(path).read_text(encoding="utf-8"))
    elif text is not None:
        frontmatter, _ = split_frontmatter(text)

    raw_type = str(frontmatter.get("type", "")).strip()
    if raw_type != entry.entry_type:
        hard_failures.append(f"frontmatter.type must be '{entry.entry_type}'")

    related_links = extract_wikilinks(entry.sections.get("Related", ""))

    if entry.entry_type == "placeholder":
        if not _has_meaningful_text(entry.summary):
            hard_failures.append("placeholder must contain a gap description in the body")
    else:
        if entry.status not in VALID_STATUSES:
            hard_failures.append(
                "formal entry must declare frontmatter.status as fact, inferred, or disputed"
            )
        if not entry.sources:
            hard_failures.append("formal entry must declare at least one frontmatter.sources item")
        if not _has_meaningful_text(entry.summary):
            hard_failures.append("entry must contain a substantive summary/core proposition")

    if entry.entry_type == "concept":
        if not _has_meaningful_text(entry.sections.get("Scope", "")):
            hard_failures.append("concept entry must include a substantive Scope section")
        if not related_links:
            hard_failures.append("concept entry must include at least one Related wikilink")
    elif entry.entry_type == "lesson":
        for section_name in ("Trigger", "Why", "Risks"):
            if not _has_meaningful_text(entry.sections.get(section_name, "")):
                hard_failures.append(
                    f"lesson entry must include a substantive {section_name} section"
                )
        if not related_links:
            hard_failures.append("lesson entry must include at least one Related wikilink")

    if entry.sources and len(entry.sources) != len(set(entry.sources)):
        warnings.append("frontmatter.sources contains duplicate entries")
    if entry.summary and len(entry.summary) > 220:
        warnings.append("summary is longer than the preferred queryable size")

    return {
        "name": entry.name,
        "kind": entry.kind,
        "entry_type": entry.entry_type,
        "valid": not hard_failures,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "metrics": {
            "summary_length": len(entry.summary),
            "related_link_count": len(related_links),
            "source_count": len(entry.sources),
            "provenance_link_count": len(entry.provenance_links),
        },
    }


def audit_kb(kb_path: str | Path) -> dict[str, Any]:
    root = Path(kb_path)
    data = inventory(root)
    entry_objects: dict[str, ParsedEntry] = data["entry_objects"]
    docs = data["docs"]
    index_objects: dict[str, ParsedIndex] = data.get("index_objects", {})
    cfg = data["index_config"]

    entry_validations = [
        validate_entry(path=entry.path, kind=entry.kind, name=entry.name)
        for entry in entry_objects.values()
    ]
    index_validations = [
        validate_index(path=item.path)
        for item in index_objects.values()
    ]
    formal_validations = [item for item in entry_validations if item["kind"] == "formal"]
    placeholder_validations = [item for item in entry_validations if item["kind"] == "placeholder"]

    hard_fail_entries = [item["name"] for item in entry_validations if item["hard_failures"]]
    placeholder_hard_fail_entries = [
        item["name"] for item in placeholder_validations if item["hard_failures"]
    ]
    invalid_indexes = [item["name"] for item in index_validations if item["hard_failures"]]
    missing_scope = [
        item["name"]
        for item in formal_validations
        if "concept entry must include a substantive Scope section" in item["hard_failures"]
    ]
    missing_trigger = [
        item["name"]
        for item in formal_validations
        if "lesson entry must include a substantive Trigger section" in item["hard_failures"]
    ]
    missing_why = [
        item["name"]
        for item in formal_validations
        if "lesson entry must include a substantive Why section" in item["hard_failures"]
    ]
    missing_risks = [
        item["name"]
        for item in formal_validations
        if "lesson entry must include a substantive Risks section" in item["hard_failures"]
    ]
    weak_related = [
        item["name"]
        for item in formal_validations
        if item["metrics"]["related_link_count"] == 0
    ]

    provenance_contamination = [
        {
            "name": entry.name,
            "kind": entry.kind,
            "links": sorted(set(entry.provenance_links)),
        }
        for entry in entry_objects.values()
        if entry.provenance_links
    ]

    placeholder_refs = count_placeholder_refs(str(root))
    dangling = find_dangling_links(str(root))
    orphans = find_orphan_entries(str(root))
    promotable_placeholders = [
        {
            "name": item["placeholder"],
            "ref_count": item["ref_count"],
            "referenced_by": item["referenced_by"][:8],
        }
        for item in placeholder_refs
        if item["ref_count"] >= 3
    ]

    canonical_gaps: dict[str, set[str]] = defaultdict(set)
    for entry in entry_objects.values():
        if entry.kind != "formal":
            continue
        for target in entry.graph_links:
            target_doc = docs.get(target)
            if target_doc is not None and target_doc["kind"] == "placeholder":
                canonical_gaps[target].add(entry.name)

    entry_sizes = [
        len(entry.path.read_text(encoding="utf-8"))
        for entry in entry_objects.values()
        if entry.kind == "formal" and entry.path is not None
    ]
    formal_names = set(data["entries"])
    placeholder_names = set(data["placeholders"])
    known_indexes = set(index_objects)
    index_link_coverage: set[str] = set()
    overloaded_indexes = []
    unknown_index_links = []
    root_index_name = Path(cfg["root_file"]).stem
    for item in index_objects.values():
        if item.entry_count > cfg["max_entries"] or item.estimated_tokens > cfg["max_tokens"]:
            overloaded_indexes.append(
                {
                    "name": item.name,
                    "entry_count": item.entry_count,
                    "estimated_tokens": item.estimated_tokens,
                }
            )
        for target in item.links:
            if target in formal_names:
                index_link_coverage.add(target)
            elif target in placeholder_names or target not in known_indexes:
                unknown_index_links.append({"index": item.name, "link": target})
    uncovered_formal = sorted(formal_names - index_link_coverage)

    return {
        "kb_path": str(root),
        "index_config": cfg,
        "formal_entry_count": len(data["entries"]),
        "concept_entry_count": sum(
            1 for name in data["entries"] if docs[name]["entry_type"] == "concept"
        ),
        "lesson_entry_count": sum(
            1 for name in data["entries"] if docs[name]["entry_type"] == "lesson"
        ),
        "placeholder_count": len(data["placeholders"]),
        "hard_fail_entry_count": len(hard_fail_entries),
        "hard_fail_entries": sorted(hard_fail_entries),
        "invalid_placeholder_count": len(placeholder_hard_fail_entries),
        "invalid_placeholder_entries": sorted(placeholder_hard_fail_entries),
        "missing_scope_count": len(missing_scope),
        "missing_scope_entries": sorted(missing_scope),
        "missing_trigger_count": len(missing_trigger),
        "missing_trigger_entries": sorted(missing_trigger),
        "missing_why_count": len(missing_why),
        "missing_why_entries": sorted(missing_why),
        "missing_risks_count": len(missing_risks),
        "missing_risks_entries": sorted(missing_risks),
        "weak_related_count": len(weak_related),
        "weak_related_entries": sorted(weak_related),
        "dangling_link_count": len(dangling),
        "dangling_links": dangling[:100],
        "orphan_entry_count": len(orphans),
        "orphan_entries": orphans[:100],
        "promotable_placeholder_count": len(promotable_placeholders),
        "promotable_placeholders": promotable_placeholders[:50],
        "canonical_gap_count": len(canonical_gaps),
        "canonical_gaps": [
            {"name": name, "referenced_by": sorted(refs)}
            for name, refs in sorted(canonical_gaps.items())
        ],
        "provenance_contamination_count": len(provenance_contamination),
        "provenance_contamination": provenance_contamination[:100],
        "avg_entry_size": _average(entry_sizes),
        "p50_entry_size": _percentile(entry_sizes, 50),
        "p90_entry_size": _percentile(entry_sizes, 90),
        "top_shallow_entries": [
            {"name": item["name"], "hard_failures": item["hard_failures"]}
            for item in sorted(
                entry_validations,
                key=lambda value: len(value["hard_failures"]),
                reverse=True,
            )
            if item["hard_failures"]
        ][:10],
        "entry_validation": entry_validations,
        "index_validation": index_validations,
        "index_count": len(index_objects),
        "invalid_index_count": len(invalid_indexes),
        "invalid_indexes": sorted(invalid_indexes),
        "root_index_present": root_index_name in index_objects,
        "overloaded_index_count": len(overloaded_indexes),
        "overloaded_indexes": sorted(overloaded_indexes, key=lambda item: item["name"]),
        "uncovered_formal_entry_count": len(uncovered_formal),
        "uncovered_formal_entries": uncovered_formal[:100],
        "unknown_index_link_count": len(unknown_index_links),
        "unknown_index_links": unknown_index_links[:100],
    }


def plan_index_repairs(kb_path: str | Path) -> list[dict[str, Any]]:
    root = Path(kb_path)
    data = inventory(root)
    report = audit_kb(root)
    index_docs: dict[str, dict[str, Any]] = data.get("index_docs", {})
    actions: list[dict[str, Any]] = []

    if not report["root_index_present"]:
        actions.append(
            {
                "action": "create_root_index",
                "target": Path(data["index_config"]["root_file"]).stem,
                "reason": "root index is missing",
                "priority": "high",
            }
        )

    for name in report["invalid_indexes"]:
        actions.append(
            {
                "action": "repair_index_contract",
                "target": name,
                "reason": "index frontmatter or metadata is invalid",
                "priority": "high",
            }
        )

    for item in report["overloaded_indexes"]:
        actions.append(
            {
                "action": "split_index",
                "target": item["name"],
                "reason": (
                    f"index exceeds threshold "
                    f"(entries={item['entry_count']}, tokens={item['estimated_tokens']})"
                ),
                "priority": "medium",
            }
        )

    for item in report["unknown_index_links"]:
        actions.append(
            {
                "action": "repair_index_link",
                "target": item["index"],
                "link": item["link"],
                "reason": "index references a missing, placeholder, or unknown target",
                "priority": "high",
            }
        )

    for name in report["uncovered_formal_entries"]:
        actions.append(
            {
                "action": "cover_entry_from_index",
                "target": name,
                "reason": "formal entry is not reachable from any index",
                "priority": "medium",
            }
        )

    actions.extend(_merge_candidate_actions(index_docs))
    actions.sort(
        key=lambda item: (_priority_rank(item["priority"]), item["action"], item["target"])
    )
    return actions


def find_dangling_links(kb_path: str) -> list[dict[str, Any]]:
    root = Path(kb_path)
    data = inventory(root)
    entry_objects: dict[str, ParsedEntry] = data["entry_objects"]
    known_names = set(entry_objects)
    results = []

    for entry in entry_objects.values():
        rel = _relative_path(entry.path, root)
        for line in entry.knowledge_lines:
            for target in extract_wikilinks(line):
                if target not in known_names:
                    results.append(
                        {
                            "link": target,
                            "source_file": rel,
                            "context": line.strip(),
                        }
                    )
    return results


def _merge_candidate_actions(index_docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    names = sorted(name for name, item in index_docs.items() if not item.get("is_root"))
    actions = []
    for idx, left in enumerate(names):
        left_links = set(index_docs[left].get("links", []))
        if not left_links or len(left_links) > 3:
            continue
        for right in names[idx + 1 :]:
            right_links = set(index_docs[right].get("links", []))
            if not right_links or len(right_links) > 3:
                continue
            overlap = left_links & right_links
            union = left_links | right_links
            if len(overlap) < 2:
                continue
            if len(union) == 0:
                continue
            jaccard = len(overlap) / len(union)
            if jaccard < 0.6:
                continue
            actions.append(
                {
                    "action": "merge_index_candidates",
                    "target": f"{left}+{right}",
                    "reason": (
                        "two low-density indexes have high overlap "
                        f"(jaccard={jaccard:.2f})"
                    ),
                    "priority": "low",
                }
            )
    return actions


def count_placeholder_refs(kb_path: str) -> list[dict[str, Any]]:
    root = Path(kb_path)
    data = inventory(root)
    entry_objects: dict[str, ParsedEntry] = data["entry_objects"]
    placeholder_names = set(data["placeholders"])

    ref_map: dict[str, list[str]] = {name: [] for name in placeholder_names}
    for entry in entry_objects.values():
        rel = _relative_path(entry.path, root)
        for target in entry.graph_links:
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
    root = Path(kb_path)
    data = inventory(root)
    entry_objects: dict[str, ParsedEntry] = data["entry_objects"]

    orphans = []
    for name in data["entries"]:
        entry = entry_objects[name]
        has_outlinks = bool(entry.graph_links)
        has_inlinks = any(
            name in other.graph_links
            for other_name, other in entry_objects.items()
            if other_name != name
        )
        if not has_outlinks and not has_inlinks:
            orphans.append(_relative_path(entry.path, root))
    return sorted(orphans)


def collect_ref_contexts(kb_path: str, placeholder_name: str) -> list[str]:
    root = Path(kb_path)
    data = inventory(root)
    entry_objects: dict[str, ParsedEntry] = data["entry_objects"]
    results = []
    target_pattern = re.compile(r"\[\[" + re.escape(placeholder_name) + r"(?:[|#][^\]]*)?\]\]")

    for entry in entry_objects.values():
        lines = list(entry.knowledge_lines)
        rel = _relative_path(entry.path, root)
        for index, line in enumerate(lines):
            if not target_pattern.search(line):
                continue
            start = max(0, index - 3)
            end = min(len(lines), index + 4)
            context = "\n".join(lines[start:end])
            results.append(f"来源：{rel}\n上下文：\n{context}")
    return results


def _split_body_structure(body: str, *, kind: str = "formal") -> dict[str, Any]:
    title = ""
    title_seen = False
    current_section = "__preamble__"
    buckets: dict[str, list[str]] = defaultdict(list)
    section_order: list[str] = []
    knowledge_lines: list[str] = []
    provenance_lines: list[str] = []

    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if not title_seen:
            title_match = TITLE_PATTERN.match(stripped)
            if title_match:
                title = title_match.group(1).strip()
                title_seen = True
                continue

        heading = SECTION_PATTERN.match(stripped)
        if heading:
            current_section = normalize_section_name(heading.group(1))
            if current_section not in buckets:
                section_order.append(current_section)
            if current_section in PROVENANCE_HEADINGS:
                provenance_lines.append(raw_line)
            else:
                knowledge_lines.append(raw_line)
            continue

        buckets[current_section].append(raw_line)
        if current_section in PROVENANCE_HEADINGS:
            provenance_lines.append(raw_line)
            continue
        if kind == "placeholder" and _is_placeholder_provenance_line(stripped):
            provenance_lines.append(raw_line)
            continue
        knowledge_lines.append(raw_line)

    sections = {
        name: "\n".join(buckets[name]).strip()
        for name in section_order
    }
    preamble = "\n".join(buckets.pop("__preamble__", [])).strip()
    return {
        "title": title,
        "preamble": preamble,
        "sections": sections,
        "knowledge_lines": knowledge_lines,
        "provenance_lines": provenance_lines,
    }


def _index_paths(root: Path) -> list[Path]:
    candidates = []
    cfg = index_config()
    root_index = root / cfg["root_file"]
    if root_index.is_file():
        candidates.append(root_index)
    indexes_dir = root / "indexes"
    if indexes_dir.is_dir():
        candidates.extend(sorted(indexes_dir.glob(cfg["segment_glob"])))
    return candidates


def parse_index(path: str | Path) -> ParsedIndex:
    source_path = Path(path)
    text = source_path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    _, preamble = split_sections(body)
    title_match = TITLE_PATTERN.search(body)
    title = title_match.group(1).strip() if title_match else source_path.stem
    summary = _extract_summary(preamble, kind="formal")
    links = tuple(extract_wikilinks(body))
    kind = str(frontmatter.get("kind", "")).strip()
    raw_entry_count = frontmatter.get("entry_count")
    raw_estimated_tokens = frontmatter.get("estimated_tokens")
    segment = str(frontmatter.get("segment", source_path.stem)).strip() or source_path.stem
    last_tidied_at = str(frontmatter.get("last_tidied_at", "")).strip()
    entry_count = int(raw_entry_count) if isinstance(raw_entry_count, int) else len(set(links))
    estimated_tokens = (
        int(raw_estimated_tokens)
        if isinstance(raw_estimated_tokens, int)
        else _estimate_tokens(text)
    )
    root_name = Path(index_config()["root_file"]).stem
    return ParsedIndex(
        name=source_path.stem,
        path=source_path,
        kind=kind,
        title=title,
        summary=summary,
        links=links,
        entry_count=entry_count,
        estimated_tokens=estimated_tokens,
        is_root=source_path.stem == root_name,
        segment=segment,
        last_tidied_at=last_tidied_at,
    )


def validate_index(path: str | Path) -> dict[str, Any]:
    item = parse_index(path)
    hard_failures = []
    warnings = []

    if item.kind != "index":
        hard_failures.append("index frontmatter.kind must be 'index'")
    if not item.segment:
        hard_failures.append("index must declare a non-empty frontmatter.segment")
    if item.is_root and item.segment != "root":
        hard_failures.append("root index must use frontmatter.segment='root'")
    if item.last_tidied_at and not DATE_PATTERN.fullmatch(item.last_tidied_at):
        hard_failures.append("index last_tidied_at must use YYYY-MM-DD format")
    if item.entry_count < 0:
        hard_failures.append("index entry_count must be >= 0")
    if item.estimated_tokens <= 0:
        hard_failures.append("index estimated_tokens must be > 0")
    if not item.summary:
        warnings.append("index should include a short summary/purpose statement")
    if not item.links:
        warnings.append("index should link to at least one segment or formal entry")

    return {
        "name": item.name,
        "valid": not hard_failures,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "metrics": {
            "entry_count": item.entry_count,
            "estimated_tokens": item.estimated_tokens,
            "link_count": len(item.links),
            "is_root": item.is_root,
        },
    }


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
def _priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(priority, 3)


def _infer_entry_type(
    *,
    frontmatter: dict[str, Any],
    fallback_kind: str,
    title: str,
    sections: dict[str, str],
) -> str:
    raw_type = str(frontmatter.get("type", "")).strip()
    if raw_type in {"concept", "lesson", "placeholder"}:
        return raw_type
    if (
        fallback_kind == "placeholder"
        or str(frontmatter.get("status", "")).strip() == "placeholder"
    ):
        return "placeholder"
    if "Trigger" in sections or "Why" in sections or "Risks" in sections:
        return "lesson"
    if _is_sentence_style(title):
        return "lesson"
    return "concept"


def _normalize_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    return [str(item).strip() for item in raw_value if str(item).strip()]


def _extract_summary(preamble: str, *, kind: str) -> str:
    lines = []
    for raw_line in preamble.splitlines():
        stripped = raw_line.strip()
        if kind == "placeholder" and _is_placeholder_provenance_line(stripped):
            continue
        lines.append(raw_line)

    cleaned_preamble = "\n".join(lines).strip()
    if not cleaned_preamble:
        return ""

    for block in re.split(r"\n\s*\n", cleaned_preamble):
        text = _compress_whitespace(_strip_quote_prefixes(block))
        if text:
            return _truncate(_first_sentences(text, 2), 260)
    return ""


def _strip_quote_prefixes(text: str) -> str:
    return "\n".join(line.lstrip("> ").rstrip() for line in text.splitlines()).strip()


def _first_sentences(text: str, limit: int) -> str:
    sentences = [segment.strip() for segment in re.split(r"[。！？.!?]", text) if segment.strip()]
    chosen = "。".join(sentences[:limit])
    if chosen and not chosen.endswith("。"):
        chosen += "。"
    return chosen


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _compress_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _has_meaningful_text(text: str) -> bool:
    compact = re.sub(r"\[\[[^\]]+\]\]", "", text or "")
    compact = re.sub(r"[`*_>#-]", " ", compact)
    compact = _compress_whitespace(compact)
    if not compact:
        return False
    return len(compact) >= 4 or bool(re.fullmatch(r"[\u4e00-\u9fff]{2,}", compact))


def _is_sentence_style(title: str) -> bool:
    return len(title) > 4 and any(marker in title for marker in SENTENCE_STYLE_MARKERS)


def _is_placeholder_provenance_line(stripped: str) -> bool:
    return any(stripped.startswith(prefix) for prefix in PROVENANCE_LINE_PREFIXES)


def _average(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = round((percentile / 100) * (len(ordered) - 1))
    return ordered[index]


def _relative_path(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
