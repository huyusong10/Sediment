from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any

from mcp_server.i18n import query_language_rules
from mcp_server.kb import (
    ParsedEntry,
    RetrievalCandidate,
    SelectedPassage,
)
from mcp_server.kb import (
    audit_kb as core_audit_kb,
)
from mcp_server.kb import (
    inventory as core_inventory,
)
from mcp_server.kb import (
    validate_entry as core_validate_entry,
)

LANGUAGE_RULES = query_language_rules()


def inventory(kb_path: str | Path) -> dict[str, Any]:
    return core_inventory(kb_path)


def shortlist(
    question: str,
    kb_path: str | Path | None = None,
    inventory_data: dict[str, Any] | None = None,
    limit: int = 8,
    preferred_entries: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    data = inventory_data or inventory(kb_path)
    entries = _entry_objects(data)
    preferred = set(preferred_entries or [])
    question_lower = question.lower()
    question_mode = _question_mode(question)
    terms = _extract_terms(question)
    results: list[RetrievalCandidate] = []

    for entry in entries.values():
        evidence_score = 0
        matched_terms: list[str] = []
        matched_fields: set[str] = set()
        reason_bits: list[str] = []
        lowered_aliases = [alias.lower() for alias in entry.aliases]

        if entry.name.lower() in question_lower:
            evidence_score += 120
            matched_terms.append(entry.name)
            matched_fields.add("name")
            reason_bits.append("name exact match")

        for alias in entry.aliases:
            if alias.lower() in question_lower:
                evidence_score += 90
                matched_terms.append(alias)
                matched_fields.add("alias")
                reason_bits.append(f"alias match: {alias}")

        for term in terms:
            term_lower = term.lower()
            if term_lower in entry.name.lower():
                evidence_score += 70
                matched_terms.append(term)
                matched_fields.add("name")
            if any(term_lower in alias for alias in lowered_aliases):
                evidence_score += 50
                matched_terms.append(term)
                matched_fields.add("alias")
            if term_lower in entry.summary.lower():
                evidence_score += 24
                matched_fields.add("summary")
            elif term_lower in entry.search_text.lower():
                evidence_score += 10
                matched_fields.add("body")

        if evidence_score <= 0 and entry.name not in preferred:
            continue

        score = evidence_score + min(entry.inbound_count, 8)
        if entry.kind == "placeholder":
            score -= 22
        elif entry.entry_type == "concept":
            score += 12
        else:
            score += 4

        if question_mode == "definition" and entry.entry_type == "concept":
            score += 22
        if question_mode == "guidance" and entry.entry_type == "lesson":
            score += 22
        if question_mode == "risk" and entry.entry_type == "lesson":
            score += 22

        if entry.name in preferred:
            score += 45
            matched_fields.add("index")
            reason_bits.append("index-routed candidate")

        if score <= 0:
            continue

        results.append(
            RetrievalCandidate(
                name=entry.name,
                kind=entry.kind,
                entry_type=entry.entry_type,
                status=entry.status,
                score=score,
                matched_terms=tuple(sorted(set(matched_terms))),
                matched_fields=tuple(sorted(matched_fields)),
                selection_reason=_selection_reason(reason_bits, entry, question_mode),
                summary=entry.summary,
                is_canonical=entry.is_canonical,
            )
        )

    results.sort(key=lambda item: (-item.score, item.name))
    return [item.to_record() for item in results[:limit]]


def neighbors(
    names: list[str] | tuple[str, ...],
    kb_path: str | Path | None = None,
    inventory_data: dict[str, Any] | None = None,
    depth: int = 2,
    limit: int = 12,
) -> list[dict[str, Any]]:
    data = inventory_data or inventory(kb_path)
    entries = _entry_objects(data)
    queue = deque()
    visited: dict[str, dict[str, Any]] = {}

    for name in names:
        if name in entries:
            queue.append((name, 0, None))

    while queue and len(visited) < limit:
        current, current_depth, via = queue.popleft()
        if current in visited and visited[current]["depth"] <= current_depth:
            continue

        entry = entries[current]
        visited[current] = {
            "name": current,
            "depth": current_depth,
            "via": via,
            "kind": entry.kind,
            "entry_type": entry.entry_type,
            "status": entry.status,
            "summary": entry.summary,
            "is_canonical": entry.is_canonical,
            "selection_reason": "shortlist seed" if via is None else f"graph neighbor via {via}",
        }

        if current_depth >= depth:
            continue

        next_targets = sorted(set(entry.graph_links) | _incoming_neighbors(current, entries))
        for target in next_targets:
            if target in entries:
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
    entries = _entry_objects(data)
    terms = _extract_terms(question)
    focus = _question_focus(question)
    result: dict[str, dict[str, Any]] = {}

    for name in names:
        entry = entries.get(name)
        if entry is None:
            continue

        scored: list[SelectedPassage] = []
        for section, passage in _candidate_passages(entry):
            score, reason = _score_passage(entry, section, passage, terms, focus)
            scored.append(
                SelectedPassage(
                    name=entry.name,
                    kind=entry.kind,
                    entry_type=entry.entry_type,
                    status=entry.status,
                    section=section,
                    text=_truncate(passage, snippet_char_limit),
                    score=score,
                    selection_reason=reason,
                )
            )

        scored.sort(key=lambda item: (-item.score, item.section))
        result[name] = {
            "kind": entry.kind,
            "entry_type": entry.entry_type,
            "status": entry.status,
            "title": entry.title,
            "summary": entry.summary,
            "aliases": list(entry.aliases),
            "links": list(entry.graph_links),
            "snippets": [item.to_record() for item in scored[:max_snippets_per_entry]],
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
    elif normalized["confidence"] in {"high", "medium"} and not normalized["sources"]:
        errors.append("high/medium confidence answers must cite at least one source")

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
    return core_validate_entry(path=path, text=text, name=name, kind=kind)


def audit_kb(kb_path: str | Path) -> dict[str, Any]:
    return core_audit_kb(kb_path)


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
    routed_indexes = route_indexes(question, inventory_data=data)
    preferred_entries = _preferred_entries_from_indexes(routed_indexes, data)
    seeds = shortlist(
        question,
        inventory_data=data,
        limit=shortlist_limit,
        preferred_entries=preferred_entries,
    )
    if not seeds and preferred_entries:
        fallback_seeds = []
        docs = data.get("docs", {})
        for name in preferred_entries[:shortlist_limit]:
            doc = docs.get(name)
            if doc is None:
                continue
            fallback_seeds.append(
                {
                    "name": name,
                    "kind": doc["kind"],
                    "entry_type": doc["entry_type"],
                    "status": doc["status"],
                    "score": 1,
                    "matched_terms": [],
                    "matched_fields": ["index"],
                    "selection_reason": "index-only routing fallback",
                    "summary": doc["summary"],
                    "is_canonical": doc["is_canonical"],
                }
            )
        seeds = fallback_seeds
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
            "index_count": len(data.get("indexes", [])),
            "concept_entry_count": sum(
                1 for name in data["entries"] if data["docs"][name]["entry_type"] == "concept"
            ),
            "lesson_entry_count": sum(
                1 for name in data["entries"] if data["docs"][name]["entry_type"] == "lesson"
            ),
        },
        "question_analysis": {
            "mode": _question_mode(question),
            "focus": _question_focus(question),
            "terms": _extract_terms(question),
        },
        "initial_shortlist": seeds,
        "index_routing": {
            "strategy": "index-first-with-open-search",
            "root_index_present": "index.root" in set(data.get("indexes", [])),
            "selected_indexes": routed_indexes,
            "preferred_entries": preferred_entries,
        },
        "expanded_candidates": expanded,
        "candidate_snippets": snippet_map,
    }


def route_indexes(
    question: str,
    kb_path: str | Path | None = None,
    inventory_data: dict[str, Any] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    data = inventory_data or inventory(kb_path)
    index_docs = data.get("index_docs", {})
    if not index_docs:
        return []

    terms = _extract_terms(question)
    lowered_question = question.lower()
    results = []
    for name, item in index_docs.items():
        score = 0
        reasons = []
        haystacks = [
            name.lower(),
            str(item.get("title", "")).lower(),
            str(item.get("summary", "")).lower(),
        ]
        if name == "index.root":
            score += 10
            reasons.append("root bootstrap")
        for term in terms:
            term_lower = term.lower()
            if any(term_lower in bucket for bucket in haystacks):
                score += 22
                reasons.append(f"term match: {term}")
            linked_hits = sum(
                1 for linked in item.get("links", []) if term_lower in linked.lower()
            )
            if linked_hits:
                score += 8 * linked_hits
                reasons.append(f"link hit: {term} x{linked_hits}")
        if score <= 0 and any(term in lowered_question for term in (name.lower(),)):
            score += 12
            reasons.append("name mention")
        if score <= 0:
            continue
        results.append(
            {
                "name": name,
                "score": score,
                "selection_reason": "; ".join(dict.fromkeys(reasons)) or "heuristic match",
                "links": item.get("links", []),
                "segment": item.get("segment", name),
            }
        )
    results.sort(key=lambda value: (-value["score"], value["name"]))
    return results[:limit]


def _preferred_entries_from_indexes(
    routed_indexes: list[dict[str, Any]],
    data: dict[str, Any],
) -> list[str]:
    known_entries = set(data.get("docs", {}))
    index_docs = data.get("index_docs", {})
    preferred = []
    for item in routed_indexes:
        for target in item.get("links", []):
            if target in known_entries and target not in preferred:
                preferred.append(target)
                continue
            linked_index = index_docs.get(target)
            if not linked_index:
                continue
            for nested in linked_index.get("links", []):
                if nested in known_entries and nested not in preferred:
                    preferred.append(nested)
    return preferred


def _entry_objects(data: dict[str, Any]) -> dict[str, ParsedEntry]:
    return data.get("entry_objects", {})


def _extract_terms(question: str) -> list[str]:
    languages = _active_languages(question)
    stop_words = _merged_stop_words(languages)
    split_pattern = _merged_split_pattern(languages)
    results = []
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,24}", question):
        for part in re.split(split_pattern, token.strip()):
            part = part.strip()
            if len(part) < 2 or part.casefold() in stop_words:
                continue
            if part not in results:
                results.append(part)
    return results


def _incoming_neighbors(name: str, entries: dict[str, ParsedEntry]) -> set[str]:
    return {entry_name for entry_name, entry in entries.items() if name in entry.graph_links}


def _candidate_passages(entry: ParsedEntry) -> list[tuple[str, str]]:
    passages = []
    if entry.summary:
        passages.append(("Summary", entry.summary))
    for section, content in entry.sections.items():
        if content and section != "Source":
            passages.append((section, content))
    return passages


def _score_passage(
    entry: ParsedEntry,
    section: str,
    passage: str,
    terms: list[str],
    focus: str,
) -> tuple[int, str]:
    score = 5
    reason_parts = []
    if section == "Summary":
        score += 10
        reason_parts.append("summary")

    focus_bonuses: dict[str, int]
    if entry.entry_type == "concept":
        focus_bonuses = {
            "Summary": 26 if focus in {"definition", "comparison"} else 14,
            "Scope": 24 if focus in {"definition", "scope"} else 16,
            "Related": 2,
        }
    else:
        focus_bonuses = {
            "Summary": 12,
            "Trigger": 18,
            "Why": 18,
            "Risks": 16,
            "Related": 2,
        }
        if focus == "why":
            focus_bonuses.update({"Why": 32, "Trigger": 16, "Risks": 14})
        elif focus == "when":
            focus_bonuses.update({"Trigger": 32, "Why": 16, "Risks": 14})
        elif focus == "risk":
            focus_bonuses.update({"Risks": 32, "Why": 18, "Trigger": 14})
        elif focus in {"definition", "scope"}:
            focus_bonuses.update({"Summary": 14, "Trigger": 12, "Why": 12, "Risks": 10})

    score += focus_bonuses.get(section, 0)
    if focus_bonuses.get(section, 0):
        reason_parts.append(f"{focus}-preferred section")

    lowered = passage.lower()
    term_hits = 0
    for term in terms:
        if term.lower() in lowered:
            term_hits += 1
            score += 20
    if term_hits:
        reason_parts.append(f"{term_hits} term hit(s)")

    if entry.kind == "placeholder":
        score -= 10
        reason_parts.append("placeholder penalty")

    return score, ", ".join(reason_parts) or "generic relevance"


def _selection_reason(reason_bits: list[str], entry: ParsedEntry, question_mode: str) -> str:
    parts = list(dict.fromkeys(reason_bits))
    if entry.entry_type == "concept" and question_mode == "definition":
        parts.append("concept favored for definition query")
    if entry.entry_type == "lesson" and question_mode in {"guidance", "risk"}:
        parts.append("lesson favored for operational query")
    if entry.kind == "placeholder":
        parts.append("placeholder retained as gap evidence")
    return "; ".join(parts) or "lexical evidence"


def _question_focus(question: str) -> str:
    languages = _active_languages(question)
    lowered = question.lower()
    for focus in ("definition", "scope", "why", "when", "risk", "comparison", "guidance"):
        if _match_focus_marker(question, lowered, focus, languages):
            return focus
    return "open"


def _question_mode(question: str) -> str:
    focus = _question_focus(question)
    if focus in {"definition", "scope"}:
        return "definition"
    if focus in {"why", "when", "guidance"}:
        return "guidance"
    if focus == "risk":
        return "risk"
    if focus == "comparison":
        return "comparison"
    return "open"


def _active_languages(question: str) -> tuple[str, ...]:
    override = os.environ.get("SEDIMENT_QUERY_LANGS", "").strip()
    if override:
        requested = tuple(
            lang.strip().lower()
            for lang in override.split(",")
            if lang.strip().lower() in LANGUAGE_RULES
        )
        if requested:
            return requested
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", question))
    has_latin = bool(re.search(r"[A-Za-z]", question))
    if has_cjk and has_latin:
        return ("zh", "en")
    if has_cjk:
        return ("zh",)
    return ("en",) if has_latin else ("zh", "en")


def _merged_stop_words(languages: tuple[str, ...]) -> set[str]:
    words: set[str] = set()
    for lang in languages:
        for item in LANGUAGE_RULES[lang]["stop_words"]:
            words.add(str(item).casefold())
    return words


def _merged_split_pattern(languages: tuple[str, ...]) -> str:
    patterns = [LANGUAGE_RULES[lang]["token_splitter"] for lang in languages]
    return "|".join(f"(?:{pattern})" for pattern in patterns)


def _match_focus_marker(
    question: str,
    lowered_question: str,
    focus: str,
    languages: tuple[str, ...],
) -> bool:
    for lang in languages:
        markers = LANGUAGE_RULES[lang]["focus_markers"].get(focus, ())
        for marker in markers:
            if lang == "en":
                if marker in lowered_question:
                    return True
            elif marker in question:
                return True
    return False


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


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
