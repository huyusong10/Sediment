# ruff: noqa: E501
"""
server.py — Sediment MCP + Web Server

Stable read tools:
  - knowledge_list
  - knowledge_read
  - knowledge_ask

Enterprise workflow tools:
  - knowledge_submit_text
  - knowledge_submit_document
  - knowledge_health_report
  - knowledge_submission_queue
  - knowledge_job_status
  - knowledge_review_decide

Runs as an HTTP server using SSE transport for MCP, plus REST and Web routes for
portal/admin surfaces.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml
from mcp import types
from mcp.server import Server

from sediment.agent_runner import get_agent_runner
from sediment.control import (
    admin_overview_payload,
    apply_review_decision,
    enqueue_ingest_job,
    enqueue_tidy_job,
    resolve_tidy_issue,
    review_detail_payload,
    submit_document_request,
    submit_text_request,
    system_status_payload,
)
from sediment.i18n import tr
from sediment.instances import user_state_root
from sediment.kb import resolve_kb_document_path
from sediment.llm_cli import build_cli_command, collect_output
from sediment.package_data import read_skill_text
from sediment.platform_services import (
    build_health_issue_queue,
    detect_submitter_ip,
    get_entry_detail,
    get_health_payload,
    get_portal_home,
    graph_payload,
    list_reviews_with_jobs,
    save_entry,
    search_kb,
)
from sediment.platform_store import PlatformStore, utc_now
from sediment.quartz_runtime import (
    build_quartz_site,
    quartz_runtime_available,
    quartz_site_available,
    quartz_status,
)
from sediment.runtime import (
    admin_session_cookie_name as runtime_admin_session_cookie_name,
)
from sediment.runtime import (
    admin_session_ttl_seconds as runtime_admin_session_ttl_seconds,
)
from sediment.runtime import (
    admin_token as runtime_admin_token,
)
from sediment.runtime import (
    build_store,
)
from sediment.runtime import (
    config_path as runtime_config_path,
)
from sediment.runtime import (
    host as runtime_host,
)
from sediment.runtime import (
    instance_name as runtime_instance_name,
)
from sediment.runtime import (
    instance_root as runtime_instance_root,
)
from sediment.runtime import (
    job_max_attempts as runtime_job_max_attempts,
)
from sediment.runtime import (
    job_stale_after_seconds as runtime_job_stale_after_seconds,
)
from sediment.runtime import (
    kb_path as runtime_kb_path,
)
from sediment.runtime import (
    knowledge_name as runtime_knowledge_name,
)
from sediment.runtime import (
    max_text_submission_chars as runtime_max_text_submission_chars,
)
from sediment.runtime import (
    max_upload_bytes as runtime_max_upload_bytes,
)
from sediment.runtime import (
    platform_paths as runtime_platform_paths,
)
from sediment.runtime import (
    port as runtime_port,
)
from sediment.runtime import (
    run_jobs_in_process as runtime_run_jobs_in_process,
)
from sediment.runtime import (
    secure_cookies as runtime_secure_cookies,
)
from sediment.runtime import (
    session_secret as runtime_session_secret,
)
from sediment.runtime import (
    sse_endpoint as runtime_sse_endpoint,
)
from sediment.runtime import (
    submission_dedupe_window_seconds as runtime_submission_dedupe_window_seconds,
)
from sediment.runtime import (
    submission_rate_limit_count as runtime_submission_rate_limit_count,
)
from sediment.runtime import (
    submission_rate_limit_window_seconds as runtime_submission_rate_limit_window_seconds,
)
from sediment.runtime import (
    trust_proxy_headers as runtime_trust_proxy_headers,
)
from sediment.runtime import (
    trusted_proxy_cidrs as runtime_trusted_proxy_cidrs,
)
from sediment.settings import load_settings
from sediment.skills.explore.scripts.kb_query import (
    inventory,
    prepare_explore_context,
    validate_answer,
)
from sediment.web_ui import admin_html, admin_login_html, portal_graph_html, portal_html

KB_PATH = runtime_kb_path()
INSTANCE_NAME = runtime_instance_name()
INSTANCE_ROOT = runtime_instance_root()
KNOWLEDGE_NAME = runtime_knowledge_name()
CONFIG_PATH = runtime_config_path()
HOST = runtime_host()
PORT = runtime_port()
SSE_ENDPOINT = runtime_sse_endpoint()
ADMIN_TOKEN = runtime_admin_token()
STARTUP_ADMIN_TOKEN = os.environ.get("SEDIMENT_STARTUP_ADMIN_TOKEN", "").strip()
SESSION_SECRET = runtime_session_secret()
ADMIN_SESSION_COOKIE_NAME = runtime_admin_session_cookie_name()
ADMIN_SESSION_TTL_SECONDS = runtime_admin_session_ttl_seconds()
SECURE_COOKIES = runtime_secure_cookies()
TRUST_PROXY_HEADERS = runtime_trust_proxy_headers()
TRUSTED_PROXY_CIDRS = runtime_trusted_proxy_cidrs()
SUBMISSION_RATE_LIMIT_COUNT = runtime_submission_rate_limit_count()
SUBMISSION_RATE_LIMIT_WINDOW_SECONDS = runtime_submission_rate_limit_window_seconds()
SUBMISSION_DEDUPE_WINDOW_SECONDS = runtime_submission_dedupe_window_seconds()
MAX_TEXT_SUBMISSION_CHARS = runtime_max_text_submission_chars()
MAX_UPLOAD_BYTES = runtime_max_upload_bytes()
JOB_MAX_ATTEMPTS = runtime_job_max_attempts()
JOB_STALE_AFTER_SECONDS = runtime_job_stale_after_seconds()
RUN_JOBS_IN_PROCESS = runtime_run_jobs_in_process()
_PROJECT_ROOT = INSTANCE_ROOT
QUARTZ_SITE_DIR = runtime_platform_paths()["state_dir"] / "quartz" / "site"
QUARTZ_RUNTIME_DIR = user_state_root() / "quartz-runtime" / "quartz"
DEFAULT_LOCALE = load_settings()["locale"]

DEFAULT_CONTRACT = {
    "shortlist_limit": 8,
    "neighbor_depth": 2,
    "max_context_entries": 12,
    "max_snippets_per_entry": 2,
    "snippet_char_limit": 320,
    "cli_timeout_seconds": 150,
}

_EXPLORE_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "exploration_summary": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "entries_scanned": {"type": "integer"},
                    "entries_read": {"type": "integer"},
                    "links_followed": {"type": "integer"},
                    "mode": {"type": "string"},
                },
                "required": ["entries_scanned", "entries_read", "links_followed", "mode"],
            },
            "gaps": {"type": "array", "items": {"type": "string"}},
            "contradictions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "entries": {"type": "array", "items": {"type": "string"}},
                        "conflict": {"type": "string"},
                        "analysis": {"type": "string"},
                    },
                    "required": ["entries", "conflict", "analysis"],
                },
            },
        },
        "required": [
            "answer",
            "sources",
            "confidence",
            "exploration_summary",
            "gaps",
            "contradictions",
        ],
    },
    ensure_ascii=False,
)

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------


def _platform_paths() -> dict[str, Path]:
    return runtime_platform_paths()


def _platform_store() -> PlatformStore:
    return build_store()


def _agent_runner():
    paths = _platform_paths()
    store = _platform_store()
    return get_agent_runner(
        project_root=_PROJECT_ROOT,
        kb_path=KB_PATH,
        workspaces_dir=paths["workspaces_dir"],
        store=store,
    )


def _request_locale(request) -> str:
    raw = str(request.query_params.get("lang", "")).strip().lower()
    if raw.startswith("zh"):
        return "zh"
    if raw.startswith("en"):
        return "en"
    header = str(request.headers.get("accept-language", "")).strip().lower()
    if header.startswith("zh"):
        return "zh"
    if header.startswith("en"):
        return "en"
    return DEFAULT_LOCALE


def _path_with_locale(path: str, locale: str) -> str:
    joiner = "&" if "?" in path else "?"
    return f"{path}{joiner}lang={locale}"


def _session_secret_bytes() -> bytes | None:
    secret = SESSION_SECRET or STARTUP_ADMIN_TOKEN or ADMIN_TOKEN
    if not secret:
        return None
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _admin_auth_required() -> bool:
    return bool(ADMIN_TOKEN or STARTUP_ADMIN_TOKEN)


def _token_matches(candidate: str) -> bool:
    token = candidate.strip()
    return bool(token) and token in {ADMIN_TOKEN, STARTUP_ADMIN_TOKEN}


def _build_admin_session_cookie() -> str:
    secret = _session_secret_bytes()
    if secret is None:
        raise RuntimeError("admin session secret is unavailable")
    expires_at = int(time.time()) + ADMIN_SESSION_TTL_SECONDS
    payload = f"admin:{expires_at}"
    signature = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{expires_at}.{signature}"


def _verify_admin_session_cookie(cookie_value: str | None) -> bool:
    if not cookie_value:
        return False
    secret = _session_secret_bytes()
    if secret is None:
        return False
    expires_raw, sep, signature = str(cookie_value).partition(".")
    if not sep:
        return False
    try:
        expires_at = int(expires_raw)
    except ValueError:
        return False
    if expires_at <= int(time.time()):
        return False
    payload = f"admin:{expires_at}"
    expected = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _is_admin_authorized(request) -> bool:
    if not _admin_auth_required():
        return True
    headers = dict(request.headers)
    auth_header = headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return _verify_admin_session_cookie(request.cookies.get(ADMIN_SESSION_COOKIE_NAME))
    return _token_matches(auth_header.removeprefix("Bearer "))


def _set_admin_session_cookie(response) -> None:
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        value=_build_admin_session_cookie(),
        max_age=ADMIN_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        secure=SECURE_COOKIES,
        path="/",
    )


def _clear_admin_session_cookie(response) -> None:
    response.delete_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
        secure=SECURE_COOKIES,
    )


# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

app = Server("sediment")


@app.list_tools()
async def _app_list_tools() -> list[types.Tool]:
    return _tool_definitions()


def _tool_definitions() -> list[types.Tool]:
    return [
        types.Tool(
            name="knowledge_list",
            description=tr("tool.knowledge_list.description"),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="knowledge_read",
            description=tr("tool.knowledge_read.description"),
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": tr("tool.knowledge_read.filename"),
                    }
                },
                "required": ["filename"],
            },
        ),
        types.Tool(
            name="knowledge_ask",
            description=tr("tool.knowledge_ask.description"),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": tr("tool.knowledge_ask.question"),
                    }
                },
                "required": ["question"],
            },
        ),
        types.Tool(
            name="knowledge_submit_text",
            description=tr("tool.knowledge_submit_text.description"),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "submitter_name": {"type": "string"},
                    "submission_type": {"type": "string"},
                },
                "required": ["title", "content", "submitter_name"],
            },
        ),
        types.Tool(
            name="knowledge_submit_document",
            description=tr("tool.knowledge_submit_document.description"),
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "mime_type": {"type": "string"},
                    "content_base64": {"type": "string"},
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string"},
                                "relative_path": {"type": "string"},
                                "mime_type": {"type": "string"},
                                "content_base64": {"type": "string"},
                            },
                            "required": ["filename", "content_base64"],
                        },
                    },
                    "submitter_name": {"type": "string"},
                },
                "required": ["submitter_name"],
            },
        ),
        types.Tool(
            name="knowledge_health_report",
            description=tr("tool.knowledge_health_report.description"),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="knowledge_platform_status",
            description=tr("tool.knowledge_platform_status.description"),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="knowledge_submission_queue",
            description=tr("tool.knowledge_submission_queue.description"),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="knowledge_job_status",
            description=tr("tool.knowledge_job_status.description"),
            inputSchema={
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="knowledge_tidy_request",
            description=tr("tool.knowledge_tidy_request.description"),
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "issue_type": {"type": "string"},
                    "actor_name": {"type": "string"},
                },
                "required": ["target"],
            },
        ),
        types.Tool(
            name="knowledge_review_decide",
            description=tr("tool.knowledge_review_decide.description"),
            inputSchema={
                "type": "object",
                "properties": {
                    "review_id": {"type": "string"},
                    "decision": {"type": "string"},
                    "reviewer_name": {"type": "string"},
                    "comment": {"type": "string"},
                },
                "required": ["review_id", "decision", "reviewer_name"],
            },
        ),
    ]


@app.call_tool()
async def _app_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    result = await _dispatch_tool(name, arguments)
    return [types.TextContent(type="text", text=str(result))]


async def _dispatch_tool(name: str, arguments: dict):
    if name == "knowledge_list":
        return await _knowledge_list()
    if name == "knowledge_read":
        return await _knowledge_read(arguments.get("filename", ""))
    if name == "knowledge_ask":
        return await _knowledge_ask(arguments.get("question", ""))
    if name == "knowledge_submit_text":
        return await _knowledge_submit_text(
            title=arguments.get("title", ""),
            content=arguments.get("content", ""),
            submitter_name=arguments.get("submitter_name", ""),
            submission_type=arguments.get("submission_type", "text"),
        )
    if name == "knowledge_submit_document":
        return await _knowledge_submit_document(
            filename=arguments.get("filename", ""),
            mime_type=arguments.get("mime_type", ""),
            content_base64=arguments.get("content_base64", ""),
            submitter_name=arguments.get("submitter_name", ""),
            files=arguments.get("files"),
        )
    if name == "knowledge_health_report":
        return await _knowledge_health_report()
    if name == "knowledge_platform_status":
        return await _knowledge_platform_status()
    if name == "knowledge_submission_queue":
        return await _knowledge_submission_queue(
            status=arguments.get("status"),
            limit=arguments.get("limit", 50),
        )
    if name == "knowledge_job_status":
        return await _knowledge_job_status(arguments.get("job_id", ""))
    if name == "knowledge_tidy_request":
        return await _knowledge_tidy_request(
            target=arguments.get("target", ""),
            issue_type=arguments.get("issue_type"),
            actor_name=arguments.get("actor_name", "mcp"),
        )
    if name == "knowledge_review_decide":
        return await _knowledge_review_decide(
            review_id=arguments.get("review_id", ""),
            decision=arguments.get("decision", ""),
            reviewer_name=arguments.get("reviewer_name", ""),
            comment=arguments.get("comment", ""),
        )
    return f'ERROR: Unknown tool "{name}".'


async def _knowledge_list() -> list[str]:
    data = inventory(KB_PATH)
    names = set(data["entries"]) | set(data["placeholders"]) | set(data.get("indexes", []))
    return sorted(names)


async def _knowledge_read(filename: str) -> str:
    if "/" in filename or "\\" in filename or ".." in filename:
        return f"ERROR: Invalid filename '{filename}'. Path separators are not allowed."
    if not filename:
        return "ERROR: filename must not be empty."
    candidate = resolve_kb_document_path(KB_PATH, filename)
    if candidate is not None:
        return candidate.read_text(encoding="utf-8")
    return f"ERROR: Entry '{filename}' not found in knowledge base."


async def _knowledge_ask(question: str) -> str:
    result = answer_question(question, KB_PATH, _PROJECT_ROOT)
    return json.dumps(result, ensure_ascii=False)


async def _knowledge_submit_text(
    *,
    title: str,
    content: str,
    submitter_name: str,
    submission_type: str = "text",
) -> str:
    try:
        record = submit_text_request(
            store=_platform_store(),
            kb_path=KB_PATH,
            title=title,
            content=content,
            submitter_name=submitter_name,
            submitter_ip="mcp",
            submission_type=submission_type,
            submitter_user_id="mcp",
            rate_limit_count=1_000_000,
            rate_limit_window_seconds=1,
            max_text_chars=MAX_TEXT_SUBMISSION_CHARS,
            dedupe_window_seconds=SUBMISSION_DEDUPE_WINDOW_SECONDS,
        )
    except (PermissionError, FileExistsError, ValueError) as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return json.dumps(record, ensure_ascii=False)


async def _knowledge_submit_document(
    *,
    filename: str,
    mime_type: str,
    content_base64: str,
    submitter_name: str,
    files: list[dict[str, Any]] | None = None,
) -> str:
    try:
        file_bytes = (
            base64.b64decode(content_base64, validate=True)
            if content_base64
            else b""
        )
        decoded_files = _decode_uploaded_files(files or [])
    except ValueError as exc:
        return json.dumps({"error": f"invalid base64 payload: {exc}"}, ensure_ascii=False)
    try:
        record = submit_document_request(
            store=_platform_store(),
            uploads_dir=_platform_paths()["uploads_dir"],
            filename=filename,
            mime_type=mime_type,
            file_bytes=file_bytes,
            uploads=decoded_files,
            submitter_name=submitter_name,
            submitter_ip="mcp",
            submitter_user_id="mcp",
            rate_limit_count=1_000_000,
            rate_limit_window_seconds=1,
            max_upload_bytes=MAX_UPLOAD_BYTES,
            dedupe_window_seconds=SUBMISSION_DEDUPE_WINDOW_SECONDS,
        )
    except (PermissionError, FileExistsError, ValueError) as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return json.dumps(record, ensure_ascii=False)


async def _knowledge_health_report() -> str:
    payload = get_health_payload(KB_PATH)
    return json.dumps(payload, ensure_ascii=False)


async def _knowledge_platform_status() -> str:
    store = _platform_store()
    payload = system_status_payload(
        store=store,
        kb_path=KB_PATH,
        paths=_platform_paths(),
        instance_name=INSTANCE_NAME,
        knowledge_name=KNOWLEDGE_NAME,
        instance_root=INSTANCE_ROOT,
        config_path=CONFIG_PATH,
        host=HOST,
        port=PORT,
        sse_endpoint=SSE_ENDPOINT,
        auth_required=_admin_auth_required(),
        run_jobs_in_process=RUN_JOBS_IN_PROCESS,
        submission_rate_limit_count=SUBMISSION_RATE_LIMIT_COUNT,
        submission_rate_limit_window_seconds=SUBMISSION_RATE_LIMIT_WINDOW_SECONDS,
        submission_dedupe_window_seconds=SUBMISSION_DEDUPE_WINDOW_SECONDS,
        max_text_submission_chars=MAX_TEXT_SUBMISSION_CHARS,
        max_upload_bytes=MAX_UPLOAD_BYTES,
        job_max_attempts=JOB_MAX_ATTEMPTS,
        job_stale_after_seconds=JOB_STALE_AFTER_SECONDS,
        trust_proxy_headers=TRUST_PROXY_HEADERS,
        trusted_proxy_cidrs=[str(item) for item in TRUSTED_PROXY_CIDRS],
    )
    return json.dumps(payload, ensure_ascii=False)


async def _knowledge_submission_queue(status: str | None = None, limit: int = 50) -> str:
    store = _platform_store()
    payload = {"submissions": store.list_submissions(status=status, limit=limit)}
    return json.dumps(payload, ensure_ascii=False)


async def _knowledge_job_status(job_id: str) -> str:
    store = _platform_store()
    job = store.get_job(job_id)
    if job is None:
        return json.dumps({"error": "job not found"}, ensure_ascii=False)
    return json.dumps(job, ensure_ascii=False)


async def _knowledge_tidy_request(
    *,
    target: str,
    issue_type: str | None = None,
    actor_name: str = "mcp",
) -> str:
    target = str(target).strip()
    if not target:
        return json.dumps({"error": "target must not be empty"}, ensure_ascii=False)
    store = _platform_store()
    issue = resolve_tidy_issue(
        kb_path=KB_PATH,
        target=target,
        issue_type=issue_type,
    )
    job = enqueue_tidy_job(
        store=store,
        kb_path=KB_PATH,
        issue=issue,
        actor_name=actor_name,
        max_attempts=JOB_MAX_ATTEMPTS,
    )
    if RUN_JOBS_IN_PROCESS:
        _agent_runner().submit(job["id"])
    return json.dumps({"job": job, "issue": issue}, ensure_ascii=False)


async def _knowledge_review_decide(
    *,
    review_id: str,
    decision: str,
    reviewer_name: str,
    comment: str = "",
) -> str:
    result = apply_review_decision(
        store=_platform_store(),
        kb_path=KB_PATH,
        review_id=review_id,
        decision=decision,
        reviewer_name=reviewer_name,
        comment=comment,
    )
    return json.dumps(result, ensure_ascii=False)


def answer_question(question: str, kb_path: Path, project_root: Path) -> dict[str, Any]:
    question = question.strip()
    if not question:
        return _error_payload("Question must not be empty.")

    inventory_data = inventory(kb_path)
    if not inventory_data["entries"]:
        return {
            "answer": (
                "Knowledge base has no formal entries yet, "
                "so explore cannot answer reliably."
            ),
            "sources": [],
            "confidence": "low",
            "exploration_summary": {
                "entries_scanned": 0,
                "entries_read": 0,
                "links_followed": 0,
                "mode": "no-evidence",
            },
            "gaps": ["No formal entries are available in the knowledge base."],
            "contradictions": [],
        }

    try:
        skill_body, runtime_contract, skill_label = _load_explore_skill(project_root)
        context = prepare_explore_context(
            question,
            inventory_data=inventory_data,
            shortlist_limit=runtime_contract["shortlist_limit"],
            neighbor_depth=runtime_contract["neighbor_depth"],
            max_context_entries=runtime_contract["max_context_entries"],
            max_snippets_per_entry=runtime_contract["max_snippets_per_entry"],
            snippet_char_limit=runtime_contract["snippet_char_limit"],
        )

        if not context["expanded_candidates"]:
            return {
                "answer": "No sufficiently relevant knowledge entries were found for this question.",
                "sources": [],
                "confidence": "low",
                "exploration_summary": {
                    "entries_scanned": len(inventory_data["entries"]),
                    "entries_read": 0,
                    "links_followed": 0,
                    "mode": "no-match",
                },
                "gaps": ["The current KB does not expose an obvious formal entry for this question."],
                "contradictions": [],
            }

        payload = {"question": question, "runtime_contract": runtime_contract, "context": context}
        return _run_validated_explore(
            question=question,
            skill_body=skill_body,
            runtime_contract=runtime_contract,
            context=context,
            payload=payload,
            project_root=project_root,
            skill_label=skill_label,
            inventory_data=inventory_data,
        )
    except RuntimeError as exc:
        return _error_payload(str(exc))


def _load_explore_skill(project_root: Path) -> tuple[str, dict[str, Any], str]:
    local_skill_path = project_root / "skills" / "explore" / "SKILL.md"
    if local_skill_path.exists():
        content = local_skill_path.read_text(encoding="utf-8")
        skill_label = str(local_skill_path)
    else:
        try:
            content = read_skill_text("explore")
            skill_label = "package:sediment.skills.explore/SKILL.md"
        except (FileNotFoundError, ModuleNotFoundError) as exc:
            raise RuntimeError("Explore skill not found in package resources.") from exc

    frontmatter, body = _split_frontmatter(content)
    runtime_contract = dict(DEFAULT_CONTRACT)
    extra_contract = frontmatter.get("runtime_contract") or {}
    if isinstance(extra_contract, dict):
        runtime_contract.update(
            {
                key: value
                for key, value in extra_contract.items()
                if key in DEFAULT_CONTRACT and isinstance(value, type(DEFAULT_CONTRACT[key]))
            }
        )
    return body.strip(), runtime_contract, skill_label


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not match:
        return {}, text
    frontmatter = yaml.safe_load(match.group(1)) or {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return frontmatter, text[match.end() :]


def _build_explore_prompt(
    question: str,
    skill_body: str,
    runtime_contract: dict[str, Any],
    context: dict[str, Any],
    retry_reason: str | None = None,
) -> str:
    payload = {
        "question": question,
        "runtime_contract": runtime_contract,
        "prepared_context": context,
    }
    preamble = [
        "You are the internal Sediment explore runtime.",
        "Treat the prepared KB context as the default starting path derived from root-first index routing.",
        "If your runtime supports white-box KB search, you may inspect additional KB indexes or entry files to verify or deepen the answer.",
        "Do not read raw materials outside the KB. Do not invent sources. Placeholder entries are weak evidence and must not be the only basis of an answer.",
        "Return JSON only. No prose before or after the JSON object.",
    ]
    if retry_reason:
        preamble.append(
            "Previous response was invalid. Fix it and return one valid JSON object only. "
            f"Failure reason: {retry_reason}"
        )
    return "\n\n".join(
        [
            *preamble,
            skill_body,
            "## Prepared Context",
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    )


def _run_validated_explore(
    *,
    question: str,
    skill_body: str,
    runtime_contract: dict[str, Any],
    context: dict[str, Any],
    payload: dict[str, Any],
    project_root: Path,
    skill_label: str,
    inventory_data: dict[str, Any],
) -> dict[str, Any]:
    retry_reason = None
    for _ in range(2):
        prompt = _build_explore_prompt(
            question,
            skill_body,
            runtime_contract,
            context,
            retry_reason=retry_reason,
        )
        raw_output = _run_explore_cli(
            prompt=prompt,
            skill_body=skill_body,
            project_root=project_root,
            skill_label=skill_label,
            payload=payload,
            timeout_seconds=runtime_contract["cli_timeout_seconds"],
        )

        try:
            parsed_output = _parse_cli_json(raw_output)
        except RuntimeError:
            retry_reason = "response was not a valid JSON object"
            continue

        validation = validate_answer(parsed_output, inventory_data=inventory_data)
        if validation["valid"]:
            return validation["normalized"]
        retry_reason = "; ".join(validation["errors"])

    raise RuntimeError(f"Explore runtime returned invalid JSON: {retry_reason}")


def _run_explore_cli(
    *,
    prompt: str,
    skill_body: str,
    project_root: Path,
    skill_label: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> str:
    settings = load_settings()

    with tempfile.TemporaryDirectory(prefix="sediment-explore-") as temp_dir:
        temp_root = Path(temp_dir)
        prompt_file = temp_root / "prompt.txt"
        payload_file = temp_root / "payload.json"
        skill_file = temp_root / "skill.md"
        prompt_file.write_text(prompt, encoding="utf-8")
        payload_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        skill_file.write_text(skill_body, encoding="utf-8")

        invocation = build_cli_command(
            settings,
            prompt=prompt,
            prompt_file=prompt_file,
            payload_file=payload_file,
            skill_file=skill_file,
            cwd=project_root,
            extra_args=["--json-schema", _EXPLORE_JSON_SCHEMA],
        )
        try:
            result = subprocess.run(
                invocation.command,
                input=invocation.stdin_data,
                text=True,
                capture_output=True,
                cwd=str(project_root),
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            backend = settings["agent"]["backend"]
            raise RuntimeError(
                f"Explore runtime CLI is unavailable for backend {backend}: "
                f"{exc.filename or invocation.command[0]}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Explore runtime timed out after {timeout_seconds} seconds."
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            detail = stderr or stdout or f"exit code {result.returncode}"
            raise RuntimeError(f"Explore runtime CLI failed: {detail}")
        output = collect_output(invocation, stdout=result.stdout, stderr=result.stderr)
        if not output:
            raise RuntimeError("Explore runtime CLI returned no output.")
        return output


def _parse_cli_json(raw_output: str) -> dict[str, Any]:
    candidates = [raw_output.strip()]
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", raw_output, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())
    start = raw_output.find("{")
    end = raw_output.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw_output[start : end + 1].strip())

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise RuntimeError("Explore runtime did not return a valid JSON object.")


def _error_payload(message: str) -> dict[str, Any]:
    return {
        "answer": message,
        "sources": [],
        "confidence": "low",
        "exploration_summary": {
            "entries_scanned": 0,
            "entries_read": 0,
            "links_followed": 0,
            "mode": "error",
        },
        "gaps": [message],
        "contradictions": [],
        "error": message,
    }


# ---------------------------------------------------------------------------
# HTTP / REST / Web
# ---------------------------------------------------------------------------


def _json_response(payload: Any, status: int = 200):
    from starlette.responses import JSONResponse

    return JSONResponse(payload, status_code=status)


def _html_response(html: str, status: int = 200):
    from starlette.responses import HTMLResponse

    return HTMLResponse(html, status_code=status)


def _redirect(url: str):
    from starlette.responses import RedirectResponse

    return RedirectResponse(url)


async def _request_json_or_empty(request) -> dict[str, Any]:
    try:
        body = await request.body()
    except Exception:  # noqa: BLE001
        return {}
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _decode_uploaded_files(raw_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decoded: list[dict[str, Any]] = []
    for item in raw_files:
        if not isinstance(item, dict):
            continue
        payload = str(item.get("content_base64", "")).strip()
        if not payload:
            continue
        decoded.append(
            {
                "filename": str(item.get("filename", "")),
                "relative_path": str(item.get("relative_path", "")),
                "mime_type": str(item.get("mime_type", "")),
                "file_bytes": base64.b64decode(payload, validate=True),
            }
        )
    return decoded


async def _portal_page(request):
    return _html_response(
        portal_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=_request_locale(request),
        )
    )


async def _portal_graph_page(request):
    locale = _request_locale(request)
    return _html_response(
        portal_graph_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=locale,
            quartz=quartz_status(
                runtime_dir=QUARTZ_RUNTIME_DIR,
                site_dir=QUARTZ_SITE_DIR,
            ),
            admin_kb_path=_path_with_locale("/admin/kb", locale),
        )
    )


async def _admin_page(request):
    return await _admin_overview_page(request)


async def _admin_overview_page(request):
    locale = _request_locale(request)
    if not _is_admin_authorized(request):
        return _html_response(
            admin_login_html(
                knowledge_name=KNOWLEDGE_NAME,
                instance_name=INSTANCE_NAME,
                locale=locale,
                next_path=_path_with_locale("/admin", locale),
            ),
            status=200,
        )
    return _html_response(
        admin_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=locale,
            section="overview",
            quartz=quartz_status(runtime_dir=QUARTZ_RUNTIME_DIR, site_dir=QUARTZ_SITE_DIR),
        )
    )


async def _admin_kb_page(request):
    locale = _request_locale(request)
    if not _is_admin_authorized(request):
        return _html_response(
            admin_login_html(
                knowledge_name=KNOWLEDGE_NAME,
                instance_name=INSTANCE_NAME,
                locale=locale,
                next_path=_path_with_locale("/admin/kb", locale),
            ),
            status=200,
        )
    return _html_response(
        admin_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=locale,
            section="kb",
            quartz=quartz_status(runtime_dir=QUARTZ_RUNTIME_DIR, site_dir=QUARTZ_SITE_DIR),
        )
    )


async def _admin_reviews_page(request):
    locale = _request_locale(request)
    if not _is_admin_authorized(request):
        return _html_response(
            admin_login_html(
                knowledge_name=KNOWLEDGE_NAME,
                instance_name=INSTANCE_NAME,
                locale=locale,
                next_path=_path_with_locale("/admin/reviews", locale),
            ),
            status=200,
        )
    return _html_response(
        admin_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=locale,
            section="reviews",
            quartz=quartz_status(runtime_dir=QUARTZ_RUNTIME_DIR, site_dir=QUARTZ_SITE_DIR),
        )
    )


async def _root_page(request):
    return _redirect("/portal")


async def _healthz(request):
    return _json_response(
        {
            "status": "ok",
            "server_time": utc_now(),
            "worker_mode": "in_process" if RUN_JOBS_IN_PROCESS else "queue",
        }
    )


async def _api_portal_home(request):
    store = _platform_store()
    return _json_response(get_portal_home(KB_PATH, store=store))


async def _api_portal_search(request):
    query = request.query_params.get("q", "")
    return _json_response(search_kb(KB_PATH, query))


async def _api_portal_entry(request):
    try:
        payload = get_entry_detail(KB_PATH, request.path_params["name"])
    except FileNotFoundError:
        return _json_response({"error": "entry not found"}, status=404)
    return _json_response(payload)


async def _api_portal_graph(request):
    return _json_response(graph_payload(KB_PATH))


def _quartz_site_available() -> bool:
    return quartz_site_available(QUARTZ_SITE_DIR)


def _quartz_runtime_available() -> bool:
    return quartz_runtime_available(QUARTZ_RUNTIME_DIR)


async def _api_portal_submit_text(request):
    body = await request.json()
    try:
        record = submit_text_request(
            store=_platform_store(),
            kb_path=KB_PATH,
            title=str(body.get("title", "")),
            content=str(body.get("content", "")),
            submitter_name=str(body.get("submitter_name", "")),
            submitter_ip=detect_submitter_ip(
                dict(request.headers),
                request.client.host if request.client else None,
                trust_proxy_headers=TRUST_PROXY_HEADERS,
                trusted_proxy_cidrs=TRUSTED_PROXY_CIDRS,
            ),
            submission_type=str(body.get("submission_type", "text")),
            submitter_user_id=None,
            rate_limit_count=SUBMISSION_RATE_LIMIT_COUNT,
            rate_limit_window_seconds=SUBMISSION_RATE_LIMIT_WINDOW_SECONDS,
            max_text_chars=MAX_TEXT_SUBMISSION_CHARS,
            dedupe_window_seconds=SUBMISSION_DEDUPE_WINDOW_SECONDS,
        )
    except PermissionError as exc:
        return _json_response({"error": str(exc)}, status=429)
    except FileExistsError as exc:
        return _json_response({"error": str(exc)}, status=409)
    except ValueError as exc:
        return _json_response({"error": str(exc)}, status=400)
    return _json_response(record, status=201)


async def _api_portal_submit_document(request):
    body = await request.json()
    try:
        file_bytes = (
            base64.b64decode(str(body.get("content_base64", "")), validate=True)
            if str(body.get("content_base64", "")).strip()
            else b""
        )
        decoded_files = _decode_uploaded_files(body.get("files") or [])
        record = submit_document_request(
            store=_platform_store(),
            uploads_dir=_platform_paths()["uploads_dir"],
            filename=str(body.get("filename", "")),
            mime_type=str(body.get("mime_type", "")),
            file_bytes=file_bytes,
            uploads=decoded_files,
            submitter_name=str(body.get("submitter_name", "")),
            submitter_ip=detect_submitter_ip(
                dict(request.headers),
                request.client.host if request.client else None,
                trust_proxy_headers=TRUST_PROXY_HEADERS,
                trusted_proxy_cidrs=TRUSTED_PROXY_CIDRS,
            ),
            submitter_user_id=None,
            rate_limit_count=SUBMISSION_RATE_LIMIT_COUNT,
            rate_limit_window_seconds=SUBMISSION_RATE_LIMIT_WINDOW_SECONDS,
            max_upload_bytes=MAX_UPLOAD_BYTES,
            dedupe_window_seconds=SUBMISSION_DEDUPE_WINDOW_SECONDS,
        )
    except PermissionError as exc:
        return _json_response({"error": str(exc)}, status=429)
    except FileExistsError as exc:
        return _json_response({"error": str(exc)}, status=409)
    except (ValueError, binascii.Error) as exc:
        return _json_response({"error": str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001
        return _json_response({"error": str(exc)}, status=400)
    return _json_response(record, status=201)


async def _admin_guard(request):
    if not _is_admin_authorized(request):
        return _json_response(
            {
                "error": "admin authentication is required",
                "auth_required": True,
                "login_path": "/admin",
            },
            status=401,
        )
    return None


def _system_status_payload(store: PlatformStore) -> dict[str, Any]:
    paths = _platform_paths()
    return system_status_payload(
        store=store,
        kb_path=KB_PATH,
        paths=paths,
        instance_name=INSTANCE_NAME,
        knowledge_name=KNOWLEDGE_NAME,
        instance_root=INSTANCE_ROOT,
        config_path=CONFIG_PATH,
        host=HOST,
        port=PORT,
        sse_endpoint=SSE_ENDPOINT,
        auth_required=_admin_auth_required(),
        run_jobs_in_process=RUN_JOBS_IN_PROCESS,
        submission_rate_limit_count=SUBMISSION_RATE_LIMIT_COUNT,
        submission_rate_limit_window_seconds=SUBMISSION_RATE_LIMIT_WINDOW_SECONDS,
        submission_dedupe_window_seconds=SUBMISSION_DEDUPE_WINDOW_SECONDS,
        max_text_submission_chars=MAX_TEXT_SUBMISSION_CHARS,
        max_upload_bytes=MAX_UPLOAD_BYTES,
        job_max_attempts=JOB_MAX_ATTEMPTS,
        job_stale_after_seconds=JOB_STALE_AFTER_SECONDS,
        trust_proxy_headers=TRUST_PROXY_HEADERS,
        trusted_proxy_cidrs=[str(item) for item in TRUSTED_PROXY_CIDRS],
    )


async def _api_admin_session_status(request):
    return _json_response(
        {
            "authenticated": _is_admin_authorized(request),
            "auth_required": _admin_auth_required(),
            "cookie_name": ADMIN_SESSION_COOKIE_NAME,
            "session_ttl_seconds": ADMIN_SESSION_TTL_SECONDS,
        }
    )


async def _api_admin_session_create(request):
    body = await _request_json_or_empty(request)
    token = str(body.get("token", ""))
    if _admin_auth_required() and not _token_matches(token):
        return _json_response({"error": "invalid admin token"}, status=401)
    response = _json_response(
        {
            "authenticated": True,
            "auth_required": _admin_auth_required(),
            "session_ttl_seconds": ADMIN_SESSION_TTL_SECONDS,
        }
    )
    if _admin_auth_required():
        _set_admin_session_cookie(response)
    _platform_store().add_audit_log(
        actor_name="admin-session",
        actor_role="platform_admin",
        action="admin.session.create",
        target_type="session",
        target_id=request.client.host if request.client else "unknown",
        details={"auth_required": _admin_auth_required()},
    )
    return response


async def _api_admin_session_delete(request):
    response = _json_response(
        {"authenticated": False, "auth_required": _admin_auth_required()}
    )
    _clear_admin_session_cookie(response)
    _platform_store().add_audit_log(
        actor_name="admin-session",
        actor_role="platform_admin",
        action="admin.session.delete",
        target_type="session",
        target_id=request.client.host if request.client else "unknown",
        details={"auth_required": _admin_auth_required()},
    )
    return response


async def _api_admin_overview(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    return _json_response(
        admin_overview_payload(
            store=store,
            kb_path=KB_PATH,
            stale_after_seconds=JOB_STALE_AFTER_SECONDS,
        )
    )


async def _api_admin_health_summary(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    return _json_response(get_health_payload(KB_PATH))


async def _api_admin_health_issues(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    return _json_response({"issues": build_health_issue_queue(KB_PATH)})


async def _api_admin_submissions(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    return _json_response({"submissions": store.list_submissions(limit=200)})


async def _api_admin_submission_detail(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    submission = store.get_submission(request.path_params["submission_id"])
    if submission is None:
        return _json_response({"error": "submission not found"}, status=404)
    jobs = [
        job
        for job in store.list_jobs(limit=200)
        if job.get("source_submission_id") == submission["id"]
    ]
    return _json_response({"submission": submission, "jobs": jobs})


async def _api_admin_submission_triage(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    submission_id = request.path_params["submission_id"]
    body = await request.json()
    status = str(body.get("status", "triaged"))
    submission = store.update_submission(submission_id, status=status, notes=body.get("notes"))
    if submission is None:
        return _json_response({"error": "submission not found"}, status=404)
    store.add_audit_log(
        actor_name=str(body.get("actor_name", "admin")),
        actor_role="committer",
        action="submission.triage",
        target_type="submission",
        target_id=submission_id,
        details={"status": status, "notes": body.get("notes")},
    )
    return _json_response(submission)


async def _api_admin_run_ingest(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    body = await _request_json_or_empty(request)
    submission_id = request.path_params["submission_id"]
    try:
        job = enqueue_ingest_job(
            store=store,
            submission_id=submission_id,
            actor_name=str(body.get("actor_name", "admin")),
            max_attempts=JOB_MAX_ATTEMPTS,
        )
    except FileNotFoundError:
        return _json_response({"error": "submission not found"}, status=404)
    if RUN_JOBS_IN_PROCESS:
        _agent_runner().submit(job["id"])
    return _json_response(job, status=202)


async def _api_admin_jobs(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    return _json_response({"jobs": store.list_jobs(limit=200)})


async def _api_admin_job_detail(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    job = store.get_job(request.path_params["job_id"])
    if job is None:
        return _json_response({"error": "job not found"}, status=404)
    return _json_response(job)


async def _api_admin_job_retry(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    body = await _request_json_or_empty(request)
    try:
        job = store.retry_job(request.path_params["job_id"])
    except ValueError as exc:
        return _json_response({"error": str(exc)}, status=400)
    if job is None:
        return _json_response({"error": "job not found"}, status=404)
    if job.get("source_submission_id"):
        store.update_submission(job["source_submission_id"], status="triaged")
    store.add_audit_log(
        actor_name=str(body.get("actor_name", "admin")),
        actor_role="platform_admin",
        action="job.retry",
        target_type="job",
        target_id=job["id"],
        details={"job_type": job["job_type"]},
    )
    if RUN_JOBS_IN_PROCESS:
        _agent_runner().submit(job["id"])
    return _json_response(job, status=202)


async def _api_admin_job_cancel(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    body = await _request_json_or_empty(request)
    reason = str(body.get("reason", "job cancelled by admin"))
    try:
        job = store.cancel_job(request.path_params["job_id"], reason=reason)
    except ValueError as exc:
        return _json_response({"error": str(exc)}, status=400)
    if job is None:
        return _json_response({"error": "job not found"}, status=404)
    if job.get("source_submission_id") and job["status"] == "cancelled":
        store.update_submission(job["source_submission_id"], status="triaged")
    store.add_audit_log(
        actor_name=str(body.get("actor_name", "admin")),
        actor_role="platform_admin",
        action="job.cancel",
        target_type="job",
        target_id=job["id"],
        details={"job_type": job["job_type"], "reason": reason},
    )
    return _json_response(job)


async def _api_admin_tidy(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    body = await request.json()
    issue = body.get("issue") or {}
    job = enqueue_tidy_job(
        store=store,
        kb_path=KB_PATH,
        issue=issue,
        actor_name=str(body.get("actor_name", "admin")),
        max_attempts=JOB_MAX_ATTEMPTS,
    )
    if RUN_JOBS_IN_PROCESS:
        _agent_runner().submit(job["id"])
    return _json_response(job, status=202)


async def _api_admin_reviews(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    decision = request.query_params.get("decision")
    return _json_response({"reviews": list_reviews_with_jobs(store=_platform_store(), decision=decision)})


async def _api_admin_review_detail(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    try:
        payload = review_detail_payload(_platform_store(), request.path_params["review_id"])
    except FileNotFoundError:
        return _json_response({"error": "review not found"}, status=404)
    return _json_response(payload)


async def _api_admin_review_approve(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    body = await request.json()
    try:
        payload = apply_review_decision(
            store=_platform_store(),
            kb_path=KB_PATH,
            review_id=request.path_params["review_id"],
            decision=str(body.get("decision", "approve")),
            reviewer_name=str(body.get("reviewer_name", "admin")),
            comment=str(body.get("comment", "")),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _json_response({"error": str(exc)}, status=400)
    return _json_response(payload)


async def _api_admin_review_reject(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    body = await request.json()
    try:
        payload = apply_review_decision(
            store=_platform_store(),
            kb_path=KB_PATH,
            review_id=request.path_params["review_id"],
            decision="reject",
            reviewer_name=str(body.get("reviewer_name", "admin")),
            comment=str(body.get("comment", "")),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _json_response({"error": str(exc)}, status=400)
    return _json_response(payload)


async def _api_admin_system_status(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    return _json_response(_system_status_payload(store))


async def _api_admin_audit_logs(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    store = _platform_store()
    try:
        limit = int(request.query_params.get("limit", "50"))
    except ValueError:
        limit = 50
    return _json_response({"logs": store.list_audit_logs(limit=limit)})


async def _api_admin_entry_detail(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    try:
        payload = get_entry_detail(KB_PATH, request.path_params["name"])
    except FileNotFoundError:
        return _json_response({"error": "entry not found"}, status=404)
    return _json_response(payload)


async def _api_admin_entry_save(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    body = await request.json()
    store = _platform_store()
    try:
        payload = save_entry(
            KB_PATH,
            name=request.path_params["name"],
            content=str(body.get("content", "")),
            expected_hash=body.get("expected_hash"),
            actor_name=str(body.get("actor_name", "admin")),
            store=store,
        )
    except (RuntimeError, ValueError) as exc:
        return _json_response({"error": str(exc)}, status=400)
    return _json_response(payload)


async def _api_admin_explore(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    body = await _request_json_or_empty(request)
    question = str(body.get("question", "")).strip()
    if not question:
        return _json_response({"error": "question must not be empty"}, status=400)
    return _json_response(answer_question(question, KB_PATH, _PROJECT_ROOT))


async def _api_admin_quartz_status(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    return _json_response(quartz_status(runtime_dir=QUARTZ_RUNTIME_DIR, site_dir=QUARTZ_SITE_DIR))


async def _api_admin_quartz_build(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    body = await _request_json_or_empty(request)
    try:
        payload = build_quartz_site(
            kb_path=KB_PATH,
            runtime_dir=QUARTZ_RUNTIME_DIR,
            site_dir=QUARTZ_SITE_DIR,
            knowledge_name=KNOWLEDGE_NAME,
            locale=_request_locale(request),
        )
    except RuntimeError as exc:
        return _json_response({"error": str(exc)}, status=400)
    _platform_store().add_audit_log(
        actor_name=str(body.get("actor_name", "admin")),
        actor_role="committer",
        action="quartz.build",
        target_type="quartz_site",
        target_id=str(QUARTZ_SITE_DIR),
        details={"runtime_path": str(QUARTZ_RUNTIME_DIR)},
    )
    return _json_response(payload, status=202)


# ---------------------------------------------------------------------------
# MCP HTTP / SSE Router
# ---------------------------------------------------------------------------


def _make_router(sse):
    async def _handle_direct_jsonrpc(scope, receive, send, body_bytes):
        body: dict[str, Any] | None = None
        try:
            body = json.loads(body_bytes.decode("utf-8"))
            method = body.get("method", "")
            params = body.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            if method == "tools/call" and tool_name:
                result = await _call_tool_for_rpc(tool_name, arguments)
                response_body = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": body.get("id", 1),
                        "result": {"content": [{"type": "text", "text": result}]},
                    },
                    ensure_ascii=False,
                )
            elif method == "tools/list":
                tools = await _list_tools_for_rpc()
                tool_defs = [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema,
                    }
                    for tool in tools
                ]
                response_body = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": body.get("id", 1),
                        "result": {"tools": tool_defs},
                    },
                    ensure_ascii=False,
                )
            elif method == "initialize":
                response_body = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": body.get("id", 1),
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "sediment", "version": "0.2.0"},
                        },
                    },
                    ensure_ascii=False,
                )
            elif method == "initialized":
                response_body = json.dumps({"jsonrpc": "2.0"}, ensure_ascii=False)
            else:
                response_body = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": body.get("id", 1),
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                    },
                    ensure_ascii=False,
                )
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            response_body = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": body.get("id", 0) if isinstance(body, dict) else 0,
                    "error": {"code": -32603, "message": str(exc)},
                },
                ensure_ascii=False,
            )

        resp_bytes = response_body.encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(resp_bytes)).encode()],
                ],
            }
        )
        await send({"type": "http.response.body", "body": resp_bytes})

    async def router(scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "GET":

            async def handle_sse(scope, receive, send):
                async with sse.connect_sse(scope, receive, send) as (read_stream, write_stream):
                    await app.run(
                        read_stream,
                        write_stream,
                        app.create_initialization_options(
                            notification_options=None,
                            experimental_capabilities=None,
                        ),
                        raise_exceptions=True,
                    )

            return await handle_sse(scope, receive, send)
        if scope["type"] == "http" and scope["method"] == "POST":
            content_type = ""
            for key, value in scope.get("headers", []):
                if key.lower() == b"content-type":
                    content_type = value.decode("utf-8", errors="replace")
                    break
            body_parts = []
            while True:
                message = await receive()
                if message["type"] == "http.request":
                    body_parts.append(message.get("body", b""))
                    if not message.get("more_body", False):
                        break
            body_bytes = b"".join(body_parts)
            if "application/json" in content_type:
                return await _handle_direct_jsonrpc(scope, receive, send, body_bytes)
            return await sse.handle_post_message(scope, receive, send)

        await send(
            {
                "type": "http.response.start",
                "status": 405,
                "headers": [[b"content-type", b"text/plain"]],
            }
        )
        await send({"type": "http.response.body", "body": b"Method Not Allowed"})

    return router


async def _list_tools_for_rpc() -> list[types.Tool]:
    return _tool_definitions()


async def _call_tool_for_rpc(name: str, arguments: dict) -> str:
    result = await _dispatch_tool(name, arguments)
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False)


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                from starlette.datastructures import MutableHeaders

                headers = MutableHeaders(raw=message["headers"])
                path = scope.get("path", "")
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "no-referrer")
                if path.startswith("/quartz"):
                    headers.setdefault("X-Frame-Options", "SAMEORIGIN")
                    headers.setdefault(
                        "Content-Security-Policy",
                        "default-src 'self'; "
                        "img-src 'self' data: blob:; "
                        "style-src 'self' 'unsafe-inline'; "
                        "script-src 'self' 'unsafe-inline'; "
                        "connect-src 'self'; "
                        "font-src 'self' data:; "
                        "base-uri 'self'; "
                        "form-action 'self'; "
                        "frame-ancestors 'self'",
                    )
                else:
                    headers.setdefault("X-Frame-Options", "DENY")
                    headers.setdefault(
                        "Content-Security-Policy",
                        "default-src 'self'; "
                        "img-src 'self' data:; "
                        "style-src 'self' 'unsafe-inline'; "
                        "script-src 'self' 'unsafe-inline'; "
                        "connect-src 'self'; "
                        "base-uri 'self'; "
                        "form-action 'self'; "
                        "frame-ancestors 'none'",
                    )
                if path.startswith("/admin") or path.startswith("/api/admin"):
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_wrapper)


def create_starlette_app():
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Mount, Route
    from starlette.staticfiles import StaticFiles

    _platform_store()
    sse = SseServerTransport("")
    routes = [
        Route("/", _root_page),
        Route("/healthz", _healthz),
        Route("/portal", _portal_page),
        Route("/portal/graph-view", _portal_graph_page),
        Route("/admin", _admin_overview_page),
        Route("/admin/kb", _admin_kb_page),
        Route("/admin/reviews", _admin_reviews_page),
        Route("/api/admin/session", _api_admin_session_status, methods=["GET"]),
        Route("/api/admin/session", _api_admin_session_create, methods=["POST"]),
        Route("/api/admin/session", _api_admin_session_delete, methods=["DELETE"]),
        Route("/api/portal/home", _api_portal_home),
        Route("/api/portal/search", _api_portal_search),
        Route("/api/portal/entries/{name:str}", _api_portal_entry),
        Route("/api/portal/graph", _api_portal_graph),
        Route("/api/portal/submissions/text", _api_portal_submit_text, methods=["POST"]),
        Route("/api/portal/submissions/document", _api_portal_submit_document, methods=["POST"]),
        Route("/api/admin/overview", _api_admin_overview),
        Route("/api/admin/system/status", _api_admin_system_status),
        Route("/api/admin/audit", _api_admin_audit_logs),
        Route("/api/admin/health/summary", _api_admin_health_summary),
        Route("/api/admin/health/issues", _api_admin_health_issues),
        Route("/api/admin/submissions", _api_admin_submissions),
        Route("/api/admin/submissions/{submission_id:str}", _api_admin_submission_detail),
        Route("/api/admin/submissions/{submission_id:str}/triage", _api_admin_submission_triage, methods=["POST"]),
        Route("/api/admin/submissions/{submission_id:str}/run-ingest", _api_admin_run_ingest, methods=["POST"]),
        Route("/api/admin/jobs", _api_admin_jobs),
        Route("/api/admin/jobs/{job_id:str}", _api_admin_job_detail),
        Route("/api/admin/jobs/{job_id:str}/retry", _api_admin_job_retry, methods=["POST"]),
        Route("/api/admin/jobs/{job_id:str}/cancel", _api_admin_job_cancel, methods=["POST"]),
        Route("/api/admin/tidy", _api_admin_tidy, methods=["POST"]),
        Route("/api/admin/reviews", _api_admin_reviews),
        Route("/api/admin/reviews/{review_id:str}", _api_admin_review_detail),
        Route("/api/admin/reviews/{review_id:str}/approve", _api_admin_review_approve, methods=["POST"]),
        Route("/api/admin/reviews/{review_id:str}/reject", _api_admin_review_reject, methods=["POST"]),
        Route("/api/admin/entries/{name:str}", _api_admin_entry_detail, methods=["GET"]),
        Route("/api/admin/entries/{name:str}", _api_admin_entry_save, methods=["PUT"]),
        Route("/api/admin/explore", _api_admin_explore, methods=["POST"]),
        Route("/api/admin/quartz/status", _api_admin_quartz_status, methods=["GET"]),
        Route("/api/admin/quartz/build", _api_admin_quartz_build, methods=["POST"]),
        Mount(SSE_ENDPOINT, app=_make_router(sse), routes=False),
    ]
    QUARTZ_SITE_DIR.mkdir(parents=True, exist_ok=True)
    routes.append(
        Mount(
            "/quartz",
            app=StaticFiles(directory=str(QUARTZ_SITE_DIR), html=True, check_dir=False),
        )
    )
    return Starlette(
        middleware=[Middleware(SecurityHeadersMiddleware)],
        routes=routes,
    )


def main(argv: list[str] | None = None):
    import uvicorn

    starlette_app = create_starlette_app()
    print(f"Sediment MCP Server listening on http://{HOST}:{PORT}")
    print(f"Portal:        http://{HOST}:{PORT}/portal")
    print(f"Admin:         http://{HOST}:{PORT}/admin")
    if STARTUP_ADMIN_TOKEN:
        print(f"Startup token: {STARTUP_ADMIN_TOKEN}")
    print(f"Health:        http://{HOST}:{PORT}/healthz")
    print(f"SSE endpoint:  http://{HOST}:{PORT}{SSE_ENDPOINT}")
    print(f"POST endpoint: http://{HOST}:{PORT}{SSE_ENDPOINT}")
    print(f"In-process jobs: {'enabled' if RUN_JOBS_IN_PROCESS else 'disabled'}")
    uvicorn.run(starlette_app, host=HOST, port=PORT)


if __name__ == "__main__":
    raise SystemExit(main())
