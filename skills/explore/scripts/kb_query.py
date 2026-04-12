from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from skills.tidy.scripts.tidy_utils import (
    count_placeholder_refs,
    extract_wikilinks,
    find_dangling_links,
    find_orphan_entries,
    graph_links_from_text,
    graph_relevant_text,
    split_frontmatter,
    split_sections,
)

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
FORMAL_ENTRY_TYPES = {"concept", "lesson"}
VALID_STATUSES = {"fact", "inferred", "disputed"}


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

    entries = sorted(name for name, doc in docs.items() if doc["kind"] == "formal")
    placeholders = sorted(name for name, doc in docs.items() if doc["kind"] == "placeholder")
    canonical_entries = sorted(
        name for name, doc in docs.items() if doc["kind"] == "formal" and doc["is_canonical"]
    )

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
    question_mode = _question_mode(question)
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
                evidence_score += 20
            if term_lower in doc["search_text"].lower():
                evidence_score += 8

        if evidence_score <= 0:
            continue

        score += evidence_score
        score += min(doc["inbound_count"], 8)

        if doc["kind"] == "placeholder":
            score -= 22
        elif doc["entry_type"] == "concept":
            score += 12
        else:
            score += 4

        if question_mode == "definition" and doc["entry_type"] == "concept":
            score += 22
        if question_mode in {"guidance", "risk"} and doc["entry_type"] == "lesson":
            score += 22

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
        if name in docs:
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
            if target in docs:
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

        scored = []
        for section, passage in _candidate_passages(doc):
            score = _score_passage(doc["entry_type"], section, passage, terms)
            scored.append((score, section, _truncate(passage, snippet_char_limit)))

        scored.sort(key=lambda item: (-item[0], item[1]))
        result[name] = {
            "kind": doc["kind"],
            "summary": doc["summary"],
            "aliases": doc["aliases"],
            "links": doc["links"],
            "snippets": [
                {"section": section, "text": passage}
                for _, section, passage in scored[:max_snippets_per_entry]
            ],
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

    frontmatter, body = split_frontmatter(text)
    sections, _ = split_sections(body)
    entry_type = _infer_entry_type(
        frontmatter=frontmatter,
        fallback_kind=kind or "formal",
        title=name,
        sections=sections,
    )
    actual_kind = "placeholder" if entry_type == "placeholder" else "formal"
    summary = _extract_summary(body)
    related_links = extract_wikilinks(sections.get("Related", ""))
    sources = _normalize_sources(frontmatter.get("sources"))
    hard_failures = []
    warnings = []

    raw_type = str(frontmatter.get("type", "")).strip()
    if raw_type != entry_type:
        hard_failures.append(f"frontmatter.type must be '{entry_type}'")

    if entry_type == "placeholder":
        if not summary:
            hard_failures.append("placeholder must contain a gap description in the body")
    else:
        status = str(frontmatter.get("status", "")).strip()
        if status not in VALID_STATUSES:
            hard_failures.append(
                "formal entry must declare frontmatter.status as fact, inferred, or disputed"
            )
        if not sources:
            hard_failures.append("formal entry must declare at least one frontmatter.sources item")
        if not summary:
            hard_failures.append("entry must contain a substantive summary/core proposition")

    if entry_type == "concept":
        if not _is_substantive(sections.get("Scope", "")):
            hard_failures.append("concept entry must include a substantive Scope section")
        if not related_links:
            hard_failures.append("concept entry must include at least one Related wikilink")
    elif entry_type == "lesson":
        for section_name in ("Trigger", "Why", "Risks"):
            if not _is_substantive(sections.get(section_name, "")):
                hard_failures.append(
                    f"lesson entry must include a substantive {section_name} section"
                )
        if not related_links:
            hard_failures.append("lesson entry must include at least one Related wikilink")

    if sources and len(sources) != len(set(sources)):
        warnings.append("frontmatter.sources contains duplicate entries")
    if summary and len(summary) > 220:
        warnings.append("summary is longer than the preferred queryable size")

    return {
        "name": name,
        "kind": actual_kind,
        "entry_type": entry_type,
        "valid": not hard_failures,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "metrics": {
            "summary_length": len(summary),
            "related_link_count": len(related_links),
            "source_count": len(sources),
        },
    }


def audit_kb(kb_path: str | Path) -> dict[str, Any]:
    root = Path(kb_path)
    data = inventory(root)
    docs = data["docs"]

    entry_validations = []
    for name in data["entries"]:
        doc = docs[name]
        entry_validations.append(validate_entry(path=doc["path"], kind="formal", name=name))

    hard_fail_entries = [item["name"] for item in entry_validations if item["hard_failures"]]
    missing_scope = [
        item["name"]
        for item in entry_validations
        if "concept entry must include a substantive Scope section" in item["hard_failures"]
    ]
    missing_trigger = [
        item["name"]
        for item in entry_validations
        if "lesson entry must include a substantive Trigger section" in item["hard_failures"]
    ]
    missing_why = [
        item["name"]
        for item in entry_validations
        if "lesson entry must include a substantive Why section" in item["hard_failures"]
    ]
    missing_risks = [
        item["name"]
        for item in entry_validations
        if "lesson entry must include a substantive Risks section" in item["hard_failures"]
    ]
    weak_related = [
        item["name"]
        for item in entry_validations
        if item["metrics"]["related_link_count"] == 0
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
        if doc["kind"] != "formal":
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
        "concept_entry_count": sum(
            1 for name in data["entries"] if docs[name]["entry_type"] == "concept"
        ),
        "lesson_entry_count": sum(
            1 for name in data["entries"] if docs[name]["entry_type"] == "lesson"
        ),
        "placeholder_count": len(data["placeholders"]),
        "hard_fail_entry_count": len(hard_fail_entries),
        "hard_fail_entries": sorted(hard_fail_entries),
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
            "concept_entry_count": sum(
                1 for name in data["entries"] if data["docs"][name]["entry_type"] == "concept"
            ),
            "lesson_entry_count": sum(
                1 for name in data["entries"] if data["docs"][name]["entry_type"] == "lesson"
            ),
        },
        "initial_shortlist": seeds,
        "expanded_candidates": expanded,
        "candidate_snippets": snippet_map,
    }


def _parse_doc(path: Path, kind: str) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(content)
    sections, _ = split_sections(body)
    aliases = frontmatter.get("aliases") or []
    if not isinstance(aliases, list):
        aliases = []

    entry_type = _infer_entry_type(
        frontmatter=frontmatter,
        fallback_kind=kind,
        title=path.stem,
        sections=sections,
    )
    actual_kind = "placeholder" if entry_type == "placeholder" else "formal"

    return {
        "name": path.stem,
        "path": str(path),
        "kind": actual_kind,
        "entry_type": entry_type,
        "status": str(frontmatter.get("status", "")).strip(),
        "aliases": [str(alias).strip() for alias in aliases if str(alias).strip()],
        "sources": _normalize_sources(frontmatter.get("sources")),
        "summary": _extract_summary(body),
        "links": graph_links_from_text(content, kind=actual_kind),
        "body": body,
        "sections_map": sections,
        "sections": list(sections.keys()),
        "search_text": graph_relevant_text(content, kind=actual_kind),
        "is_canonical": entry_type == "concept",
    }


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


def _normalize_sources(raw_sources: Any) -> list[str]:
    if not isinstance(raw_sources, list):
        return []
    return [str(item).strip() for item in raw_sources if str(item).strip()]


def _extract_summary(body: str) -> str:
    _, preamble = split_sections(body)
    if preamble:
        return _truncate(_first_sentences(_compress_whitespace(preamble), 2), 260)

    for block in re.split(r"\n\s*\n", body):
        text = _compress_whitespace(block)
        if not text or text.startswith("## "):
            continue
        return _truncate(_first_sentences(text, 2), 260)
    return ""


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
    passages = []
    if doc["summary"]:
        passages.append(("Summary", doc["summary"]))
    for section, content in doc["sections_map"].items():
        if content and section != "Source":
            passages.append((section, content))
    return passages


def _score_passage(entry_type: str, section: str, passage: str, terms: list[str]) -> int:
    score = 5
    if entry_type == "concept" and section == "Scope":
        score += 12
    if entry_type == "lesson" and section in {"Trigger", "Why", "Risks"}:
        score += 12
    lowered = passage.lower()
    for term in terms:
        if term.lower() in lowered:
            score += 20
    return score


def _question_mode(question: str) -> str:
    lowered = question.lower()
    if any(marker in question for marker in ("什么是", "定义", "含义")):
        return "definition"
    if any(marker in question for marker in ("为什么", "原因", "为何")):
        return "guidance"
    if any(marker in question for marker in ("风险", "坑", "误区", "避免")):
        return "risk"
    if "how" in lowered or "when" in lowered:
        return "guidance"
    return "open"


def _is_substantive(text: str) -> bool:
    if not text:
        return False
    compact = re.sub(r"\s+", "", re.sub(r"\[\[[^\]]+\]\]", "", text))
    bullets = [line for line in text.splitlines() if line.strip().startswith(("-", "*"))]
    return len(compact) >= 20 or len(bullets) >= 1


def _is_sentence_style(title: str) -> bool:
    return len(title) > 4 and any(marker in title for marker in SENTENCE_STYLE_MARKERS)


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
