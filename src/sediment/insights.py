from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_LANGUAGES = {"en", "zh"}
DEFAULT_KB_LANGUAGE = "en"

_INTENT_MARKERS = {
    "zh": {
        "workflow": ("流程", "步骤", "如何", "怎么", "路径", "入职", "上手"),
        "relation": ("关系", "联系", "相关", "依赖"),
        "risk": ("风险", "为什么不能", "为什么不", "故障", "失败", "边界"),
        "comparison": ("区别", "对比", "比较", "差异", "vs"),
    },
    "en": {
        "workflow": ("workflow", "process", "steps", "how", "onboard", "onboarding"),
        "relation": ("relation", "relationship", "related", "dependency"),
        "risk": ("risk", "failure", "incident", "danger", "boundary", "why not"),
        "comparison": ("compare", "comparison", "difference", "vs"),
    },
}
_QUERY_PREFIXES = {
    "zh": (
        "什么是",
        "是什么",
        "有哪些",
        "如何",
        "怎么",
        "为什么",
        "是否",
        "能否",
        "请问",
        "根据",
        "综合",
    ),
    "en": (
        "what is",
        "what are",
        "how to",
        "how do",
        "how can",
        "why is",
        "why do",
        "can",
        "should",
        "please",
        "based on",
    ),
}
_QUERY_FILLERS = {
    "zh": ("完整", "当前", "默认", "一下", "一下子", "到底", "到底是"),
    "en": ("current", "default", "full", "complete", "overall", "please"),
}
_WORKFLOW_SUFFIX = {"zh": "流程", "en": "workflow"}
_LESSON_SUFFIX = {"zh": "经验", "en": "lesson"}


def normalize_language(value: str | None) -> str:
    token = str(value or "").strip().lower()
    if token.startswith("zh"):
        return "zh"
    if token.startswith("en"):
        return "en"
    return DEFAULT_KB_LANGUAGE


def detect_query_language(query: str, *, default_language: str = DEFAULT_KB_LANGUAGE) -> str:
    text = str(query or "")
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_cjk and not has_latin:
        return "zh"
    if has_latin and not has_cjk:
        return "en"
    if has_cjk and has_latin:
        return "zh"
    return normalize_language(default_language)


def normalize_query_for_kb(query: str, *, kb_language: str) -> str:
    # v1 keeps query text intact and only normalizes whitespace/punctuation.
    # This provides a stable contract without introducing opaque translation.
    text = re.sub(r"\s+", " ", str(query or "")).strip()
    if kb_language == "zh":
        return text.replace("?", "？")
    return text


def detect_intent(query: str, *, language: str | None = None) -> str:
    lang = normalize_language(language or detect_query_language(query))
    lowered = str(query or "").strip().lower()
    raw = str(query or "")
    for intent in ("workflow", "comparison", "relation", "risk"):
        markers = _INTENT_MARKERS[lang][intent]
        if lang == "zh":
            if any(marker in raw for marker in markers):
                return intent
        else:
            if any(marker in lowered for marker in markers):
                return intent
    return "definition"


def normalize_subject(query: str, *, language: str | None = None) -> str:
    lang = normalize_language(language or detect_query_language(query))
    text = re.sub(r"\s+", " ", str(query or "")).strip().strip("?.!？！。")
    lowered = text.lower()
    for prefix in _QUERY_PREFIXES[lang]:
        if lang == "zh":
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
        elif lowered.startswith(prefix):
            text = text[len(prefix) :].strip()
            lowered = text.lower()
    for filler in _QUERY_FILLERS[lang]:
        if lang == "zh":
            text = text.replace(filler, "")
        else:
            text = re.sub(rf"\b{re.escape(filler)}\b", " ", text, flags=re.IGNORECASE)
    if lang == "zh":
        text = re.sub(r"(是什么|有哪些|怎么做|如何做|为什么|是否|能否)$", "", text)
    else:
        text = re.sub(
            r"\b(what|is|are|how|to|do|does|why|can|should|the|a|an)\b",
            " ",
            text,
            flags=re.IGNORECASE,
        )
    text = re.sub(r"[\s\-_/]+", " ", text).strip(" ，,;；:：")
    return text or str(query or "").strip()


def build_cluster_key(*, language: str, intent: str, normalized_subject: str) -> str:
    subject = normalize_subject(normalized_subject or "", language=language)
    fingerprint = subject.casefold().replace(" ", "-")
    if not fingerprint:
        fingerprint = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:12]
    return f"{normalize_language(language)}::{intent.strip().lower() or 'definition'}::{fingerprint}"


def fingerprint_actor(*parts: str | None) -> str:
    payload = "|".join(str(part or "").strip() for part in parts if str(part or "").strip())
    if not payload:
        return ""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_demand_score(
    *,
    signal_count: int,
    unique_actor_count: int,
    last_seen_at: str | None,
) -> float:
    count_score = min(max(signal_count, 0) / 5.0, 1.0) * 0.5
    actor_score = min(max(unique_actor_count, 0) / 3.0, 1.0) * 0.3
    recency_score = 0.0
    if last_seen_at:
        try:
            observed = datetime.fromisoformat(last_seen_at)
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            age_days = max(
                (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
                / 86400.0,
                0.0,
            )
            if age_days <= 7:
                recency_score = 0.2
            elif age_days <= 30:
                recency_score = 0.12
            else:
                recency_score = 0.05
        except ValueError:
            recency_score = 0.05
    return round(min(count_score + actor_score + recency_score, 1.0), 3)


def compute_maturity_score(
    *,
    signal_count: int,
    unique_actor_count: int,
    source_entries: list[str],
    mode: str,
    normalized_subject: str,
) -> float:
    source_count = len({str(item).strip() for item in source_entries if str(item).strip()})
    source_score = min(source_count / 3.0, 1.0) * 0.45
    mode_score = {"direct": 0.3, "synthesized": 0.25, "gap": 0.0}.get(mode, 0.1)
    subject_score = 0.15 if normalized_subject.strip() else 0.0
    stability_score = 0.1 if signal_count >= 3 else 0.04
    collaboration_score = 0.05 if unique_actor_count >= 2 else 0.0
    return round(
        min(source_score + mode_score + subject_score + stability_score + collaboration_score, 1.0),
        3,
    )


def cluster_state(
    *,
    signal_count: int,
    unique_actor_count: int,
    source_entries: list[str],
    demand_score: float,
    maturity_score: float,
    insight_id: str | None = None,
) -> str:
    if insight_id:
        return "materialized"
    if is_ready_for_materialization(
        signal_count=signal_count,
        unique_actor_count=unique_actor_count,
        source_entries=source_entries,
        demand_score=demand_score,
        maturity_score=maturity_score,
    ):
        return "ready"
    if signal_count >= 2:
        return "clustered"
    return "captured"


def is_ready_for_materialization(
    *,
    signal_count: int,
    unique_actor_count: int,
    source_entries: list[str],
    demand_score: float,
    maturity_score: float,
) -> bool:
    unique_sources = {str(item).strip() for item in source_entries if str(item).strip()}
    return (
        signal_count >= 3
        and unique_actor_count >= 2
        and len(unique_sources) >= 2
        and demand_score >= 0.6
        and maturity_score >= 0.6
    )


def infer_insight_kind(*, intent: str) -> str:
    if intent == "workflow":
        return "workflow"
    if intent == "risk":
        return "lesson"
    if intent in {"relation", "comparison"}:
        return "mapping"
    return "concept"


def infer_recommended_action(*, kind: str, supporting_entries: list[str]) -> str:
    if kind == "workflow" and len(supporting_entries) >= 3:
        return "promote"
    if kind in {"concept", "lesson"} and len(supporting_entries) >= 2:
        return "merge"
    return "keep_observing"


def insight_title_from_cluster(
    *,
    normalized_subject: str,
    language: str,
    intent: str,
) -> str:
    subject = normalized_subject.strip() or "Untitled Insight"
    if intent == "workflow":
        suffix = _WORKFLOW_SUFFIX[normalize_language(language)]
        if normalize_language(language) == "zh":
            return subject if subject.endswith(suffix) else f"{subject}{suffix}"
        lowered = subject.lower()
        return subject if suffix in lowered else f"{subject} {suffix}"
    if intent == "risk":
        suffix = _LESSON_SUFFIX[normalize_language(language)]
        if normalize_language(language) == "zh":
            return subject if subject.endswith(suffix) else f"{subject}{suffix}"
        lowered = subject.lower()
        return subject if suffix in lowered else f"{subject} {suffix}"
    return subject


def slugify_filename(value: str) -> str:
    lowered = str(value or "").strip().lower()
    if not lowered:
        return "insight"
    cleaned = re.sub(r"[^\w\s-]", "", lowered, flags=re.UNICODE)
    compact = re.sub(r"[-\s]+", "-", cleaned, flags=re.UNICODE).strip("-")
    return compact or "insight"


def insight_frontmatter(cluster: dict[str, Any], *, insight_id: str, title: str) -> dict[str, Any]:
    supporting_entries = list(dict.fromkeys(cluster.get("source_entries") or []))
    trigger_queries = list(dict.fromkeys(cluster.get("sample_queries") or []))
    kind = str(cluster.get("kind") or infer_insight_kind(intent=str(cluster.get("intent") or "definition")))
    hypothesis = str(cluster.get("hypothesis") or "").strip()
    if not hypothesis:
        hypothesis = f"Formal KB evidence suggests that '{title}' is a stable latent knowledge unit."
    proposed_answer = str(cluster.get("proposed_answer") or "").strip() or str(
        cluster.get("answer_excerpt") or ""
    ).strip()
    return {
        "id": insight_id,
        "title": title,
        "kind": kind,
        "hypothesis": hypothesis,
        "proposed_answer": proposed_answer,
        "supporting_entries": supporting_entries,
        "trigger_queries": trigger_queries,
        "review_state": "proposed",
        "origin": "explore",
    }


def render_insight_markdown(frontmatter: dict[str, Any], *, review_notes: str = "") -> str:
    sections = [
        ("Hypothesis", str(frontmatter.get("hypothesis") or "").strip()),
        ("Proposed Answer", str(frontmatter.get("proposed_answer") or "").strip()),
        (
            "Supporting Entries",
            "\n".join(
                f"- [[{item}]]"
                for item in frontmatter.get("supporting_entries") or []
                if str(item).strip()
            ).strip(),
        ),
        (
            "Trigger Queries",
            "\n".join(
                f"- {item}"
                for item in frontmatter.get("trigger_queries") or []
                if str(item).strip()
            ).strip(),
        ),
        ("Review Notes", review_notes.strip()),
    ]
    body = ["# " + str(frontmatter.get("title") or frontmatter.get("id") or "Insight")]
    for heading, content in sections:
        body.append(f"\n## {heading}\n{content or '-'}")
    yaml_block = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{yaml_block}\n---\n\n" + "\n".join(body).strip() + "\n"


def parse_insight(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    text = source_path.read_text(encoding="utf-8")
    frontmatter: dict[str, Any] = {}
    body = text
    if text.startswith("---\n"):
        try:
            _, raw_frontmatter, remainder = text.split("---\n", 2)
        except ValueError:
            remainder = text
        else:
            loaded = yaml.safe_load(raw_frontmatter) or {}
            if isinstance(loaded, dict):
                frontmatter = loaded
            body = remainder
    sections: dict[str, str] = {}
    current_name = ""
    bucket: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current_name:
                sections[current_name] = "\n".join(bucket).strip()
            current_name = line[3:].strip()
            bucket = []
            continue
        bucket.append(line)
    if current_name:
        sections[current_name] = "\n".join(bucket).strip()
    title = str(frontmatter.get("title") or source_path.stem).strip() or source_path.stem
    return {
        "id": str(frontmatter.get("id") or source_path.stem).strip() or source_path.stem,
        "name": source_path.stem,
        "path": str(source_path),
        "title": title,
        "kind": str(frontmatter.get("kind") or "concept").strip() or "concept",
        "hypothesis": str(frontmatter.get("hypothesis") or sections.get("Hypothesis", "")).strip(),
        "proposed_answer": str(
            frontmatter.get("proposed_answer") or sections.get("Proposed Answer", "")
        ).strip(),
        "supporting_entries": list(frontmatter.get("supporting_entries") or []),
        "trigger_queries": list(frontmatter.get("trigger_queries") or []),
        "review_state": str(frontmatter.get("review_state") or "proposed").strip() or "proposed",
        "origin": str(frontmatter.get("origin") or "explore").strip() or "explore",
        "summary": str(
            frontmatter.get("proposed_answer") or sections.get("Proposed Answer", "")
        ).strip(),
        "sections_map": sections,
        "body": body.strip(),
        "frontmatter": frontmatter,
    }


def validate_insight_content(path: Path, content: str) -> dict[str, Any]:
    try:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8")
        parsed = parse_insight(temp)
    finally:
        temp.unlink(missing_ok=True)
    failures: list[str] = []
    if not parsed["id"]:
        failures.append("insight id must not be empty")
    if not parsed["title"]:
        failures.append("insight title must not be empty")
    if not parsed["kind"]:
        failures.append("insight kind must not be empty")
    if not parsed["review_state"]:
        failures.append("insight review_state must not be empty")
    return {
        "name": parsed["name"],
        "valid": not failures,
        "hard_failures": failures,
        "warnings": [],
        "metrics": {
            "supporting_entry_count": len(parsed["supporting_entries"]),
            "trigger_query_count": len(parsed["trigger_queries"]),
        },
    }
