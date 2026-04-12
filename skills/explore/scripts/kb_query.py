from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import yaml

from skills.tidy.scripts.tidy_utils import (
    count_placeholder_refs,
    find_dangling_links,
    find_orphan_entries,
    graph_links_from_text,
)

LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$")
STOP_WORDS = {
    "什么",
    "哪些",
    "多少",
    "几种",
    "为什么",
    "如何",
    "怎么",
    "怎样",
    "可以",
    "应该",
    "需要",
    "里面",
    "中",
    "里",
    "从",
    "看",
    "和",
    "与",
    "及",
    "是",
    "的",
    "了",
    "在",
    "由",
    "把",
    "将",
    "对",
    "有",
    "一个",
    "这个",
    "那个",
    "这些",
    "那些",
    "定义",
    "作用",
    "流程",
    "步骤",
    "逻辑",
    "问题",
    "系统",
    "知识",
    "文档",
}
SENTENCE_STYLE_MARKERS = (
    "必须",
    "应该",
    "需要",
    "优先",
    "避免",
    "防止",
    "不要",
    "不能",
    "导致",
    "如果",
    "当",
    "先",
    "再",
    "前",
    "后",
    "时",
    "须",
)
REQUIRED_FORMAL_SECTIONS = (
    "Context",
    "Why This Matters",
    "Common Pitfalls",
    "Related",
    "Source",
)


def inventory(kb_path: str | Path) -> dict[str, Any]:
    root = Path(kb_path)
    docs: dict[str, dict[str, Any]] = {}
    alias_map: dict[str, list[str]] = defaultdict(list)

    for kind, subdir in (("formal", "entries"), ("placeholder", "placeholders")):
        current = root / subdir
        if not current.is_dir():
            continue

        for path in sorted(current.glob("*.md")):
            if path.name == ".gitkeep":
                continue

            payload = _parse_doc(path, kind)
            docs[payload["name"]] = payload
            for alias in payload["aliases"]:
                alias_map[alias].append(payload["name"])

    inbound_counts: dict[str, int] = defaultdict(int)
    for doc in docs.values():
        for target in doc["links"]:
            if target in docs:
                inbound_counts[target] += 1

    for name, doc in docs.items():
        doc["inbound_count"] = inbound_counts.get(name, 0)

    canonical_entries = sorted(
        name for name, doc in docs.items() if doc["kind"] == "formal" and doc["is_canonical"]
    )
    entries = sorted(name for name, doc in docs.items() if doc["kind"] == "formal")
    placeholders = sorted(name for name, doc in docs.items() if doc["kind"] == "placeholder")

    return {
        "kb_path": str(root),
        "entries": entries,
        "placeholders": placeholders,
        "aliases": {alias: sorted(set(names)) for alias, names in alias_map.items()},
        "canonical_entries": canonical_entries,
        "docs": docs,
    }


def shortlist(
    question: str,
    kb_path: str | Path | None = None,
    inventory_data: dict[str, Any] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    data = inventory_data or inventory(kb_path)
    question_lower = question.lower()
    terms = _extract_terms(question)
    results = []

    for doc in data["docs"].values():
        score = 0
        evidence_score = 0
        matched_terms = []
        lowered_aliases = [alias.lower() for alias in doc["aliases"]]

        if doc["name"].lower() in question_lower:
            evidence_score += 120
            matched_terms.append(doc["name"])

        for alias in doc["aliases"]:
            if alias.lower() in question_lower:
                evidence_score += 90
                matched_terms.append(alias)

        for term in terms:
            term_lower = term.lower()
            if term_lower in doc["name"].lower():
                evidence_score += 70
                matched_terms.append(term)
            if any(term_lower in alias for alias in lowered_aliases):
                evidence_score += 50
                matched_terms.append(term)
            if term_lower in doc["summary"].lower():
                evidence_score += 18
            if term_lower in doc["body"].lower():
                evidence_score += 8

        if evidence_score <= 0:
            continue

        score += evidence_score

        if doc["is_canonical"]:
            score += 8
        if doc["kind"] == "placeholder":
            score -= 22
        else:
            score += 4

        score += min(doc["inbound_count"], 8)
        if score <= 0:
            continue

        results.append(
            {
                "name": doc["name"],
                "kind": doc["kind"],
                "score": score,
                "matched_terms": sorted(set(matched_terms)),
                "is_canonical": doc["is_canonical"],
                "summary": doc["summary"],
            }
        )

    results.sort(key=lambda item: (-item["score"], item["name"]))
    return results[:limit]


def neighbors(
    names: list[str] | tuple[str, ...],
    kb_path: str | Path | None = None,
    inventory_data: dict[str, Any] | None = None,
    depth: int = 2,
    limit: int = 12,
) -> list[dict[str, Any]]:
    data = inventory_data or inventory(kb_path)
    docs = data["docs"]
    queue = deque()
    visited: dict[str, dict[str, Any]] = {}

    for name in names:
        if name not in docs:
            continue
        queue.append((name, 0, None))

    while queue and len(visited) < limit:
        current, current_depth, via = queue.popleft()
        if current in visited and visited[current]["depth"] <= current_depth:
            continue

        visited[current] = {
            "name": current,
            "depth": current_depth,
            "via": via,
            "kind": docs[current]["kind"],
        }

        if current_depth >= depth:
            continue

        next_targets = sorted(set(docs[current]["links"]) | _incoming_neighbors(current, docs))
        for target in next_targets:
            if target not in docs:
                continue
            queue.append((target, current_depth + 1, current))

    ordered = sorted(visited.values(), key=lambda item: (item["depth"], item["name"]))
    return ordered[:limit]


def snippets(
    names: list[str] | tuple[str, ...],
    question: str = "",
    kb_path: str | Path | None = None,
    inventory_data: dict[str, Any] | None = None,
    max_snippets_per_entry: int = 2,
    snippet_char_limit: int = 320,
) -> dict[str, dict[str, Any]]:
    data = inventory_data or inventory(kb_path)
    docs = data["docs"]
    terms = _extract_terms(question)
    result: dict[str, dict[str, Any]] = {}

    for name in names:
        doc = docs.get(name)
        if doc is None:
            continue

        picked = []
        passages = _candidate_passages(doc)
        scored = []
        for section, passage in passages:
            score = _score_passage(section, passage, terms)
            scored.append((score, section, _truncate(passage, snippet_char_limit)))

        scored.sort(key=lambda item: (-item[0], item[1]))
        for _, section, passage in scored[:max_snippets_per_entry]:
            picked.append({"section": section, "text": passage})

        result[name] = {
            "kind": doc["kind"],
            "summary": doc["summary"],
            "aliases": doc["aliases"],
            "links": doc["links"],
            "snippets": picked,
        }

    return result


def validate_answer(
    answer_payload: dict[str, Any],
    kb_path: str | Path | None = None,
    inventory_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = inventory_data or inventory(kb_path)
    docs = data["docs"]
    errors = []

    normalized = {
        "answer": answer_payload.get("answer", ""),
        "sources": answer_payload.get("sources", []),
        "confidence": answer_payload.get("confidence", ""),
        "exploration_summary": answer_payload.get("exploration_summary", {}),
        "gaps": answer_payload.get("gaps", []),
        "contradictions": answer_payload.get("contradictions", []),
    }

    if not isinstance(normalized["answer"], str) or not normalized["answer"].strip():
        errors.append("answer must be a non-empty string")

    if not isinstance(normalized["sources"], list) or not all(
        isinstance(item, str) and item.strip() for item in normalized["sources"]
    ):
        errors.append("sources must be a list of non-empty strings")
    else:
        normalized["sources"] = list(dict.fromkeys(item.strip() for item in normalized["sources"]))
        invalid_sources = [item for item in normalized["sources"] if item not in docs]
        if invalid_sources:
            errors.append(f"unknown sources: {', '.join(invalid_sources)}")
        elif normalized["sources"]:
            formal_sources = [
                name for name in normalized["sources"] if docs[name]["kind"] == "formal"
            ]
            if not formal_sources:
                errors.append(
                    "at least one formal source is required; "
                    "placeholder-only evidence is invalid"
                )

    if normalized["confidence"] not in {"high", "medium", "low"}:
        errors.append("confidence must be one of: high, medium, low")

    summary = normalized["exploration_summary"]
    if not isinstance(summary, dict):
        errors.append("exploration_summary must be an object")
    else:
        for key in ("entries_scanned", "entries_read", "links_followed"):
            if not isinstance(summary.get(key), int):
                errors.append(f"exploration_summary.{key} must be an integer")
        if not isinstance(summary.get("mode"), str) or not summary.get("mode"):
            errors.append("exploration_summary.mode must be a non-empty string")

    if not isinstance(normalized["gaps"], list) or not all(
        isinstance(item, str) for item in normalized["gaps"]
    ):
        errors.append("gaps must be a list of strings")

    contradictions = normalized["contradictions"]
    if not isinstance(contradictions, list):
        errors.append("contradictions must be a list")
    else:
        for idx, item in enumerate(contradictions):
            if not isinstance(item, dict):
                errors.append(f"contradictions[{idx}] must be an object")
                continue
            entries = item.get("entries", [])
            if not isinstance(entries, list) or not all(isinstance(name, str) for name in entries):
                errors.append(f"contradictions[{idx}].entries must be a list of strings")
            else:
                missing = [name for name in entries if name not in docs]
                if missing:
                    errors.append(
                        f"contradictions[{idx}] references unknown entries: {', '.join(missing)}"
                    )
            if not isinstance(item.get("conflict"), str) or not item.get("conflict"):
                errors.append(f"contradictions[{idx}].conflict must be a non-empty string")
            if not isinstance(item.get("analysis"), str) or not item.get("analysis"):
                errors.append(f"contradictions[{idx}].analysis must be a non-empty string")

    return {
        "valid": not errors,
        "errors": errors,
        "normalized": normalized,
    }


def validate_entry(
    *,
    path: str | Path | None = None,
    text: str | None = None,
    name: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    if path is None and text is None:
        raise ValueError("validate_entry requires either path or text")

    source_path = Path(path) if path is not None else None
    if source_path is not None:
        text = source_path.read_text(encoding="utf-8")
        if kind is None:
            kind = "placeholder" if source_path.parent.name == "placeholders" else "formal"
        if name is None:
            name = source_path.stem

    assert text is not None
    name = name or "UNKNOWN"
    kind = kind or "formal"

    frontmatter, body = _split_frontmatter(text)
    sections, preamble = _parse_sections(body)
    hard_failures = []
    warnings = []

    if kind == "placeholder":
        if frontmatter.get("status") != "placeholder":
            hard_failures.append("placeholder must declare status: placeholder")
        if "#status/placeholder" not in body:
            hard_failures.append("placeholder must include #status/placeholder marker")
        if "Needs human or agent" not in body:
            hard_failures.append("placeholder must include a next-step checklist")
        if "Appears in:" not in body and "Referenced in:" not in body:
            warnings.append("placeholder should record where it appears")
        return {
            "name": name,
            "kind": kind,
            "valid": not hard_failures,
            "hard_failures": hard_failures,
            "warnings": warnings,
            "metrics": {
                "inline_link_count": len(_extract_links(body)),
                "missing_sections": [],
            },
        }

    summary = _extract_summary(body)
    lesson_like = _is_sentence_style(name) or _looks_like_lesson(summary)

    missing_sections = [section for section in REQUIRED_FORMAL_SECTIONS if section not in sections]
    for section in missing_sections:
        hard_failures.append(f"missing required section: {section}")

    if lesson_like and "Evidence / Reasoning" not in sections:
        hard_failures.append("lesson-style entry must include section: Evidence / Reasoning")

    inline_link_count = _count_inline_links(body)
    if inline_link_count < 2:
        hard_failures.append("formal entry must contain at least 2 inline wikilinks")

    for section_name in ("Context", "Why This Matters", "Common Pitfalls"):
        content = sections.get(section_name, "")
        if not _is_substantive(content):
            hard_failures.append(f"section too short or empty: {section_name}")

    if lesson_like and not _is_substantive(sections.get("Evidence / Reasoning", "")):
        hard_failures.append("section too short or empty: Evidence / Reasoning")

    related_links = len(_extract_links(sections.get("Related", "")))
    if related_links < 2:
        hard_failures.append("Related section must mention at least 2 linked entries")

    source_refs = len(_extract_links(sections.get("Source", ""))) + len(
        [line for line in sections.get("Source", "").splitlines() if line.strip().startswith("-")]
    )
    if source_refs < 1:
        hard_failures.append("Source section must contain at least 1 source reference")

    if not summary:
        hard_failures.append("entry must contain a substantive summary/core proposition")
    elif len(summary) > 220:
        warnings.append("summary is longer than the preferred queryable size")

    if not preamble.strip():
        warnings.append("entry preamble is empty")

    return {
        "name": name,
        "kind": kind,
        "valid": not hard_failures,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "metrics": {
            "inline_link_count": inline_link_count,
            "missing_sections": missing_sections,
            "related_link_count": related_links,
            "source_ref_count": source_refs,
            "lesson_like": lesson_like,
        },
    }


def audit_kb(kb_path: str | Path) -> dict[str, Any]:
    root = Path(kb_path)
    data = inventory(root)
    docs = data["docs"]

    entry_validations = []
    for name in data["entries"]:
        doc = docs[name]
        validation = validate_entry(path=doc["path"], kind="formal", name=name)
        entry_validations.append(validation)

    hard_fail_entries = [item["name"] for item in entry_validations if item["hard_failures"]]
    missing_why = [
        item["name"]
        for item in entry_validations
        if any("Why This Matters" in failure for failure in item["hard_failures"])
    ]
    missing_pitfalls = [
        item["name"]
        for item in entry_validations
        if any("Common Pitfalls" in failure for failure in item["hard_failures"])
    ]
    weak_inline_links = [
        item["name"]
        for item in entry_validations
        if item["metrics"]["inline_link_count"] < 2
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
    for doc in docs.values():
        if doc["kind"] != "formal" or not _is_sentence_style(doc["name"]):
            continue
        for target in doc["links"]:
            target_doc = docs.get(target)
            if target_doc is not None and target_doc["kind"] == "placeholder":
                canonical_gaps[target].add(doc["name"])

    entry_sizes = [
        len(Path(docs[name]["path"]).read_text(encoding="utf-8"))
        for name in data["entries"]
    ]

    return {
        "kb_path": str(root),
        "formal_entry_count": len(data["entries"]),
        "placeholder_count": len(data["placeholders"]),
        "hard_fail_entry_count": len(hard_fail_entries),
        "hard_fail_entries": sorted(hard_fail_entries),
        "missing_why_count": len(missing_why),
        "missing_why_entries": sorted(missing_why),
        "missing_common_pitfalls_count": len(missing_pitfalls),
        "missing_common_pitfalls_entries": sorted(missing_pitfalls),
        "weak_inline_link_count": len(weak_inline_links),
        "weak_inline_link_entries": sorted(weak_inline_links),
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
    }


def prepare_explore_context(
    question: str,
    kb_path: str | Path | None = None,
    inventory_data: dict[str, Any] | None = None,
    shortlist_limit: int = 8,
    neighbor_depth: int = 2,
    max_context_entries: int = 12,
    max_snippets_per_entry: int = 2,
    snippet_char_limit: int = 320,
) -> dict[str, Any]:
    data = inventory_data or inventory(kb_path)
    seeds = shortlist(question, inventory_data=data, limit=shortlist_limit)
    seed_names = [item["name"] for item in seeds]
    expanded = neighbors(
        seed_names,
        inventory_data=data,
        depth=neighbor_depth,
        limit=max_context_entries,
    )
    candidate_names = [item["name"] for item in expanded]
    snippet_map = snippets(
        candidate_names,
        question=question,
        inventory_data=data,
        max_snippets_per_entry=max_snippets_per_entry,
        snippet_char_limit=snippet_char_limit,
    )

    return {
        "inventory_overview": {
            "formal_entry_count": len(data["entries"]),
            "placeholder_count": len(data["placeholders"]),
            "alias_count": len(data["aliases"]),
        },
        "initial_shortlist": seeds,
        "expanded_candidates": expanded,
        "candidate_snippets": snippet_map,
    }


def _parse_doc(path: Path, kind: str) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)
    aliases = frontmatter.get("aliases") or []
    if not isinstance(aliases, list):
        aliases = []
    actual_kind = (
        "placeholder"
        if kind == "placeholder" or frontmatter.get("status") == "placeholder"
        else "formal"
    )

    return {
        "name": path.stem,
        "path": str(path),
        "kind": actual_kind,
        "aliases": [str(alias).strip() for alias in aliases if str(alias).strip()],
        "summary": _extract_summary(body),
        "links": graph_links_from_text(body, kind=actual_kind),
        "body": body,
        "sections": list(_parse_sections(body)[0].keys()),
        "is_canonical": actual_kind != "placeholder" and not _is_sentence_style(path.stem),
    }


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not match:
        return {}, text
    payload = yaml.safe_load(match.group(1)) or {}
    if not isinstance(payload, dict):
        payload = {}
    return payload, text[match.end() :]


def _parse_sections(body: str) -> tuple[dict[str, str], str]:
    current = "__preamble__"
    buckets: dict[str, list[str]] = defaultdict(list)
    for line in body.splitlines():
        heading = HEADING_PATTERN.match(line.strip())
        if heading:
            current = heading.group(1).strip()
            continue
        buckets[current].append(line)

    preamble = "\n".join(buckets.pop("__preamble__", [])).strip()
    sections = {name: "\n".join(lines).strip() for name, lines in buckets.items()}
    return sections, preamble


def _extract_summary(body: str) -> str:
    cleaned = re.sub(r"^#{1,6}\s+[^\n]+\n?", "", body, flags=re.MULTILINE).strip()
    blocks = re.split(r"\n\s*\n", cleaned)
    for block in blocks:
        text = _compress_whitespace(block)
        if not text:
            continue
        if text.startswith("#status/placeholder"):
            continue
        if text.startswith("- [ ] Needs human or agent"):
            continue
        if text.startswith("## "):
            continue
        return _truncate(_first_sentences(text, 2), 260)
    return ""


def _extract_links(text: str) -> list[str]:
    links = []
    for raw in LINK_PATTERN.findall(text):
        target = raw.split("|")[0].split("#")[0].strip()
        if target:
            links.append(target)
    return list(dict.fromkeys(links))


def _extract_terms(question: str) -> list[str]:
    results = []
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,24}", question):
        for part in re.split(r"[和与及、/]", token.strip()):
            part = part.strip()
            if len(part) < 2 or part in STOP_WORDS:
                continue
            if part not in results:
                results.append(part)
    return results


def _incoming_neighbors(name: str, docs: dict[str, dict[str, Any]]) -> set[str]:
    return {doc_name for doc_name, doc in docs.items() if name in doc["links"]}


def _candidate_passages(doc: dict[str, Any]) -> list[tuple[str, str]]:
    sections, preamble = _parse_sections(doc["body"])
    passages = []
    if preamble:
        passages.append(("Summary", preamble))
    for section, content in sections.items():
        if not content:
            continue
        if section == "Source":
            continue
        passages.append((section, content))
    return passages


def _score_passage(section: str, passage: str, terms: list[str]) -> int:
    score = 5
    if section == "Why This Matters":
        score += 10
    if section == "Common Pitfalls":
        score += 8
    if section == "Evidence / Reasoning":
        score += 8
    lowered = passage.lower()
    for term in terms:
        if term.lower() in lowered:
            score += 20
    return score


def _is_substantive(text: str) -> bool:
    if not text:
        return False
    bullets = [line for line in text.splitlines() if line.strip().startswith(("-", "*"))]
    compact = re.sub(r"\s+", "", re.sub(r"\[\[[^\]]+\]\]", "", text))
    return len(compact) >= 40 or len(bullets) >= 2


def _count_inline_links(body: str) -> int:
    lines = []
    current_section = None
    for line in body.splitlines():
        heading = HEADING_PATTERN.match(line.strip())
        if heading:
            current_section = heading.group(1).strip()
            continue
        if current_section in {"Related", "Source"}:
            continue
        lines.append(line)
    return len(_extract_links("\n".join(lines)))


def _is_sentence_style(title: str) -> bool:
    return len(title) > 4 and any(marker in title for marker in SENTENCE_STYLE_MARKERS)


def _looks_like_lesson(summary: str) -> bool:
    return any(
        marker in summary.lower()
        for marker in ("must", "should", "avoid", "when ", "if ", "否则", "避免", "应", "需")
    )


def _first_sentences(text: str, limit: int) -> str:
    sentences = [segment.strip() for segment in re.split(r"[。！？]", text) if segment.strip()]
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


def _read_json_arg(path: str | None) -> dict[str, Any]:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.load(sys.stdin)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic KB query helpers for Sediment")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("kb_path")

    shortlist_parser = subparsers.add_parser("shortlist")
    shortlist_parser.add_argument("kb_path")
    shortlist_parser.add_argument("question")
    shortlist_parser.add_argument("--limit", type=int, default=8)

    neighbors_parser = subparsers.add_parser("neighbors")
    neighbors_parser.add_argument("kb_path")
    neighbors_parser.add_argument("names", nargs="+")
    neighbors_parser.add_argument("--depth", type=int, default=2)
    neighbors_parser.add_argument("--limit", type=int, default=12)

    snippets_parser = subparsers.add_parser("snippets")
    snippets_parser.add_argument("kb_path")
    snippets_parser.add_argument("names", nargs="+")
    snippets_parser.add_argument("--question", default="")
    snippets_parser.add_argument("--max-snippets-per-entry", type=int, default=2)
    snippets_parser.add_argument("--snippet-char-limit", type=int, default=320)

    validate_answer_parser = subparsers.add_parser("validate-answer")
    validate_answer_parser.add_argument("kb_path")
    validate_answer_parser.add_argument("--json-file")

    validate_entry_parser = subparsers.add_parser("validate-entry")
    validate_entry_parser.add_argument("entry_path")

    audit_parser = subparsers.add_parser("audit-kb")
    audit_parser.add_argument("kb_path")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "inventory":
        payload = inventory(args.kb_path)
    elif args.command == "shortlist":
        payload = shortlist(args.question, kb_path=args.kb_path, limit=args.limit)
    elif args.command == "neighbors":
        payload = neighbors(args.names, kb_path=args.kb_path, depth=args.depth, limit=args.limit)
    elif args.command == "snippets":
        payload = snippets(
            args.names,
            question=args.question,
            kb_path=args.kb_path,
            max_snippets_per_entry=args.max_snippets_per_entry,
            snippet_char_limit=args.snippet_char_limit,
        )
    elif args.command == "validate-answer":
        payload = validate_answer(_read_json_arg(args.json_file), kb_path=args.kb_path)
    elif args.command == "validate-entry":
        payload = validate_entry(path=args.entry_path)
    elif args.command == "audit-kb":
        payload = audit_kb(args.kb_path)
    else:
        parser.error(f"unknown command: {args.command}")
        return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
