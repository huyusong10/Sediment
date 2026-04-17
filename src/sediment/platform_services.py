from __future__ import annotations

import base64
import difflib
import hashlib
import io
import ipaddress
import json
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sediment.diagnostics import DiagnosticLogger
from sediment.kb import (
    audit_kb,
    extract_wikilinks,
    index_config,
    inventory,
    resolve_kb_document_path,
    split_frontmatter,
    validate_entry,
    validate_index,
)
from sediment.platform_store import PlatformStore

LOGGER = DiagnosticLogger("platform_services")

FORMAL_STATUSES = {"fact", "inferred", "disputed"}
ALLOWED_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/zip",
    "application/x-zip-compressed",
}
ZIP_MIME_TYPES = {"application/zip", "application/x-zip-compressed"}
SUPPORTED_UPLOAD_SUFFIXES = {".txt", ".md", ".docx", ".pptx"}
SUBMISSION_ANALYSIS_SCHEMA = json.dumps(
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "recommended_title": {"type": "string"},
            "recommended_type": {
                "type": "string",
                "enum": ["concept", "lesson", "feedback"],
            },
            "duplicate_risk": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "committer_action": {
                "type": "string",
                "enum": ["manual_review", "ingest", "merge_or_link"],
            },
            "committer_note": {"type": "string"},
            "related_entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["name", "reason"],
                },
            },
        },
        "required": [
            "summary",
            "recommended_title",
            "recommended_type",
            "duplicate_risk",
            "committer_action",
            "committer_note",
            "related_entries",
        ],
    },
    ensure_ascii=False,
)


def infer_mime_type(filename: str) -> str | None:
    lower = str(filename or "").strip().lower()
    if lower.endswith(".md"):
        return "text/markdown"
    if lower.endswith(".txt"):
        return "text/plain"
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if lower.endswith(".pptx"):
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if lower.endswith(".zip"):
        return "application/zip"
    return None


def ensure_platform_state(
    *,
    store: PlatformStore,
    state_dir: str | Path,
    uploads_dir: str | Path,
    workspaces_dir: str | Path,
) -> None:
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    Path(uploads_dir).mkdir(parents=True, exist_ok=True)
    Path(workspaces_dir).mkdir(parents=True, exist_ok=True)
    store.init()


def build_submission_hash(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\n---\n")
    return digest.hexdigest()


def normalize_name(raw_value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", raw_value).strip()
    return cleaned or fallback


def parse_trusted_proxy_cidrs(raw_value: str | None) -> tuple[ipaddress._BaseNetwork, ...]:
    if not raw_value:
        return ()
    networks: list[ipaddress._BaseNetwork] = []
    for item in raw_value.split(","):
        token = item.strip()
        if not token:
            continue
        networks.append(ipaddress.ip_network(token, strict=False))
    return tuple(networks)


def detect_submitter_ip(
    headers: dict[str, str] | None,
    client_host: str | None,
    *,
    trust_proxy_headers: bool = False,
    trusted_proxy_cidrs: Iterable[ipaddress._BaseNetwork] = (),
) -> str:
    headers = headers or {}
    normalized_client = normalize_ip(client_host)
    if not trust_proxy_headers:
        return normalized_client

    trusted_networks = tuple(trusted_proxy_cidrs)
    if not trusted_networks:
        return normalized_client
    if not ip_in_networks(normalized_client, trusted_networks):
        return normalized_client

    forwarded = normalize_ip(headers.get("x-forwarded-for", "").split(",")[0].strip())
    real_ip = normalize_ip(headers.get("x-real-ip", "").strip())
    return forwarded or real_ip or normalized_client


def normalize_ip(raw_value: str | None) -> str:
    value = (raw_value or "").strip()
    if not value:
        return "unknown"
    candidate = value
    if value.startswith("[") and "]" in value:
        candidate = value[1 : value.index("]")]
    elif value.count(":") == 1 and "." in value:
        host, _, port = value.rpartition(":")
        if port.isdigit():
            candidate = host
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return value


def ip_in_networks(
    client_ip: str,
    networks: Iterable[ipaddress._BaseNetwork],
) -> bool:
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    return any(address in network for network in networks)


def extract_upload_text(file_path: str | Path, mime_type: str) -> str:
    path = Path(file_path)
    if mime_type == "text/plain":
        return path.read_text(encoding="utf-8", errors="replace")
    if mime_type == "text/markdown":
        return path.read_text(encoding="utf-8", errors="replace")
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        from docx import Document

        doc = Document(path)
        paragraphs = [item.text.strip() for item in doc.paragraphs if item.text.strip()]
        return "\n\n".join(paragraphs).strip()
    if mime_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        from pptx import Presentation

        presentation = Presentation(path)
        chunks: list[str] = []
        for slide_index, slide in enumerate(presentation.slides, start=1):
            slide_lines: list[str] = []
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text = str(shape.text).strip()
                    if text:
                        slide_lines.append(text)
            if slide_lines:
                chunks.append(f"Slide {slide_index}\n" + "\n".join(slide_lines))
        return "\n\n".join(chunks).strip()
    raise ValueError(f"Unsupported mime type: {mime_type}")


def analyze_text_submission(
    *,
    kb_path: str | Path,
    title: str,
    content: str,
    submission_type: str,
) -> dict[str, Any]:
    cleaned_title = normalize_name(title, fallback="未命名提交")
    cleaned_content = content.strip()
    shortlist = search_kb(kb_path, f"{cleaned_title}\n{cleaned_content}", limit=6)
    fallback = _fallback_submission_analysis(
        title=cleaned_title,
        submission_type=submission_type,
        shortlist=shortlist,
    )
    LOGGER.info(
        "submission.analysis.start",
        "Starting submission analysis.",
        details={
            "title": cleaned_title,
            "submission_type": submission_type,
            "shortlist_count": len(shortlist),
        },
    )
    try:
        from sediment.llm_cli import build_cli_command, collect_output, parse_json_object
        from sediment.settings import load_settings

        settings = load_settings()
        timeout_seconds = min(
            max(15, int(settings["agent"]["exec_timeout_seconds"])),
            90,
        )
        prompt = _build_submission_analysis_prompt(
            title=cleaned_title,
            content=cleaned_content,
            submission_type=submission_type,
            shortlist=shortlist,
        )
        with tempfile.TemporaryDirectory(prefix="sediment-submit-analysis-") as temp_dir:
            temp_root = Path(temp_dir)
            prompt_file = temp_root / "prompt.txt"
            payload_file = temp_root / "payload.json"
            prompt_file.write_text(prompt, encoding="utf-8")
            payload_file.write_text(
                json.dumps(
                    {
                        "title": cleaned_title,
                        "submission_type": submission_type,
                        "content": cleaned_content,
                        "shortlist": shortlist,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            invocation = build_cli_command(
                settings,
                prompt,
                prompt_file=prompt_file,
                payload_file=payload_file,
                cwd=Path(settings["workspace_root"]),
                extra_args=["--json-schema", SUBMISSION_ANALYSIS_SCHEMA],
            )
            result = subprocess.run(
                invocation.command,
                input=invocation.stdin_data,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                cwd=str(Path(settings["workspace_root"])),
            )
        if result.returncode != 0:
            detail = (
                result.stderr.strip()
                or result.stdout.strip()
                or f"exit code {result.returncode}"
            )
            fallback["status"] = "degraded"
            fallback["warnings"] = [f"Agent analysis failed: {detail}"]
            LOGGER.warning(
                "submission.analysis.degraded",
                "Submission analysis degraded because the agent CLI failed.",
                details={
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                },
            )
            return fallback
        raw_output = collect_output(invocation, stdout=result.stdout, stderr=result.stderr)
        parsed = parse_json_object(raw_output)
        normalized = _normalize_submission_analysis(
            parsed,
            title=cleaned_title,
            submission_type=submission_type,
            shortlist=shortlist,
        )
        normalized["status"] = "ok"
        LOGGER.info(
            "submission.analysis.completed",
            "Submission analysis completed.",
            details={
                "recommended_type": normalized.get("recommended_type"),
                "committer_action": normalized.get("committer_action"),
            },
        )
        return normalized
    except Exception as exc:  # noqa: BLE001
        fallback["status"] = "degraded"
        fallback["warnings"] = [f"Agent analysis unavailable: {exc}"]
        LOGGER.error(
            "submission.analysis.unavailable",
            "Submission analysis fell back because the agent runtime was unavailable.",
            error=exc,
            details={
                "title": cleaned_title,
                "submission_type": submission_type,
            },
        )
        return fallback


def prepare_document_submission(
    *,
    filename: str,
    mime_type: str,
    file_bytes: bytes,
    uploads: list[dict[str, Any]] | None,
    max_upload_bytes: int,
) -> dict[str, Any]:
    normalized_uploads, skipped = _expand_document_uploads(
        filename=filename,
        mime_type=mime_type,
        file_bytes=file_bytes,
        uploads=uploads,
        max_upload_bytes=max_upload_bytes,
    )
    if not normalized_uploads:
        raise ValueError("could not find a supported document to ingest")
    LOGGER.info(
        "document.prepare.start",
        "Preparing document submission payload.",
        details={
            "filename": filename,
            "mime_type": mime_type,
            "upload_count": len(normalized_uploads),
            "skipped_count": len(skipped),
        },
    )

    extracted_parts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="sediment-upload-extract-") as temp_dir:
        temp_root = Path(temp_dir)
        for index, upload in enumerate(normalized_uploads, start=1):
            temp_path = temp_root / f"{index}_{sanitize_filename(Path(upload['filename']).name)}"
            temp_path.write_bytes(upload["file_bytes"])
            text = extract_upload_text(temp_path, upload["mime_type"]).strip()
            if not text:
                continue
            extracted_parts.append(f"## {upload['relative_path']}\n\n{text}")

    if not extracted_parts:
        raise ValueError("could not extract text from uploaded document")

    source_label = _bundle_label(filename=filename, uploads=normalized_uploads)
    notes_parts: list[str] = []
    if skipped:
        notes_parts.append("Skipped unsupported files: " + ", ".join(skipped[:8]))
        LOGGER.warning(
            "document.prepare.skipped_uploads",
            "Skipped unsupported uploads while preparing document submission.",
            details={"skipped": skipped[:8], "skipped_count": len(skipped)},
        )
    notes = " | ".join(notes_parts) if notes_parts else None

    original_is_archive = mime_type in ZIP_MIME_TYPES
    if uploads or len(normalized_uploads) > 1 or original_is_archive:
        if original_is_archive and not uploads:
            stored_bytes = file_bytes
            stored_filename = sanitize_filename(filename or "upload.zip")
        else:
            stored_bytes = _zip_document_bundle(normalized_uploads)
            stored_filename = sanitize_filename(source_label)
            if not stored_filename.lower().endswith(".zip"):
                stored_filename = f"{stored_filename}.zip"
        stored_mime_type = "application/zip"
    else:
        only = normalized_uploads[0]
        stored_bytes = only["file_bytes"]
        stored_filename = sanitize_filename(only["filename"])
        stored_mime_type = only["mime_type"]

    return {
        "title": source_label,
        "filename": stored_filename,
        "mime_type": stored_mime_type,
        "file_bytes": stored_bytes,
        "extracted_text": "\n\n".join(extracted_parts).strip(),
        "notes": notes,
        "file_count": len(normalized_uploads),
    }


def prepare_document_staging_upload(
    *,
    filename: str,
    mime_type: str,
    file_bytes: bytes,
    uploads: list[dict[str, Any]] | None,
    max_upload_bytes: int,
) -> dict[str, Any]:
    normalized_uploads, skipped = _expand_document_uploads(
        filename=filename,
        mime_type=mime_type,
        file_bytes=file_bytes,
        uploads=uploads,
        max_upload_bytes=max_upload_bytes,
    )
    if not normalized_uploads:
        raise ValueError("could not find a supported document to stage")

    source_label = _bundle_label(filename=filename, uploads=normalized_uploads)
    notes_parts: list[str] = []
    if skipped:
        notes_parts.append("Skipped unsupported files: " + ", ".join(skipped[:8]))
    original_is_archive = mime_type in ZIP_MIME_TYPES
    if uploads or len(normalized_uploads) > 1 or original_is_archive:
        if original_is_archive and not uploads:
            stored_bytes = file_bytes
            stored_filename = sanitize_filename(filename or "upload.zip")
        else:
            stored_bytes = _zip_document_bundle(normalized_uploads)
            stored_filename = sanitize_filename(source_label)
            if not stored_filename.lower().endswith(".zip"):
                stored_filename = f"{stored_filename}.zip"
        stored_mime_type = "application/zip"
    else:
        only = normalized_uploads[0]
        stored_bytes = only["file_bytes"]
        stored_filename = sanitize_filename(only["filename"])
        stored_mime_type = only["mime_type"]

    return {
        "title": source_label,
        "filename": stored_filename,
        "mime_type": stored_mime_type,
        "file_bytes": stored_bytes,
        "notes": " | ".join(notes_parts) if notes_parts else None,
        "file_count": len(normalized_uploads),
    }


def _build_submission_analysis_prompt(
    *,
    title: str,
    content: str,
    submission_type: str,
    shortlist: list[dict[str, Any]],
) -> str:
    shortlist_payload = [
        {
            "name": item["name"],
            "entry_type": item["entry_type"],
            "status": item["status"],
            "summary": item["summary"],
            "snippet": item["snippet"],
            "score": item["score"],
        }
        for item in shortlist
    ]
    return "\n\n".join(
        [
            "You are the Sediment submission triage assistant.",
            "Review this incoming user submission against the current KB shortlist.",
            "Be conservative. Suggest a better title or type only when clearly helpful.",
            "Return JSON only. No markdown fences and no prose before or after the JSON object.",
            "Focus on helping a human committer judge the submission quickly.",
            json.dumps(
                {
                    "submission": {
                        "title": title,
                        "type": submission_type,
                        "content": content,
                    },
                    "kb_shortlist": shortlist_payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )


def _fallback_submission_analysis(
    *,
    title: str,
    submission_type: str,
    shortlist: list[dict[str, Any]],
) -> dict[str, Any]:
    related_entries = [
        {"name": item["name"], "reason": item["summary"] or item["snippet"] or "相关条目"}
        for item in shortlist[:4]
    ]
    highest_score = shortlist[0]["score"] if shortlist else 0
    duplicate_risk = "high" if highest_score >= 16 else "medium" if shortlist else "low"
    committer_action = "merge_or_link" if duplicate_risk == "high" else "ingest"
    if submission_type == "feedback":
        committer_action = "manual_review"
    summary = (
        "Agent analysis is unavailable, but Sediment found related KB entries for manual review."
        if shortlist
        else "Agent analysis is unavailable. The submission is stored and ready for manual review."
    )
    return {
        "status": "fallback",
        "summary": summary,
        "recommended_title": title,
        "recommended_type": (
            submission_type
            if submission_type in {"concept", "lesson", "feedback"}
            else "concept"
        ),
        "duplicate_risk": duplicate_risk,
        "committer_action": committer_action,
        "committer_note": (
            "Compare against the related entries before running ingest."
            if shortlist
            else "No obvious duplicate was found from the KB shortlist."
        ),
        "related_entries": related_entries,
        "warnings": [],
    }


def _normalize_submission_analysis(
    payload: dict[str, Any],
    *,
    title: str,
    submission_type: str,
    shortlist: list[dict[str, Any]],
) -> dict[str, Any]:
    fallback = _fallback_submission_analysis(
        title=title,
        submission_type=submission_type,
        shortlist=shortlist,
    )
    related_entries = payload.get("related_entries")
    normalized_entries: list[dict[str, str]] = []
    if isinstance(related_entries, list):
        for item in related_entries[:6]:
            if not isinstance(item, dict):
                continue
            name = normalize_name(str(item.get("name", "")), fallback="")
            reason = normalize_name(str(item.get("reason", "")), fallback="相关条目")
            if name:
                normalized_entries.append({"name": name, "reason": reason})
    return {
        "summary": normalize_name(str(payload.get("summary", "")), fallback=fallback["summary"]),
        "recommended_title": normalize_name(
            str(payload.get("recommended_title", "")),
            fallback=fallback["recommended_title"],
        ),
        "recommended_type": (
            str(payload.get("recommended_type", "")).strip()
            if str(payload.get("recommended_type", "")).strip() in {"concept", "lesson", "feedback"}
            else fallback["recommended_type"]
        ),
        "duplicate_risk": (
            str(payload.get("duplicate_risk", "")).strip()
            if str(payload.get("duplicate_risk", "")).strip() in {"low", "medium", "high"}
            else fallback["duplicate_risk"]
        ),
        "committer_action": (
            str(payload.get("committer_action", "")).strip()
            if str(payload.get("committer_action", "")).strip()
            in {"manual_review", "ingest", "merge_or_link"}
            else fallback["committer_action"]
        ),
        "committer_note": normalize_name(
            str(payload.get("committer_note", "")),
            fallback=fallback["committer_note"],
        ),
        "related_entries": normalized_entries or fallback["related_entries"],
        "warnings": [],
    }


def _expand_document_uploads(
    *,
    filename: str,
    mime_type: str,
    file_bytes: bytes,
    uploads: list[dict[str, Any]] | None,
    max_upload_bytes: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    if uploads:
        return _normalize_supplied_uploads(uploads, max_upload_bytes=max_upload_bytes)
    normalized_mime = mime_type or infer_mime_type(filename or "") or ""
    if normalized_mime in ZIP_MIME_TYPES:
        return _extract_zip_upload(
            filename=filename or "upload.zip",
            file_bytes=file_bytes,
            max_upload_bytes=max_upload_bytes,
        )
    if normalized_mime not in ALLOWED_MIME_TYPES:
        raise ValueError("unsupported upload type")
    return (
        [
            {
                "filename": filename or "upload.bin",
                "relative_path": sanitize_relative_upload_path(filename or "upload.bin"),
                "mime_type": normalized_mime,
                "file_bytes": file_bytes,
            }
        ],
        [],
    )


def _normalize_supplied_uploads(
    uploads: list[dict[str, Any]],
    *,
    max_upload_bytes: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    normalized: list[dict[str, Any]] = []
    skipped: list[str] = []
    total_bytes = 0
    for item in uploads:
        if not isinstance(item, dict):
            continue
        raw_bytes = item.get("file_bytes", b"")
        if not isinstance(raw_bytes, bytes) or not raw_bytes:
            continue
        filename = str(item.get("filename") or item.get("relative_path") or "upload.bin")
        relative_path = sanitize_relative_upload_path(
            str(item.get("relative_path") or filename),
            fallback=filename,
        )
        mime_type = str(item.get("mime_type") or infer_mime_type(filename) or "").strip()
        if _is_ignorable_upload(relative_path):
            skipped.append(relative_path)
            continue
        total_bytes += len(raw_bytes)
        if total_bytes > max(1, max_upload_bytes):
            raise ValueError("uploaded document bundle is too large")
        if mime_type in ZIP_MIME_TYPES:
            expanded, expanded_skipped = _extract_zip_upload(
                filename=filename,
                file_bytes=raw_bytes,
                max_upload_bytes=max_upload_bytes,
            )
            normalized.extend(expanded)
            skipped.extend(expanded_skipped)
            continue
        if mime_type not in ALLOWED_MIME_TYPES:
            skipped.append(relative_path)
            continue
        normalized.append(
            {
                "filename": filename,
                "relative_path": relative_path,
                "mime_type": mime_type,
                "file_bytes": raw_bytes,
            }
        )
    return normalized, skipped


def _extract_zip_upload(
    *,
    filename: str,
    file_bytes: bytes,
    max_upload_bytes: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    supported: list[dict[str, Any]] = []
    skipped: list[str] = []
    total_unpacked = 0
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        infos = [item for item in archive.infolist() if not item.is_dir()]
        if len(infos) > 200:
            raise ValueError("archive contains too many files")
        for info in infos:
            relative_path = sanitize_relative_upload_path(info.filename, fallback=filename)
            if _is_ignorable_upload(relative_path):
                skipped.append(relative_path)
                continue
            mime_type = infer_mime_type(relative_path) or ""
            if mime_type not in ALLOWED_MIME_TYPES or mime_type in ZIP_MIME_TYPES:
                skipped.append(relative_path)
                continue
            total_unpacked += max(0, int(info.file_size))
            if total_unpacked > max(1, max_upload_bytes) * 4:
                raise ValueError("archive expands beyond the safe size limit")
            supported.append(
                {
                    "filename": Path(relative_path).name,
                    "relative_path": relative_path,
                    "mime_type": mime_type,
                    "file_bytes": archive.read(info),
                }
            )
    return supported, skipped


def _zip_document_bundle(uploads: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in uploads:
            archive.writestr(item["relative_path"], item["file_bytes"])
    return buffer.getvalue()


def _bundle_label(*, filename: str, uploads: list[dict[str, Any]]) -> str:
    if filename and filename.strip():
        base = Path(filename).stem.strip()
        if base:
            return base
    roots = {
        item["relative_path"].split("/", 1)[0]
        for item in uploads
        if "/" in item["relative_path"]
    }
    if len(roots) == 1:
        return next(iter(roots))
    if len(uploads) == 1:
        return Path(uploads[0]["filename"]).stem or uploads[0]["filename"]
    return "document-bundle"


def sanitize_relative_upload_path(raw_value: str, *, fallback: str | None = None) -> str:
    value = (raw_value or fallback or "upload.bin").replace("\\", "/").strip().lstrip("/")
    parts: list[str] = []
    for part in value.split("/"):
        token = part.strip()
        if not token or token in {".", ".."}:
            continue
        parts.append(sanitize_filename(token))
    if not parts:
        return sanitize_filename(fallback or "upload.bin")
    return "/".join(parts)


def _is_ignorable_upload(relative_path: str) -> bool:
    lower = relative_path.lower()
    return (
        lower.startswith("__macosx/")
        or lower.endswith(".ds_store")
        or lower.endswith("thumbs.db")
    )


def submit_text(
    *,
    store: PlatformStore,
    kb_path: str | Path,
    title: str,
    content: str,
    submitter_name: str,
    submitter_ip: str,
    submission_type: str = "text",
    submitter_user_id: str | None = None,
    notes: str | None = None,
    rate_limit_count: int = 1,
    rate_limit_window_seconds: int = 60,
    max_text_chars: int = 20_000,
    dedupe_window_seconds: int = 86_400,
) -> dict[str, Any]:
    cleaned_title = normalize_name(title, fallback="未命名提交")
    cleaned_content = content.strip()
    cleaned_submitter = normalize_name(submitter_name, fallback="Anonymous")
    if not cleaned_content:
        raise ValueError("submission content must not be empty")
    if len(cleaned_content) > max(1, max_text_chars):
        raise ValueError("submission content is too large")
    dedupe_hash = build_submission_hash(cleaned_title, cleaned_content)

    analysis = analyze_text_submission(
        kb_path=kb_path,
        title=cleaned_title,
        content=cleaned_content,
        submission_type=submission_type,
    )

    record = store.create_submission_checked(
        submission_type=submission_type,
        title=cleaned_title,
        raw_text=cleaned_content,
        extracted_text=cleaned_content,
        stored_file_path=None,
        mime_type="text/plain",
        submitter_name=cleaned_submitter,
        submitter_ip=submitter_ip,
        submitter_user_id=submitter_user_id,
        dedupe_hash=dedupe_hash,
        rate_limit_count=max(1, rate_limit_count),
        rate_limit_window_seconds=max(1, rate_limit_window_seconds),
        dedupe_window_seconds=max(0, dedupe_window_seconds),
        analysis=analysis,
        notes=notes,
    )
    store.add_audit_log(
        actor_name=cleaned_submitter,
        actor_id=submitter_user_id,
        actor_role="contributor",
        action="submission.create_text",
        target_type="submission",
        target_id=record["id"],
        details={"submission_type": submission_type},
    )
    LOGGER.info(
        "submission.text.created",
        "Created text submission.",
        submission_id=record["id"],
        user_id=submitter_user_id,
        details={
            "submission_type": submission_type,
            "submitter_ip": submitter_ip,
            "title": cleaned_title,
        },
    )
    return record


def submit_document(
    *,
    store: PlatformStore,
    uploads_dir: str | Path,
    filename: str,
    mime_type: str,
    file_bytes: bytes,
    uploads: list[dict[str, Any]] | None = None,
    submitter_name: str,
    submitter_ip: str,
    submitter_user_id: str | None = None,
    notes: str | None = None,
    rate_limit_count: int = 1,
    rate_limit_window_seconds: int = 60,
    max_upload_bytes: int = 10 * 1024 * 1024,
    dedupe_window_seconds: int = 86_400,
) -> dict[str, Any]:
    if not uploads and len(file_bytes) > max(1, max_upload_bytes):
        raise ValueError("uploaded file is too large")

    cleaned_submitter = normalize_name(submitter_name, fallback="Anonymous")
    prepared = prepare_document_submission(
        filename=filename,
        mime_type=mime_type,
        file_bytes=file_bytes,
        uploads=uploads,
        max_upload_bytes=max_upload_bytes,
    )
    safe_filename = sanitize_filename(prepared["filename"] or "upload.bin")
    stored_path = Path(uploads_dir) / f"{uuid.uuid4().hex}_{safe_filename}"
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    stored_path.write_bytes(prepared["file_bytes"])
    extracted_text = str(prepared["extracted_text"]).strip()
    dedupe_hash = build_submission_hash(safe_filename, prepared["mime_type"], extracted_text)
    try:
        record = store.create_submission_checked(
            submission_type="document",
            title=str(prepared["title"]),
            raw_text=base64.b64encode(prepared["file_bytes"]).decode("ascii"),
            extracted_text=extracted_text,
            stored_file_path=str(stored_path),
            mime_type=str(prepared["mime_type"]),
            submitter_name=cleaned_submitter,
            submitter_ip=submitter_ip,
            submitter_user_id=submitter_user_id,
            dedupe_hash=dedupe_hash,
            rate_limit_count=max(1, rate_limit_count),
            rate_limit_window_seconds=max(1, rate_limit_window_seconds),
            dedupe_window_seconds=max(0, dedupe_window_seconds),
            notes=prepared["notes"] or notes,
        )
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    store.add_audit_log(
        actor_name=cleaned_submitter,
        actor_id=submitter_user_id,
        actor_role="contributor",
        action="submission.create_document",
        target_type="submission",
        target_id=record["id"],
        details={
            "filename": safe_filename,
            "mime_type": prepared["mime_type"],
            "file_count": prepared["file_count"],
        },
    )
    LOGGER.info(
        "submission.document.created",
        "Created document submission.",
        submission_id=record["id"],
        user_id=submitter_user_id,
        details={
            "filename": safe_filename,
            "mime_type": prepared["mime_type"],
            "file_count": prepared["file_count"],
            "submitter_ip": submitter_ip,
        },
    )
    return record


def submit_feedback_item(
    *,
    store: PlatformStore,
    title: str,
    content: str,
    submitter_name: str,
    submitter_ip: str,
    submitter_user_id: str | None = None,
    notes: str | None = None,
    rate_limit_count: int = 1,
    rate_limit_window_seconds: int = 60,
    max_text_chars: int = 20_000,
    dedupe_window_seconds: int = 86_400,
) -> dict[str, Any]:
    cleaned_title = normalize_name(title, fallback="Untitled feedback")
    cleaned_content = content.strip()
    cleaned_submitter = normalize_name(submitter_name, fallback="Anonymous")
    if not cleaned_content:
        raise ValueError("submission content must not be empty")
    if len(cleaned_content) > max(1, max_text_chars):
        raise ValueError("submission content is too large")
    item = store.create_inbox_item_checked(
        item_type="text_feedback",
        title=cleaned_title,
        body_text=cleaned_content,
        stored_file_path=None,
        original_filename=None,
        mime_type="text/plain",
        submitter_name=cleaned_submitter,
        submitter_ip=submitter_ip,
        submitter_user_id=submitter_user_id,
        dedupe_hash=build_submission_hash(cleaned_title, cleaned_content),
        rate_limit_count=max(1, rate_limit_count),
        rate_limit_window_seconds=max(1, rate_limit_window_seconds),
        dedupe_window_seconds=max(0, dedupe_window_seconds),
        status="open",
        notes=notes,
    )
    store.add_audit_log(
        actor_name=cleaned_submitter,
        actor_id=submitter_user_id,
        actor_role="contributor",
        action="inbox.create_text_feedback",
        target_type="inbox_item",
        target_id=item["id"],
        details={"item_type": "text_feedback"},
    )
    return item


def submit_uploaded_document_item(
    *,
    store: PlatformStore,
    uploads_dir: str | Path,
    filename: str,
    mime_type: str,
    file_bytes: bytes,
    uploads: list[dict[str, Any]] | None = None,
    submitter_name: str,
    submitter_ip: str,
    submitter_user_id: str | None = None,
    notes: str | None = None,
    rate_limit_count: int = 1,
    rate_limit_window_seconds: int = 60,
    max_upload_bytes: int = 10 * 1024 * 1024,
    dedupe_window_seconds: int = 86_400,
) -> dict[str, Any]:
    if not uploads and len(file_bytes) > max(1, max_upload_bytes):
        raise ValueError("uploaded file is too large")
    cleaned_submitter = normalize_name(submitter_name, fallback="Anonymous")
    prepared = prepare_document_staging_upload(
        filename=filename,
        mime_type=mime_type,
        file_bytes=file_bytes,
        uploads=uploads,
        max_upload_bytes=max_upload_bytes,
    )
    safe_filename = sanitize_filename(prepared["filename"] or "upload.bin")
    stored_path = Path(uploads_dir) / f"{uuid.uuid4().hex}_{safe_filename}"
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    stored_path.write_bytes(prepared["file_bytes"])
    try:
        item = store.create_inbox_item_checked(
            item_type="uploaded_document",
            title=str(prepared["title"]),
            body_text="",
            stored_file_path=str(stored_path),
            original_filename=safe_filename,
            mime_type=str(prepared["mime_type"]),
            submitter_name=cleaned_submitter,
            submitter_ip=submitter_ip,
            submitter_user_id=submitter_user_id,
            dedupe_hash=build_submission_hash(
                safe_filename,
                prepared["mime_type"],
                base64.b64encode(prepared["file_bytes"]).decode("ascii"),
            ),
            rate_limit_count=max(1, rate_limit_count),
            rate_limit_window_seconds=max(1, rate_limit_window_seconds),
            dedupe_window_seconds=max(0, dedupe_window_seconds),
            status="staged",
            notes=prepared["notes"] or notes,
        )
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    store.add_audit_log(
        actor_name=cleaned_submitter,
        actor_id=submitter_user_id,
        actor_role="contributor",
        action="inbox.create_uploaded_document",
        target_type="inbox_item",
        target_id=item["id"],
        details={
            "filename": safe_filename,
            "mime_type": prepared["mime_type"],
            "file_count": prepared["file_count"],
        },
    )
    return item


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.strip())
    return cleaned or "upload.bin"


def get_portal_home(kb_path: str | Path, *, store: PlatformStore) -> dict[str, Any]:
    data = inventory(kb_path)
    report = audit_kb(kb_path)
    inbox_counts = store.inbox_status_counts() if hasattr(store, "inbox_status_counts") else {}
    docs = data["docs"]
    recent = sorted(
        (
            {
                "name": name,
                "entry_type": doc["entry_type"],
                "status": doc["status"],
                "updated_at": Path(doc["path"]).stat().st_mtime if doc["path"] else 0,
            }
            for name, doc in docs.items()
            if doc["path"]
        ),
        key=lambda item: item["updated_at"],
        reverse=True,
    )[:8]
    for item in recent:
        item["updated_at"] = int(item["updated_at"])
    return {
        "counts": {
            "formal_entries": len(data["entries"]),
            "placeholders": len(data["placeholders"]),
            "indexes": len(data["indexes"]),
            "pending_submissions": (
                inbox_counts.get("open", 0)
                + inbox_counts.get("staged", 0)
                + inbox_counts.get("ready", 0)
                + inbox_counts.get("ingesting", 0)
            ),
            "health_issues": len(build_health_issue_queue(kb_path)),
        },
        "recent_updates": recent,
        "health_summary": summarize_health_report(report),
    }


def search_kb(kb_path: str | Path, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    raw_query = query.strip()
    if not raw_query:
        return []
    data = inventory(kb_path)
    terms = [term for term in re.split(r"\s+", raw_query) if term]
    results: list[dict[str, Any]] = []
    for name, doc in data["docs"].items():
        score = 0
        haystacks = {
            "title": doc["title"],
            "aliases": " ".join(doc["aliases"]),
            "summary": doc["summary"],
            "body": doc["body"],
        }
        for term in terms:
            lowered = term.casefold()
            if lowered in haystacks["title"].casefold():
                score += 10
            if lowered in haystacks["aliases"].casefold():
                score += 8
            if lowered in haystacks["summary"].casefold():
                score += 6
            if lowered in haystacks["body"].casefold():
                score += 3
        if score <= 0:
            continue
        score += min(doc["inbound_count"], 5)
        if doc["kind"] == "formal":
            score += 2
        snippet = build_search_snippet(doc["body"], terms)
        results.append(
            {
                "name": name,
                "title": doc["title"],
                "kind": doc["kind"],
                "entry_type": doc["entry_type"],
                "status": doc["status"],
                "summary": doc["summary"],
                "snippet": snippet,
                "score": score,
            }
        )
    return sorted(results, key=lambda item: (-item["score"], item["name"]))[:limit]


def search_kb_suggestions(
    kb_path: str | Path,
    query: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    raw_query = query.strip()
    if not raw_query:
        return []
    data = inventory(kb_path)
    terms = [term for term in re.split(r"\s+", raw_query) if term]
    suggestions: list[dict[str, Any]] = []
    for name, doc in data["docs"].items():
        score = 0
        matched_field = ""
        for term in terms:
            lowered = term.casefold()
            if doc["title"].casefold().startswith(lowered) or name.casefold().startswith(lowered):
                score += 16
                matched_field = matched_field or "title"
            elif lowered in doc["title"].casefold():
                score += 12
                matched_field = matched_field or "title"
            elif any(alias.casefold().startswith(lowered) for alias in doc["aliases"]):
                score += 10
                matched_field = matched_field or "aliases"
            elif lowered in " ".join(doc["aliases"]).casefold():
                score += 8
                matched_field = matched_field or "aliases"
            elif lowered in doc["summary"].casefold():
                score += 4
                matched_field = matched_field or "summary"
        if score <= 0:
            continue
        suggestions.append(
            {
                "name": name,
                "title": doc["title"],
                "kind": doc["kind"],
                "entry_type": doc["entry_type"],
                "status": doc["status"],
                "summary": doc["summary"],
                "matched_field": matched_field or "summary",
                "score": score + min(int(doc["inbound_count"]), 5),
            }
        )
    return sorted(suggestions, key=lambda item: (-item["score"], item["name"]))[:limit]


def build_search_snippet(body: str, terms: list[str]) -> str:
    compact = re.sub(r"\s+", " ", body).strip()
    if not compact:
        return ""
    lowered = compact.casefold()
    for term in terms:
        idx = lowered.find(term.casefold())
        if idx != -1:
            start = max(0, idx - 80)
            end = min(len(compact), idx + 140)
            snippet = compact[start:end].strip()
            if start > 0:
                snippet = "..." + snippet
            if end < len(compact):
                snippet = snippet + "..."
            return snippet
    return compact[:180] + ("..." if len(compact) > 180 else "")


def get_entry_detail(kb_path: str | Path, name: str) -> dict[str, Any]:
    data = inventory(kb_path)
    doc = data["docs"].get(name) or data["index_docs"].get(name)
    if doc is None:
        raise FileNotFoundError(name)
    path = resolve_kb_document_path(kb_path, name)
    content = path.read_text(encoding="utf-8") if path else ""
    validation = None
    if path and (path.parent.name == "indexes" or path.name == index_config()["root_file"]):
        validation = validate_index(path)
    elif path:
        kind = "placeholder" if "/placeholders/" in str(path) else "formal"
        validation = validate_entry(path=path, kind=kind)
    sections_map = dict(doc.get("sections_map") or {})
    canonical_section_order = ("Scope", "Trigger", "Why", "Risks", "Related")
    canonical_sections = [
        {"name": section_name, "content": str(sections_map.get(section_name, "")).strip()}
        for section_name in canonical_section_order
        if str(sections_map.get(section_name, "")).strip()
    ]
    residual_sections = [
        {"name": section_name, "content": str(section_body).strip()}
        for section_name, section_body in sections_map.items()
        if section_name not in canonical_section_order and str(section_body).strip()
    ]
    residual_parts: list[str] = []
    preamble = str(doc.get("preamble", "")).strip()
    if preamble:
        residual_parts.append(preamble)
    for section in residual_sections:
        residual_parts.append(f"## {section['name']}\n{section['content']}")
    residual_markdown = "\n\n".join(part for part in residual_parts if part).strip()
    related_links = extract_wikilinks(sections_map.get("Related", "")) or list(
        doc.get("graph_links") or []
    )
    return {
        "name": name,
        "path": str(path) if path else None,
        "content": content,
        "content_hash": content_hash(content),
        "metadata": doc,
        "validation": validation,
        "structured": {
            "title": doc.get("title") or name,
            "kind": doc.get("kind"),
            "entry_type": doc.get("entry_type"),
            "status": doc.get("status"),
            "summary": doc.get("summary"),
            "aliases": list(doc.get("aliases") or []),
            "sources": list(doc.get("sources") or []),
            "related_links": related_links,
            "canonical_sections": canonical_sections,
            "residual_markdown": residual_markdown,
            "validation_cues": {
                "valid": bool(validation.get("valid")) if isinstance(validation, dict) else None,
                "warnings": list(validation.get("warnings") or []) if isinstance(validation, dict) else [],
                "hard_failures": list(validation.get("hard_failures") or [])
                if isinstance(validation, dict)
                else [],
            },
        },
    }


def graph_payload(kb_path: str | Path) -> dict[str, Any]:
    data = inventory(kb_path)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for name, doc in data["docs"].items():
        nodes.append(
            {
                "id": name,
                "label": name,
                "kind": doc["kind"],
                "entry_type": doc["entry_type"],
                "status": doc["status"],
                "inbound_count": doc["inbound_count"],
            }
        )
        for target in doc["graph_links"]:
            edges.append({"source": name, "target": target, "kind": "related"})
    for name, doc in data["index_docs"].items():
        nodes.append(
            {
                "id": name,
                "label": name,
                "kind": "index",
                "entry_type": "index",
                "status": "n/a",
                "inbound_count": 0,
            }
        )
        for target in doc["links"]:
            edges.append({"source": name, "target": target, "kind": "index_link"})
    return {"nodes": nodes, "edges": edges}


def summarize_health_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "formal_entry_count": report["formal_entry_count"],
        "placeholder_count": report["placeholder_count"],
        "hard_fail_entry_count": report["hard_fail_entry_count"],
        "dangling_link_count": report["dangling_link_count"],
        "orphan_entry_count": report["orphan_entry_count"],
        "promotable_placeholder_count": report["promotable_placeholder_count"],
        "canonical_gap_count": report["canonical_gap_count"],
        "invalid_index_count": report["invalid_index_count"],
    }


def build_health_issue_queue(kb_path: str | Path) -> list[dict[str, Any]]:
    report = audit_kb(kb_path)
    data = inventory(kb_path)
    issues: list[dict[str, Any]] = []

    for item in report["entry_validation"]:
        if item["hard_failures"]:
            issues.append(
                issue(
                    issue_type="hard_failure",
                    severity="blocking",
                    target=item["name"],
                    summary="; ".join(item["hard_failures"]),
                    suggested_action="edit_entry",
                    evidence={"hard_failures": item["hard_failures"]},
                )
            )

    for link in report["dangling_links"]:
        issues.append(
            issue(
                issue_type="dangling_link",
                severity="high",
                target=link["source_file"],
                summary=f"链接 {link['link']} 没有目标",
                suggested_action="run_tidy",
                evidence=link,
            )
        )

    for orphan in report["orphan_entries"]:
        issues.append(
            issue(
                issue_type="orphan_entry",
                severity="medium",
                target=orphan,
                summary="正式条目缺少足够连接",
                suggested_action="run_tidy",
                evidence={"entry": orphan},
            )
        )

    for item in report["promotable_placeholders"]:
        issues.append(
            issue(
                issue_type="promotable_placeholder",
                severity="medium",
                target=item["name"],
                summary=f"placeholder 被引用 {item['ref_count']} 次，值得提升",
                suggested_action="promote_placeholder",
                evidence=item,
            )
        )

    for item in report["canonical_gaps"]:
        issues.append(
            issue(
                issue_type="canonical_gap",
                severity="high",
                target=item["name"],
                summary="正式条目依赖 placeholder 作为关键概念",
                suggested_action="run_tidy",
                evidence=item,
            )
        )

    for item in report["provenance_contamination"]:
        issues.append(
            issue(
                issue_type="provenance_contamination",
                severity="medium",
                target=item["name"],
                summary="来源型链接污染了知识图谱",
                suggested_action="edit_entry",
                evidence=item,
            )
        )

    for item in report["index_validation"]:
        if item["hard_failures"]:
            issues.append(
                issue(
                    issue_type="invalid_index",
                    severity="blocking",
                    target=item["name"],
                    summary="; ".join(item["hard_failures"]),
                    suggested_action="edit_entry",
                    evidence=item,
                )
            )

    for item in report["overloaded_indexes"]:
        issues.append(
            issue(
                issue_type="overloaded_index",
                severity="medium",
                target=item["name"],
                summary="索引规模超过阈值",
                suggested_action="run_tidy",
                evidence=item,
            )
        )

    for item in report["unknown_index_links"]:
        issues.append(
            issue(
                issue_type="unknown_index_link",
                severity="high",
                target=item["index"],
                summary=f"索引链接 {item['link']} 不存在或不应作为入口",
                suggested_action="edit_entry",
                evidence=item,
            )
        )

    for name in report["uncovered_formal_entries"]:
        issues.append(
            issue(
                issue_type="uncovered_formal_entry",
                severity="medium",
                target=name,
                summary="正式条目未被任何索引覆盖",
                suggested_action="run_tidy",
                evidence={"entry": name},
            )
        )

    for name, doc in data["docs"].items():
        if doc["kind"] != "formal":
            continue
        if doc["status"] in {"inferred", "disputed"}:
            issues.append(
                issue(
                    issue_type="low_confidence_entry",
                    severity="low" if doc["status"] == "inferred" else "medium",
                    target=name,
                    summary=f"条目状态为 {doc['status']}，需要人工关注",
                    suggested_action="review_entry",
                    evidence={"status": doc["status"]},
                )
            )

    return sorted(issues, key=lambda item: (severity_rank(item["severity"]), item["target"]))


def issue(
    *,
    issue_type: str,
    severity: str,
    target: str,
    summary: str,
    suggested_action: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": issue_type,
        "severity": severity,
        "target": target,
        "summary": summary,
        "suggested_action": suggested_action,
        "evidence": evidence,
    }


def severity_rank(severity: str) -> int:
    return {"blocking": 0, "high": 1, "medium": 2, "low": 3}.get(severity, 4)


def get_health_payload(kb_path: str | Path) -> dict[str, Any]:
    report = audit_kb(kb_path)
    issues = build_health_issue_queue(kb_path)
    counts: dict[str, int] = {}
    for item in issues:
        counts[item["severity"]] = counts.get(item["severity"], 0) + 1
    return {
        "summary": summarize_health_report(report),
        "severity_counts": counts,
        "issues": issues,
    }


def _issue_document_name(
    issue: dict[str, Any],
    *,
    docs: dict[str, dict[str, Any]],
    index_docs: dict[str, dict[str, Any]],
) -> str | None:
    evidence = issue.get("evidence") if isinstance(issue.get("evidence"), dict) else {}
    candidates = [
        issue.get("target"),
        evidence.get("name"),
        evidence.get("entry"),
        evidence.get("index"),
        evidence.get("source_file"),
    ]
    for raw_value in candidates:
        value = str(raw_value or "").strip()
        if not value:
            continue
        normalized = Path(value).stem if "/" in value or value.endswith(".md") else value
        if normalized in docs or normalized in index_docs:
            return normalized
    return None


def _admin_document_collections(
    kb_path: str | Path,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, dict[str, Any]],
]:
    root = Path(kb_path).resolve()
    data = inventory(root)
    docs = data["docs"]
    index_docs = data["index_docs"]
    issues = build_health_issue_queue(root)
    issues_by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    normalized_issues: list[dict[str, Any]] = []
    for issue in issues:
        enriched = dict(issue)
        document_name = _issue_document_name(issue, docs=docs, index_docs=index_docs)
        enriched["document_name"] = document_name
        normalized_issues.append(enriched)
        if document_name:
            issues_by_document[document_name].append(enriched)

    def build_document(name: str, doc: dict[str, Any], *, group: str) -> dict[str, Any]:
        path = resolve_kb_document_path(root, name)
        document_issues = issues_by_document.get(name, [])
        relative_path = None
        updated_at = 0
        if path is not None and path.exists():
            relative_path = str(path.resolve().relative_to(root))
            updated_at = int(path.stat().st_mtime)
        return {
            "name": name,
            "title": str(doc.get("title") or name),
            "group": group,
            "kind": str(doc.get("kind") or group),
            "entry_type": str(doc.get("entry_type") or ("index" if group == "index" else "")),
            "status": str(doc.get("status") or ("n/a" if group == "index" else "")),
            "summary": str(doc.get("summary") or ""),
            "relative_path": relative_path,
            "updated_at": updated_at,
            "aliases": list(doc.get("aliases") or []),
            "links": list(doc.get("graph_links") or doc.get("links") or []),
            "issue_count": len(document_issues),
            "issue_summaries": [str(item.get("summary") or "") for item in document_issues[:3]],
            "indexes": [],
        }

    documents_by_name: dict[str, dict[str, Any]] = {}
    for name in data["entries"]:
        documents_by_name[name] = build_document(name, docs[name], group="formal")
    for name in data["placeholders"]:
        documents_by_name[name] = build_document(name, docs[name], group="placeholder")
    for name in data["indexes"]:
        documents_by_name[name] = build_document(name, index_docs[name], group="index")
    return data, normalized_issues, issues_by_document, documents_by_name


def kb_document_browser_payload(kb_path: str | Path) -> dict[str, Any]:
    data, normalized_issues, _issues_by_document, documents_by_name = _admin_document_collections(kb_path)
    groups = {
        "formal": [documents_by_name[name] for name in data["entries"]],
        "placeholder": [documents_by_name[name] for name in data["placeholders"]],
        "index": [documents_by_name[name] for name in data["indexes"]],
    }
    return {
        "counts": {key: len(value) for key, value in groups.items()},
        "groups": groups,
        "health_issues": normalized_issues,
    }


def kb_file_management_payload(kb_path: str | Path) -> dict[str, Any]:
    data, normalized_issues, _issues_by_document, documents_by_name = _admin_document_collections(kb_path)
    index_docs = data["index_docs"]
    index_names = set(data["indexes"])
    document_names = set(documents_by_name) - index_names
    parent_indexes: dict[str, set[str]] = defaultdict(set)
    for name, record in index_docs.items():
        for target in record.get("links") or []:
            if target in index_names and target != name:
                parent_indexes[target].add(name)

    indexed_documents: dict[str, set[str]] = defaultdict(set)

    def build_index_node(name: str, *, stack: tuple[str, ...] = ()) -> tuple[dict[str, Any], set[str]]:
        record = documents_by_name[name]
        direct_doc_targets: list[str] = []
        child_index_targets: list[str] = []
        for target in record.get("links") or []:
            if target in index_names and target != name:
                child_index_targets.append(target)
            elif target in document_names:
                direct_doc_targets.append(target)
        direct_doc_targets = list(dict.fromkeys(direct_doc_targets))
        child_index_targets = [
            target for target in dict.fromkeys(child_index_targets) if target not in stack
        ]

        child_nodes: list[dict[str, Any]] = []
        reachable_documents: set[str] = set(direct_doc_targets)
        for child_name in child_index_targets:
            child_node, child_documents = build_index_node(child_name, stack=(*stack, name))
            child_nodes.append(child_node)
            reachable_documents.update(child_documents)
        for document_name in reachable_documents:
            indexed_documents[document_name].add(name)
        node = {
            "name": record["name"],
            "title": record["title"],
            "summary": record["summary"],
            "relative_path": record["relative_path"],
            "issue_count": record["issue_count"],
            "segment": str(index_docs[name].get("segment") or record["name"]),
            "is_root": bool(index_docs[name].get("is_root")),
            "entry_count": int(index_docs[name].get("entry_count") or 0),
            "estimated_tokens": int(index_docs[name].get("estimated_tokens") or 0),
            "last_tidied_at": str(index_docs[name].get("last_tidied_at") or ""),
            "direct_documents": [documents_by_name[target] for target in direct_doc_targets],
            "child_indexes": child_nodes,
            "reachable_document_count": len(reachable_documents),
        }
        return node, reachable_documents

    root_indexes = [
        name
        for name in data["indexes"]
        if bool(index_docs[name].get("is_root")) or not parent_indexes.get(name)
    ]
    top_index_names = list(dict.fromkeys(root_indexes or data["indexes"]))
    top_index_names.sort(
        key=lambda name: (
            not bool(index_docs[name].get("is_root")),
            str(documents_by_name[name].get("title") or name).casefold(),
        )
    )
    top_indexes: list[dict[str, Any]] = []
    reachable_from_top: set[str] = set()
    for name in top_index_names:
        node, reachable_documents = build_index_node(name)
        top_indexes.append(node)
        reachable_from_top.update(reachable_documents)

    for document_name, index_set in indexed_documents.items():
        if document_name in documents_by_name:
            documents_by_name[document_name]["indexes"] = sorted(index_set)

    unindexed_documents = [
        documents_by_name[name]
        for name in sorted(document_names - reachable_from_top)
    ]
    return {
        "counts": {
            "formal": len(data["entries"]),
            "placeholder": len(data["placeholders"]),
            "index": len(data["indexes"]),
            "indexed": len(reachable_from_top),
            "unindexed": len(unindexed_documents),
        },
        "documents_by_name": documents_by_name,
        "top_indexes": top_indexes,
        "unindexed_documents": unindexed_documents,
        "health_issues": normalized_issues,
    }


def search_kb_file_suggestions(
    kb_path: str | Path,
    query: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    raw_query = query.strip()
    if not raw_query:
        return []
    payload = kb_file_management_payload(kb_path)
    terms = [term for term in re.split(r"\s+", raw_query) if term]
    suggestions: list[dict[str, Any]] = []
    for document in payload["documents_by_name"].values():
        score = 0
        matched_field = ""
        aliases = list(document.get("aliases") or [])
        relative_path = str(document.get("relative_path") or "")
        summary = str(document.get("summary") or "")
        title = str(document.get("title") or "")
        name = str(document.get("name") or "")
        for term in terms:
            lowered = term.casefold()
            if title.casefold().startswith(lowered) or name.casefold().startswith(lowered):
                score += 16
                matched_field = matched_field or "title"
            elif lowered in title.casefold():
                score += 12
                matched_field = matched_field or "title"
            elif any(alias.casefold().startswith(lowered) for alias in aliases):
                score += 10
                matched_field = matched_field or "aliases"
            elif lowered in " ".join(aliases).casefold():
                score += 8
                matched_field = matched_field or "aliases"
            elif lowered in relative_path.casefold():
                score += 6
                matched_field = matched_field or "path"
            elif lowered in summary.casefold():
                score += 4
                matched_field = matched_field or "summary"
        if score <= 0:
            continue
        suggestions.append(
            {
                "name": name,
                "title": title,
                "group": str(document.get("group") or ""),
                "kind": str(document.get("kind") or ""),
                "entry_type": str(document.get("entry_type") or ""),
                "status": str(document.get("status") or ""),
                "summary": summary,
                "relative_path": relative_path,
                "indexes": list(document.get("indexes") or []),
                "matched_field": matched_field or "summary",
                "score": score + min(int(document.get("issue_count") or 0), 5),
            }
        )
    return sorted(suggestions, key=lambda item: (-item["score"], item["name"]))[:limit]


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def list_reviews_with_jobs(
    *,
    store: PlatformStore,
    decision: str | None = None,
) -> list[dict[str, Any]]:
    reviews = store.list_reviews(decision=decision, limit=200)
    enriched: list[dict[str, Any]] = []
    for review in reviews:
        payload = dict(review)
        payload["job"] = store.get_job(review["job_id"])
        if review.get("submission_id"):
            payload["submission"] = store.get_submission(review["submission_id"])
        enriched.append(payload)
    return enriched


def determine_target_path(
    kb_path: str | Path,
    *,
    name: str,
    content: str,
    relative_path: str | None = None,
) -> Path:
    root = Path(kb_path).resolve()
    if relative_path:
        target = (root / relative_path).resolve()
        if target == root or root not in target.parents:
            raise ValueError("relative path escapes knowledge base root")
        if target.exists() and target.is_dir():
            raise ValueError("relative path must point to a file inside the knowledge base")
        return target

    existing = resolve_kb_document_path(root, name)
    if existing is not None:
        return existing.resolve()

    frontmatter, _ = split_frontmatter(content)
    item_type = str(frontmatter.get("type", "")).strip()
    if item_type == "placeholder":
        return root / "placeholders" / f"{name}.md"
    if item_type in {"concept", "lesson"}:
        return root / "entries" / f"{name}.md"
    if str(frontmatter.get("kind", "")).strip() == "index" or name.startswith("index."):
        if name == "index.root":
            return root / index_config()["root_file"]
        return root / "indexes" / f"{name}.md"
    return root / "entries" / f"{name}.md"


def validate_target_content(path: Path, content: str) -> dict[str, Any] | None:
    if path.name == index_config()["root_file"] or path.parent.name == "indexes":
        temp_path = _write_temp_for_validation(path.name, content)
        try:
            return validate_index(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
    kind = "placeholder" if path.parent.name == "placeholders" else "formal"
    return validate_entry(text=content, name=path.stem, kind=kind)


def _write_temp_for_validation(filename: str, content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        prefix="sediment-validate-",
        suffix=f"-{filename}",
        delete=False,
    )
    tmp.write(content.encode("utf-8"))
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


def build_diff(path_label: str, old_content: str, new_content: str) -> str:
    diff = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{path_label}",
        tofile=f"b/{path_label}",
    )
    return "".join(diff)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temp_path = Path(temp.name)
    try:
        temp.write(content.encode("utf-8"))
        temp.flush()
        temp.close()
        temp_path.replace(path)
    except Exception:
        temp.close()
        temp_path.unlink(missing_ok=True)
        raise


def apply_operations(
    kb_path: str | Path,
    operations: list[dict[str, Any]],
    *,
    actor_name: str,
    actor_id: str | None = None,
    actor_role: str,
    store: PlatformStore,
) -> dict[str, Any]:
    root = Path(kb_path).resolve()
    prepared: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for operation in operations:
        name = operation.get("name") or Path(operation.get("relative_path", "")).stem
        target_path = determine_target_path(
            root,
            name=name,
            content=operation.get("content", ""),
            relative_path=operation.get("relative_path"),
        )
        old_content = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        target_exists = target_path.exists()
        current_hash = content_hash(old_content)
        base_hash = operation.get("base_hash")
        if base_hash and target_path.exists() and current_hash != base_hash:
            raise RuntimeError(
                f"{target_path.name} changed since review was prepared; refresh the diff first."
            )
        rel_path = str(target_path.relative_to(root))
        if rel_path in seen_paths:
            raise ValueError(f"duplicate operation target detected: {rel_path}")
        seen_paths.add(rel_path)

        change_type = operation.get("change_type", "update")
        if change_type == "delete":
            prepared.append(
                {
                    "name": name,
                    "target_path": target_path,
                    "relative_path": rel_path,
                    "change_type": "delete",
                    "target_exists": target_exists,
                    "old_content": old_content,
                }
            )
            continue

        new_content = operation["content"].strip() + "\n"
        validation = validate_target_content(target_path, new_content)
        if validation and validation.get("hard_failures"):
            raise ValueError("; ".join(validation["hard_failures"]))
        prepared.append(
            {
                "name": name,
                "target_path": target_path,
                "relative_path": rel_path,
                "change_type": change_type,
                "target_exists": target_exists,
                "old_content": old_content,
                "new_content": new_content,
            }
        )

    applied: list[dict[str, Any]] = []
    mutated: list[dict[str, Any]] = []
    try:
        for item in prepared:
            target_path = item["target_path"]
            rel_path = item["relative_path"]
            mutated.append(item)
            if item["change_type"] == "delete":
                if target_path.exists():
                    target_path.unlink()
                applied.append(
                    {
                        "name": item["name"],
                        "relative_path": rel_path,
                        "change_type": "delete",
                        "diff": build_diff(rel_path, item["old_content"], ""),
                    }
                )
                continue

            new_content = item["new_content"]
            _atomic_write_text(target_path, new_content)
            applied.append(
                {
                    "name": item["name"],
                    "relative_path": rel_path,
                    "change_type": item["change_type"],
                    "diff": build_diff(rel_path, item["old_content"], new_content),
                    "new_hash": content_hash(new_content),
                }
            )
    except Exception as exc:
        rollback_errors: list[str] = []
        for item in reversed(mutated):
            target_path = item["target_path"]
            try:
                if item["target_exists"]:
                    _atomic_write_text(target_path, item["old_content"])
                else:
                    target_path.unlink(missing_ok=True)
            except Exception as rollback_exc:  # noqa: BLE001
                rollback_errors.append(
                    f"{target_path}: {rollback_exc}"
                )
        if rollback_errors:
            raise RuntimeError(
                f"{exc}; rollback failed for {', '.join(rollback_errors)}"
            ) from exc
        raise

    store.add_audit_log(
        actor_name=actor_name,
        actor_id=actor_id,
        actor_role=actor_role,
        action="kb.apply_operations",
        target_type="knowledge_base",
        target_id=str(root),
        details={"operations": applied},
    )
    return {"operations": applied, "health": summarize_health_report(audit_kb(root))}


def save_entry(
    kb_path: str | Path,
    *,
    name: str,
    content: str,
    expected_hash: str | None,
    actor_name: str,
    actor_id: str | None = None,
    actor_role: str = "committer",
    store: PlatformStore,
) -> dict[str, Any]:
    root = Path(kb_path).resolve()
    existing = resolve_kb_document_path(root, name)
    if existing is None:
        raise FileNotFoundError(name)
    target = existing.resolve()
    old_content = target.read_text(encoding="utf-8")
    if expected_hash and old_content and content_hash(old_content) != expected_hash:
        raise RuntimeError("entry changed since it was loaded; refresh before saving")
    result = apply_operations(
        root,
        [
            {
                "name": name,
                "relative_path": str(target.relative_to(root)),
                "change_type": "update",
                "content": content,
                "base_hash": content_hash(old_content),
            }
        ],
        actor_name=actor_name,
        actor_id=actor_id,
        actor_role=actor_role,
        store=store,
    )
    detail = get_entry_detail(root, name)
    detail["write_result"] = result
    detail["write_result"]["actor"] = {
        "id": actor_id,
        "name": actor_name,
        "role": actor_role,
    }
    return detail


def stage_workspace_copy(kb_path: str | Path, workspaces_dir: str | Path, job_id: str) -> Path:
    workspaces_root = Path(workspaces_dir)
    workspaces_root.mkdir(parents=True, exist_ok=True)
    workspace = workspaces_root / job_id
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(kb_path, workspace / "knowledge-base")
    return workspace
