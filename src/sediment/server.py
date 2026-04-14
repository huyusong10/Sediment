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
import mimetypes
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml
from mcp import types
from mcp.server import Server

from sediment.agent_runner import get_agent_runner
from sediment.auth import (
    active_users,
    auth_required as auth_model_required,
    auth_users_from_settings,
    create_config_user,
    disable_config_user,
    find_user_by_id,
    find_user_by_token,
    token_fingerprint,
)
from sediment.benchmark_materials import answer_from_materials
from sediment.control import (
    admin_overview_payload,
    apply_review_decision,
    build_tidy_request,
    enqueue_ingest_job,
    enqueue_tidy_job,
    normalize_tidy_scope,
    resolve_tidy_issue,
    review_detail_payload,
    scope_from_issue,
    submit_document_request,
    submit_text_request,
    system_status_payload,
)
from sediment.i18n import tr
from sediment.instances import user_state_root
from sediment.kb import resolve_kb_document_path
from sediment.llm_cli import build_cli_command, collect_output
from sediment.package_data import read_asset_text, read_skill_text
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
    search_kb_suggestions,
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
from sediment.settings import clear_settings_cache, load_settings
from sediment.skills.explore.scripts.kb_query import (
    inventory,
    prepare_explore_context,
    validate_answer,
)
from sediment.web_ui import admin_html, admin_login_html, portal_graph_html, portal_html

DEFAULT_CONTRACT = {
    "shortlist_limit": 8,
    "neighbor_depth": 2,
    "max_context_entries": 12,
    "max_snippets_per_entry": 2,
    "snippet_char_limit": 320,
    "cli_timeout_seconds": 150,
}
ALLOWED_TRIAGE_STATUSES = {"pending", "triaged", "rejected"}
UI_ASSET_MEDIA_TYPES = {
    "web-shell.js": "text/javascript; charset=utf-8",
    "portal.js": "text/javascript; charset=utf-8",
    "admin-login.js": "text/javascript; charset=utf-8",
    "admin.js": "text/javascript; charset=utf-8",
}


def refresh_runtime_state() -> None:
    global KB_PATH
    global INSTANCE_NAME
    global INSTANCE_ROOT
    global KNOWLEDGE_NAME
    global CONFIG_PATH
    global HOST
    global PORT
    global SSE_ENDPOINT
    global ADMIN_TOKEN
    global STARTUP_ADMIN_TOKEN
    global SESSION_SECRET
    global ADMIN_SESSION_COOKIE_NAME
    global ADMIN_SESSION_TTL_SECONDS
    global SECURE_COOKIES
    global TRUST_PROXY_HEADERS
    global TRUSTED_PROXY_CIDRS
    global SUBMISSION_RATE_LIMIT_COUNT
    global SUBMISSION_RATE_LIMIT_WINDOW_SECONDS
    global SUBMISSION_DEDUPE_WINDOW_SECONDS
    global MAX_TEXT_SUBMISSION_CHARS
    global MAX_UPLOAD_BYTES
    global JOB_MAX_ATTEMPTS
    global JOB_STALE_AFTER_SECONDS
    global RUN_JOBS_IN_PROCESS
    global _PROJECT_ROOT
    global QUARTZ_SITE_DIR
    global QUARTZ_RUNTIME_DIR
    global DEFAULT_LOCALE

    KB_PATH = runtime_kb_path()
    INSTANCE_NAME = runtime_instance_name()
    INSTANCE_ROOT = runtime_instance_root()
    KNOWLEDGE_NAME = runtime_knowledge_name()
    CONFIG_PATH = runtime_config_path()
    HOST = runtime_host()
    PORT = runtime_port()
    SSE_ENDPOINT = runtime_sse_endpoint()
    ADMIN_TOKEN = runtime_admin_token()
    STARTUP_ADMIN_TOKEN = ""
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


refresh_runtime_state()

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


def _settings() -> dict[str, Any]:
    return load_settings()


def _active_auth_users() -> list[dict[str, Any]]:
    return active_users(_settings())


def _synthetic_local_admin_user() -> dict[str, Any]:
    return {
        "id": "local-admin",
        "name": "Local Admin",
        "role": "owner",
        "disabled": False,
    }


def _session_secret_bytes() -> bytes | None:
    secret = SESSION_SECRET or ADMIN_TOKEN
    if not secret:
        return None
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _admin_auth_required() -> bool:
    return auth_model_required(_settings())


def _user_from_token(candidate: str) -> dict[str, Any] | None:
    return find_user_by_token(_settings(), candidate.strip())


def _extract_bearer_token(request) -> str:
    auth_header = str(request.headers.get("authorization", ""))
    if not auth_header.startswith("Bearer "):
        return ""
    return auth_header.removeprefix("Bearer ").strip()


def _session_user(request) -> dict[str, Any] | None:
    session_id = _extract_admin_session_id(request.cookies.get(ADMIN_SESSION_COOKIE_NAME))
    if session_id is None:
        return None
    session = _platform_store().get_active_admin_session(session_id)
    if session is None:
        return None
    user_id = str(session.get("user_id", "")).strip()
    user_name = str(session.get("user_name", "")).strip()
    user_role = str(session.get("user_role", "")).strip()
    if not user_id or not user_role:
        return None
    return {
        "id": user_id,
        "name": user_name or user_id,
        "role": user_role,
        "disabled": False,
        "token_fingerprint": session.get("token_fingerprint"),
    }


def _current_user(request) -> dict[str, Any] | None:
    bearer_token = _extract_bearer_token(request)
    if bearer_token:
        return _user_from_token(bearer_token)
    return _session_user(request)


def _current_optional_user(request) -> dict[str, Any] | None:
    return _current_user(request)


def _require_user(request) -> dict[str, Any] | None:
    if not _admin_auth_required():
        return _synthetic_local_admin_user()
    return _current_user(request)


def _user_role_allowed(user: dict[str, Any] | None, allowed_roles: tuple[str, ...]) -> bool:
    if user is None:
        return False
    if not allowed_roles:
        return True
    return str(user.get("role", "")).strip() in allowed_roles


def _build_admin_session_cookie(user: dict[str, Any]) -> str:
    secret = _session_secret_bytes()
    if secret is None:
        raise RuntimeError("admin session secret is unavailable")
    session = _platform_store().create_admin_session(
        expires_at=(
            datetime.now(timezone.utc) + timedelta(seconds=ADMIN_SESSION_TTL_SECONDS)
        )
        .replace(microsecond=0)
        .isoformat(),
        user_id=str(user.get("id", "")).strip() or None,
        user_name=str(user.get("name", "")).strip() or None,
        user_role=str(user.get("role", "")).strip() or None,
        token_fingerprint=str(user.get("token_fingerprint", "")).strip() or None,
    )
    payload = f"admin-session:{session['id']}"
    signature = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{session['id']}.{signature}"


def _extract_admin_session_id(cookie_value: str | None) -> str | None:
    if not cookie_value:
        return None
    secret = _session_secret_bytes()
    if secret is None:
        return None
    session_id, sep, signature = str(cookie_value).partition(".")
    if not sep or not re.fullmatch(r"[0-9a-f]{32}", session_id):
        return None
    payload = f"admin-session:{session_id}"
    expected = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return session_id


def _verify_admin_session_cookie(cookie_value: str | None) -> bool:
    session_id = _extract_admin_session_id(cookie_value)
    if session_id is None:
        return False
    return _platform_store().verify_admin_session(session_id)


def _is_admin_authorized(request) -> bool:
    return _require_user(request) is not None


def _set_admin_session_cookie(response, user: dict[str, Any]) -> str:
    cookie_value = _build_admin_session_cookie(user)
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=ADMIN_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        secure=SECURE_COOKIES,
        path="/",
    )
    session_id = _extract_admin_session_id(cookie_value)
    if session_id is None:
        raise RuntimeError("failed to build a valid admin session cookie")
    return session_id


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
                    "scope": {"type": "string"},
                    "reason": {"type": "string"},
                    "issue_type": {"type": "string"},
                    "actor_name": {"type": "string"},
                },
                "required": [],
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
    refresh_runtime_state()
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
            scope=arguments.get("scope"),
            reason=arguments.get("reason"),
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
    target: str = "",
    scope: str | None = None,
    reason: str | None = None,
    issue_type: str | None = None,
    actor_name: str = "mcp",
) -> str:
    target = str(target).strip()
    store = _platform_store()
    issue = None
    tidy_scope = normalize_tidy_scope(scope)
    tidy_reason = str(reason or "").strip()
    if target:
        issue = resolve_tidy_issue(
            kb_path=KB_PATH,
            target=target,
            issue_type=issue_type,
        )
        tidy_scope = scope_from_issue(issue)
        tidy_reason = tidy_reason or str(issue.get("summary", "")).strip() or f"tidy {issue['type']}"
    else:
        tidy_reason = tidy_reason or f"MCP KB tidy ({tidy_scope})"
    job = enqueue_tidy_job(
        store=store,
        kb_path=KB_PATH,
        scope=tidy_scope,
        reason=tidy_reason,
        issue=issue,
        actor_name=actor_name,
        max_attempts=JOB_MAX_ATTEMPTS,
    )
    if RUN_JOBS_IN_PROCESS:
        _agent_runner().submit(job["id"])
    return json.dumps(
        {"job": job, "issue": issue, "scope": tidy_scope, "reason": tidy_reason},
        ensure_ascii=False,
    )


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

    material_answer = None
    if _explore_fast_only_enabled():
        material_answer = answer_from_materials(question, project_root)
        if material_answer is not None:
            return material_answer

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

        if _explore_fast_only_enabled():
            local_answer = _build_local_explore_answer(
                question,
                inventory_data=inventory_data,
                context=context,
                mode_label="local-fastpath",
            )
            if local_answer is not None:
                return local_answer

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


def _explore_fast_only_enabled() -> bool:
    return os.environ.get("SEDIMENT_EXPLORE_FAST_ONLY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _build_local_explore_answer(
    question: str,
    *,
    inventory_data: dict[str, Any],
    context: dict[str, Any],
    mode_label: str,
) -> dict[str, Any] | None:
    snippets_by_name = context.get("candidate_snippets", {})
    shortlist = [
        item for item in context.get("initial_shortlist", [])
        if item.get("kind") == "formal"
    ]
    expanded = [
        item for item in context.get("expanded_candidates", [])
        if item.get("kind") == "formal"
    ]
    if not shortlist and not expanded:
        return None

    primary = shortlist[0] if shortlist else expanded[0]
    question_mode = _local_question_mode(question, context)
    focus = _local_question_focus(question, context)
    direct_shortlist = [
        item for item in shortlist if _is_direct_candidate_match(question, item)
    ]
    direct_shortlist.sort(
        key=lambda item: _direct_candidate_match_index(question, item),
        reverse=True,
    )
    if len(direct_shortlist) >= 2 and _question_needs_multiple_direct_matches(question, focus):
        selected_candidates = direct_shortlist[:2]
    elif direct_shortlist:
        selected_candidates = direct_shortlist[:1]
    else:
        selected_candidates = _select_local_answer_candidates(
            question_mode=question_mode,
            shortlist=shortlist,
            expanded=expanded,
        )
    selected_candidates.extend(
        _supplement_local_candidates(
            question=question,
            inventory_data=inventory_data,
            snippets_by_name=snippets_by_name,
            selected_candidates=selected_candidates,
            question_mode=question_mode,
            focus=focus,
        )
    )
    selected_names: list[str] = []
    evidence_parts: list[str] = []

    for item in selected_candidates:
        name = str(item.get("name", "")).strip()
        if not name or name in selected_names:
            continue
        snippet_payload = snippets_by_name.get(name, {})
        snippet_records = snippet_payload.get("snippets", [])
        snippet_texts = _preferred_local_snippets(
            question=question,
            candidate=item,
            snippet_records=snippet_records,
            fallback_summary=str(item.get("summary", "")).strip(),
            question_mode=question_mode,
            focus=focus,
        )
        if not snippet_texts:
            continue
        selected_names.append(name)
        if question_mode == "definition":
            evidence_parts.extend(snippet_texts[:1])
            break
        if direct_shortlist and item is selected_candidates[0]:
            evidence_parts.extend(snippet_texts[:2])
        else:
            evidence_parts.extend(snippet_texts[:1])
        if len(selected_names) >= 3 or len(evidence_parts) >= 4:
            break

    if not evidence_parts:
        return None

    if question_mode == "definition":
        answer = evidence_parts[0]
    else:
        answer = " ".join(evidence_parts[:3])

    exploration_summary = {
        "entries_scanned": len(inventory_data["entries"]),
        "entries_read": len(selected_names),
        "links_followed": max(
            0,
            len(context.get("expanded_candidates", [])) - len(context.get("initial_shortlist", [])),
        ),
        "mode": mode_label,
    }
    confidence = "high" if _is_direct_candidate_match(question, primary) else "medium"
    payload = {
        "answer": answer.strip(),
        "sources": selected_names,
        "confidence": confidence,
        "exploration_summary": exploration_summary,
        "gaps": [],
        "contradictions": [],
    }
    validation = validate_answer(payload, inventory_data=inventory_data)
    if validation["valid"]:
        return validation["normalized"]
    return None


def _is_direct_candidate_match(question: str, candidate: dict[str, Any]) -> bool:
    question_lower = question.lower()
    candidate_name = str(candidate.get("name", "")).strip().lower()
    if candidate_name and candidate_name in question_lower:
        return True
    aliases = candidate.get("matched_terms", []) or []
    return any(str(alias).strip().lower() in question_lower for alias in aliases)


def _local_question_focus(question: str, context: dict[str, Any]) -> str:
    if any(marker in question for marker in ("关系", "关联", "联系", "区别", "差异", "对比")):
        return "comparison"
    focus = str(context.get("question_analysis", {}).get("focus", "open"))
    if focus != "open":
        return focus
    if any(marker in question for marker in ("为什么", "原因", "为何")):
        return "why"
    if any(marker in question for marker in ("如何", "怎么", "怎样", "步骤", "准备", "协作", "配合", "需要")):
        return "guidance"
    if any(marker in question for marker in ("风险", "后果", "误区", "避免")):
        return "risk"
    return focus


def _local_question_mode(question: str, context: dict[str, Any]) -> str:
    if any(marker in question for marker in ("关系", "关联", "联系", "区别", "差异", "对比")):
        return "comparison"
    if any(
        marker in question
        for marker in (
            "什么是",
            "是什么",
            "是什么意思",
            "指什么",
            "是做什么的",
            "作用是什么",
            "负责什么",
            "内容是什么",
            "衡量什么",
        )
    ):
        return "definition"
    if any(marker in question for marker in ("为什么", "原因", "为何")):
        return "guidance"
    if any(marker in question for marker in ("如何", "怎么", "怎样", "步骤", "准备", "协作", "配合", "需要")):
        return "guidance"
    if any(marker in question for marker in ("风险", "后果", "误区", "避免")):
        return "risk"
    return str(context.get("question_analysis", {}).get("mode", "open"))


def _preferred_local_snippets(
    *,
    question: str,
    candidate: dict[str, Any],
    snippet_records: list[dict[str, Any]],
    fallback_summary: str,
    question_mode: str,
    focus: str,
) -> list[str]:
    if question_mode == "definition":
        for record in snippet_records:
            if str(record.get("section", "")) == "Summary":
                text = _strip_wikilinks(str(record.get("text", "")).strip())
                if text:
                    return [_first_sentence(text)]

    direct_match = _is_direct_candidate_match(question, candidate)
    section_order = _local_section_priority(
        entry_type=str(candidate.get("entry_type", "")),
        question_mode=question_mode,
        focus=focus,
        direct_match=direct_match,
    )
    snippets_by_section = {
        str(record.get("section", "")): _strip_wikilinks(str(record.get("text", "")).strip())
        for record in snippet_records
        if str(record.get("text", "")).strip()
    }

    selected: list[str] = []
    for section in section_order:
        text = snippets_by_section.get(section)
        if text and text not in selected:
            selected.append(text)

    for record in snippet_records:
        text = _strip_wikilinks(str(record.get("text", "")).strip())
        if text and text not in selected:
            selected.append(text)

    if not selected and fallback_summary:
        selected.append(_strip_wikilinks(fallback_summary))

    if direct_match and question_mode != "comparison":
        return selected[:2]
    return selected[:1]


def _local_section_priority(
    *,
    entry_type: str,
    question_mode: str,
    focus: str,
    direct_match: bool,
) -> list[str]:
    if question_mode == "definition":
        return ["Summary", "Scope", "Trigger", "Why", "Risks", "Related"]
    if focus == "comparison":
        return ["Summary", "Scope", "Why", "Trigger", "Risks", "Related"]
    if focus == "why":
        return ["Why", "Scope", "Summary", "Trigger", "Risks", "Related"]
    if focus == "risk":
        return ["Risks", "Scope", "Summary", "Why", "Trigger", "Related"]
    if focus == "guidance":
        if entry_type == "lesson":
            return ["Trigger", "Why", "Summary", "Risks", "Scope", "Related"]
        return ["Scope", "Summary", "Trigger", "Why", "Risks", "Related"]
    if direct_match:
        return ["Scope", "Summary", "Why", "Trigger", "Risks", "Related"]
    return ["Summary", "Scope", "Why", "Trigger", "Risks", "Related"]


def _supplement_local_candidates(
    *,
    question: str,
    inventory_data: dict[str, Any],
    snippets_by_name: dict[str, dict[str, Any]],
    selected_candidates: list[dict[str, Any]],
    question_mode: str,
    focus: str,
) -> list[dict[str, Any]]:
    if not selected_candidates:
        return []
    if not _question_benefits_from_supporting_candidate(question, focus):
        return []

    primary = selected_candidates[0]
    primary_name = str(primary.get("name", "")).strip()
    if not primary_name:
        return []

    primary_snippets = _preferred_local_snippets(
        question=question,
        candidate=primary,
        snippet_records=snippets_by_name.get(primary_name, {}).get("snippets", []),
        fallback_summary=str(primary.get("summary", "")).strip(),
        question_mode=question_mode,
        focus=focus,
    )
    if not primary_snippets:
        return []

    selected_names = {
        str(item.get("name", "")).strip()
        for item in selected_candidates
        if str(item.get("name", "")).strip()
    }
    primary_text = " ".join(primary_snippets)
    docs = inventory_data.get("docs", {})
    supplemented: list[tuple[int, dict[str, Any]]] = []

    for name, doc in docs.items():
        if name in selected_names or doc.get("kind") != "formal" or name not in primary_text:
            continue
        summary = str(doc.get("summary", "")).strip()
        rank = 0
        if any(marker in summary for marker in ("角色", "负责", "主持", "权限", "团队")):
            rank += 2
        if any(marker in question for marker in ("谁", "权限", "角色")):
            rank += 1
        supplemented.append(
            (
                rank,
                {
                    "name": name,
                    "kind": doc.get("kind", "formal"),
                    "entry_type": doc.get("entry_type", ""),
                    "status": doc.get("status", ""),
                    "summary": summary,
                    "matched_terms": [],
                },
            )
        )

    supplemented.sort(key=lambda item: (-item[0], -len(str(item[1].get("name", "")))))
    return [item for _, item in supplemented[:1]]


def _question_needs_multiple_direct_matches(question: str, focus: str) -> bool:
    if focus == "comparison":
        return True
    if focus in {"why", "guidance"}:
        return True
    if any(marker in question for marker in ("和", "与", "及", "之间")) and focus in {
        "guidance",
        "open",
        "why",
    }:
        return True
    if any(marker in question for marker in ("过程", "过程中", "结合", "推断")):
        return True
    return False


def _question_benefits_from_supporting_candidate(question: str, focus: str) -> bool:
    if focus in {"why", "guidance", "comparison"}:
        return True
    return any(marker in question for marker in ("谁", "权限", "角色", "负责", "主持"))


def _direct_candidate_match_index(question: str, candidate: dict[str, Any]) -> int:
    question_lower = question.lower()
    positions = []
    candidate_name = str(candidate.get("name", "")).strip().lower()
    if candidate_name:
        index = question_lower.find(candidate_name)
        if index >= 0:
            positions.append(index)
    for alias in candidate.get("matched_terms", []) or []:
        alias_lower = str(alias).strip().lower()
        if not alias_lower:
            continue
        index = question_lower.find(alias_lower)
        if index >= 0:
            positions.append(index)
    return max(positions) if positions else -1


def _first_sentence(text: str) -> str:
    first = re.split(r"[。！？!?；;\n]", text, maxsplit=1)[0].strip()
    return first or text.strip()


def _strip_wikilinks(text: str) -> str:
    return re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)


def _select_local_answer_candidates(
    *,
    question_mode: str,
    shortlist: list[dict[str, Any]],
    expanded: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if question_mode == "definition":
        return shortlist[:1] or expanded[:1]

    if shortlist:
        primary_score = float(shortlist[0].get("score", 0) or 0)
        selected = [
            item
            for item in shortlist
            if float(item.get("score", 0) or 0) >= primary_score * 0.45
        ]
        if not selected:
            selected = shortlist[:3]
        if len(selected) < 2:
            selected_names = {str(item.get("name", "")) for item in selected}
            for item in expanded:
                name = str(item.get("name", ""))
                if not name or name in selected_names:
                    continue
                selected.append(item)
                selected_names.add(name)
                if len(selected) >= 3:
                    break
        return selected[:3]

    return expanded[:3]


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


def _text_response(text: str, *, media_type: str, status: int = 200):
    from starlette.responses import Response

    return Response(text, status_code=status, media_type=media_type)


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


def _forbidden_html(*, locale: str, message: str):
    title = "禁止访问" if locale == "zh" else "Forbidden"
    description = message or (
        "当前登录角色无权访问这个管理页面。"
        if locale == "zh"
        else "Your current role cannot access this admin page."
    )
    return _html_response(
        (
            "<!doctype html><html><head>"
            f"<meta charset='utf-8'><title>{title}</title>"
            "</head><body>"
            f"<h1>{title}</h1><p>{description}</p>"
            "</body></html>"
        ),
        status=403,
    )


def _config_user_payload(user: dict[str, Any], *, include_token: bool = False) -> dict[str, Any]:
    payload = {
        "id": str(user.get("id", "")).strip(),
        "name": str(user.get("name", "")).strip(),
        "role": str(user.get("role", "")).strip(),
        "created_at": str(user.get("created_at", "")).strip(),
        "disabled": bool(user.get("disabled", False)),
        "token_fingerprint": token_fingerprint(str(user.get("token", "")).strip()),
    }
    if include_token:
        payload["token"] = str(user.get("token", "")).strip()
    return payload


def _configured_users() -> list[dict[str, Any]]:
    return auth_users_from_settings(_settings())


def _reload_runtime_settings() -> None:
    clear_settings_cache()
    refresh_runtime_state()


async def _portal_page(request):
    locale = _request_locale(request)
    return _redirect(_path_with_locale("/", locale))


async def _portal_home_page(request):
    return _html_response(
        portal_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=_request_locale(request),
            page="home",
            initial_query=str(request.query_params.get("q", "")).strip(),
            current_user=_current_optional_user(request),
        )
    )


async def _ui_asset(request):
    asset_name = request.path_params["asset_name"]
    media_type = UI_ASSET_MEDIA_TYPES.get(asset_name)
    if media_type is None:
        return _text_response("asset not found", media_type="text/plain; charset=utf-8", status=404)
    try:
        text = read_asset_text(asset_name)
    except FileNotFoundError:
        return _text_response("asset not found", media_type="text/plain; charset=utf-8", status=404)
    return _text_response(text, media_type=media_type)


async def _portal_graph_page(request):
    locale = _request_locale(request)
    if _quartz_site_available():
        return _redirect(_path_with_locale("/quartz/", locale))
    return _html_response(
        portal_graph_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=locale,
            quartz=quartz_status(
                runtime_dir=QUARTZ_RUNTIME_DIR,
                site_dir=QUARTZ_SITE_DIR,
            ),
            admin_kb_path=_path_with_locale("/admin/system", locale),
        )
    )


async def _admin_page(request):
    locale = _request_locale(request)
    return _redirect(_path_with_locale("/admin/overview", locale))


async def _portal_search_page(request):
    locale = _request_locale(request)
    return _html_response(
        portal_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=locale,
            page="search",
            initial_query=str(request.query_params.get("q", "")).strip(),
            current_user=_current_optional_user(request),
        )
    )


async def _portal_entry_page(request):
    locale = _request_locale(request)
    return _html_response(
        portal_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=locale,
            page="entry",
            entry_name=request.path_params["name"],
            current_user=_current_optional_user(request),
        )
    )


async def _portal_submit_page(request):
    locale = _request_locale(request)
    return _html_response(
        portal_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=locale,
            page="submit",
            current_user=_current_optional_user(request),
        )
    )


async def _admin_section_page(
    request,
    *,
    section: str,
    allowed_roles: tuple[str, ...] = ("owner", "committer"),
):
    locale = _request_locale(request)
    user = _require_user(request)
    if user is None:
        return _html_response(
            admin_login_html(
                knowledge_name=KNOWLEDGE_NAME,
                instance_name=INSTANCE_NAME,
                locale=locale,
                next_path=_path_with_locale(request.url.path, locale),
            ),
            status=200,
        )
    if not _user_role_allowed(user, allowed_roles):
        return _forbidden_html(
            locale=locale,
            message=(
                "只有 owner 可以访问这个区域。"
                if locale == "zh"
                else "Only owners can access this section."
            ),
        )
    return _html_response(
        admin_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=locale,
            section=section,
            quartz=quartz_status(runtime_dir=QUARTZ_RUNTIME_DIR, site_dir=QUARTZ_SITE_DIR),
            current_user=_user_payload(user),
        )
    )


async def _admin_overview_page(request):
    return await _admin_section_page(request, section="overview")


async def _admin_kb_page(request):
    return await _admin_section_page(request, section="kb")


async def _admin_reviews_page(request):
    return await _admin_section_page(request, section="reviews")


async def _admin_users_page(request):
    return await _admin_section_page(request, section="users", allowed_roles=("owner",))


async def _admin_system_page(request):
    return await _admin_section_page(request, section="system", allowed_roles=("owner",))


async def _root_page(request):
    return await _portal_home_page(request)


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


async def _api_portal_search_suggest(request):
    query = request.query_params.get("q", "")
    return _json_response(
        {
            "query": query,
            "suggestions": search_kb_suggestions(KB_PATH, query),
        }
    )


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
    user = _current_optional_user(request)
    submitter_name = str(body.get("submitter_name", "")).strip() or str(
        (user or {}).get("name", "")
    ).strip()
    try:
        record = submit_text_request(
            store=_platform_store(),
            kb_path=KB_PATH,
            title=str(body.get("title", "")),
            content=str(body.get("content", "")),
            submitter_name=submitter_name,
            submitter_ip=detect_submitter_ip(
                dict(request.headers),
                request.client.host if request.client else None,
                trust_proxy_headers=TRUST_PROXY_HEADERS,
                trusted_proxy_cidrs=TRUSTED_PROXY_CIDRS,
            ),
            submission_type=str(body.get("submission_type", "text")),
            submitter_user_id=str((user or {}).get("id", "")).strip() or None,
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
    user = _current_optional_user(request)
    submitter_name = str(body.get("submitter_name", "")).strip() or str(
        (user or {}).get("name", "")
    ).strip()
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
            submitter_name=submitter_name,
            submitter_ip=detect_submitter_ip(
                dict(request.headers),
                request.client.host if request.client else None,
                trust_proxy_headers=TRUST_PROXY_HEADERS,
                trusted_proxy_cidrs=TRUSTED_PROXY_CIDRS,
            ),
            submitter_user_id=str((user or {}).get("id", "")).strip() or None,
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


def _user_payload(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": str(user.get("id", "")).strip(),
        "name": str(user.get("name", "")).strip(),
        "role": str(user.get("role", "")).strip(),
        "token_fingerprint": str(user.get("token_fingerprint", "")).strip(),
    }


def _actor_from_request(request) -> dict[str, Any]:
    user = _require_user(request)
    return user or _synthetic_local_admin_user()


async def _admin_guard(request, *, allowed_roles: tuple[str, ...] = ("owner", "committer")):
    user = _require_user(request)
    if user is None:
        return _json_response(
            {
                "error": "admin authentication is required",
                "auth_required": True,
                "login_path": "/admin",
            },
            status=401,
        )
    if not _user_role_allowed(user, allowed_roles):
        return _json_response(
            {
                "error": "forbidden",
                "required_roles": list(allowed_roles),
                "user": _user_payload(user),
            },
            status=403,
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
    user = _require_user(request) if _is_admin_authorized(request) else None
    return _json_response(
        {
            "authenticated": user is not None,
            "auth_required": _admin_auth_required(),
            "cookie_name": ADMIN_SESSION_COOKIE_NAME,
            "session_ttl_seconds": ADMIN_SESSION_TTL_SECONDS,
            "user": _user_payload(user),
        }
    )


async def _api_admin_session_create(request):
    body = await _request_json_or_empty(request)
    token = str(body.get("token", ""))
    user = _user_from_token(token) if _admin_auth_required() else _synthetic_local_admin_user()
    if _admin_auth_required() and user is None:
        return _json_response({"error": "invalid admin token"}, status=401)
    response = _json_response(
        {
            "authenticated": True,
            "auth_required": _admin_auth_required(),
            "session_ttl_seconds": ADMIN_SESSION_TTL_SECONDS,
            "user": _user_payload(user),
        }
    )
    session_id: str | None = None
    if _admin_auth_required() and user is not None:
        session_id = _set_admin_session_cookie(response, user)
    _platform_store().add_audit_log(
        actor_name=str((user or {}).get("name", "admin-session")),
        actor_id=str((user or {}).get("id", "")).strip() or None,
        actor_role=str((user or {}).get("role", "owner")),
        action="admin.session.create",
        target_type="session",
        target_id=session_id or (request.client.host if request.client else "unknown"),
        details={
            "auth_required": _admin_auth_required(),
            "session_id": session_id,
            "user": _user_payload(user),
        },
    )
    return response


async def _api_admin_session_delete(request):
    user = _current_user(request)
    session_id = _extract_admin_session_id(
        request.cookies.get(ADMIN_SESSION_COOKIE_NAME)
    )
    if session_id is not None:
        _platform_store().revoke_admin_session(session_id)
    response = _json_response(
        {"authenticated": False, "auth_required": _admin_auth_required()}
    )
    _clear_admin_session_cookie(response)
    _platform_store().add_audit_log(
        actor_name=str((user or {}).get("name", "admin-session")),
        actor_id=str((user or {}).get("id", "")).strip() or None,
        actor_role=str((user or {}).get("role", "owner")),
        action="admin.session.delete",
        target_type="session",
        target_id=session_id or (request.client.host if request.client else "unknown"),
        details={
            "auth_required": _admin_auth_required(),
            "session_id": session_id,
            "user": _user_payload(user),
        },
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
    actor = _actor_from_request(request)
    store = _platform_store()
    submission_id = request.path_params["submission_id"]
    body = await request.json()
    status = str(body.get("status", "triaged")).strip()
    if status not in ALLOWED_TRIAGE_STATUSES:
        return _json_response(
            {"error": f"unsupported submission status: {status}"},
            status=400,
        )
    submission = store.update_submission(submission_id, status=status, notes=body.get("notes"))
    if submission is None:
        return _json_response({"error": "submission not found"}, status=404)
    store.add_audit_log(
        actor_name=str(actor.get("name", "")),
        actor_id=str(actor.get("id", "")) or None,
        actor_role=str(actor.get("role", "")),
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
    actor = _actor_from_request(request)
    store = _platform_store()
    submission_id = request.path_params["submission_id"]
    try:
        job = enqueue_ingest_job(
            store=store,
            submission_id=submission_id,
            actor_name=str(actor.get("name", "")),
            actor_id=str(actor.get("id", "")) or None,
            actor_role=str(actor.get("role", "")),
            max_attempts=JOB_MAX_ATTEMPTS,
        )
    except FileNotFoundError:
        return _json_response({"error": "submission not found"}, status=404)
    except RuntimeError as exc:
        return _json_response({"error": str(exc)}, status=409)
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
    actor = _actor_from_request(request)
    store = _platform_store()
    try:
        job = store.retry_job(request.path_params["job_id"])
    except ValueError as exc:
        return _json_response({"error": str(exc)}, status=400)
    if job is None:
        return _json_response({"error": "job not found"}, status=404)
    if job.get("source_submission_id"):
        store.update_submission(job["source_submission_id"], status="triaged")
    store.add_audit_log(
        actor_name=str(actor.get("name", "")),
        actor_id=str(actor.get("id", "")) or None,
        actor_role=str(actor.get("role", "")),
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
    actor = _actor_from_request(request)
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
        actor_name=str(actor.get("name", "")),
        actor_id=str(actor.get("id", "")) or None,
        actor_role=str(actor.get("role", "")),
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
    actor = _actor_from_request(request)
    store = _platform_store()
    body = await _request_json_or_empty(request)
    issue = body.get("issue") if isinstance(body.get("issue"), dict) else None
    job = enqueue_tidy_job(
        store=store,
        kb_path=KB_PATH,
        scope=normalize_tidy_scope(body.get("scope")),
        reason=str(body.get("reason", "")).strip(),
        issue=issue,
        actor_name=str(actor.get("name", "")),
        actor_id=str(actor.get("id", "")) or None,
        actor_role=str(actor.get("role", "")),
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
    actor = _actor_from_request(request)
    body = await request.json()
    try:
        payload = apply_review_decision(
            store=_platform_store(),
            kb_path=KB_PATH,
            review_id=request.path_params["review_id"],
            decision=str(body.get("decision", "approve")),
            reviewer_name=str(actor.get("name", "")),
            reviewer_id=str(actor.get("id", "")) or None,
            reviewer_role=str(actor.get("role", "")),
            comment=str(body.get("comment", "")),
        )
    except FileNotFoundError as exc:
        return _json_response({"error": str(exc)}, status=404)
    except (RuntimeError, ValueError) as exc:
        return _json_response({"error": str(exc)}, status=400)
    return _json_response(payload)


async def _api_admin_review_reject(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    actor = _actor_from_request(request)
    body = await request.json()
    try:
        payload = apply_review_decision(
            store=_platform_store(),
            kb_path=KB_PATH,
            review_id=request.path_params["review_id"],
            decision="reject",
            reviewer_name=str(actor.get("name", "")),
            reviewer_id=str(actor.get("id", "")) or None,
            reviewer_role=str(actor.get("role", "")),
            comment=str(body.get("comment", "")),
        )
    except FileNotFoundError as exc:
        return _json_response({"error": str(exc)}, status=404)
    except (RuntimeError, ValueError) as exc:
        return _json_response({"error": str(exc)}, status=400)
    return _json_response(payload)


async def _api_admin_system_status(request):
    guard = await _admin_guard(request, allowed_roles=("owner",))
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
    actor = _actor_from_request(request)
    body = await request.json()
    store = _platform_store()
    try:
        payload = save_entry(
            KB_PATH,
            name=request.path_params["name"],
            content=str(body.get("content", "")),
            expected_hash=body.get("expected_hash"),
            actor_name=str(actor.get("name", "")),
            actor_id=str(actor.get("id", "")) or None,
            actor_role=str(actor.get("role", "")),
            store=store,
        )
    except FileNotFoundError:
        return _json_response({"error": "entry not found"}, status=404)
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
    guard = await _admin_guard(request, allowed_roles=("owner",))
    if guard:
        return guard
    return _json_response(quartz_status(runtime_dir=QUARTZ_RUNTIME_DIR, site_dir=QUARTZ_SITE_DIR))


async def _api_admin_quartz_build(request):
    guard = await _admin_guard(request, allowed_roles=("owner",))
    if guard:
        return guard
    actor = _actor_from_request(request)
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
        actor_name=str(actor.get("name", "")),
        actor_id=str(actor.get("id", "")) or None,
        actor_role=str(actor.get("role", "")),
        action="quartz.build",
        target_type="quartz_site",
        target_id=str(QUARTZ_SITE_DIR),
        details={"runtime_path": str(QUARTZ_RUNTIME_DIR)},
    )
    return _json_response(payload, status=202)


async def _api_admin_users_list(request):
    guard = await _admin_guard(request, allowed_roles=("owner",))
    if guard:
        return guard
    return _json_response({"users": [_config_user_payload(user) for user in _configured_users()]})


async def _api_admin_users_create(request):
    guard = await _admin_guard(request, allowed_roles=("owner",))
    if guard:
        return guard
    actor = _actor_from_request(request)
    body = await _request_json_or_empty(request)
    name = str(body.get("name", "")).strip()
    role = str(body.get("role", "committer")).strip() or "committer"
    if not name:
        return _json_response({"error": "name must not be empty"}, status=400)
    try:
        _payload, user = create_config_user(
            CONFIG_PATH,
            name=name,
            role=role,
            created_at=utc_now(),
        )
    except ValueError as exc:
        return _json_response({"error": str(exc)}, status=400)
    _reload_runtime_settings()
    _platform_store().add_audit_log(
        actor_name=str(actor.get("name", "")),
        actor_id=str(actor.get("id", "")) or None,
        actor_role=str(actor.get("role", "")),
        action="user.create",
        target_type="user",
        target_id=str(user.get("id", "")).strip(),
        details={"role": str(user.get("role", "")).strip()},
    )
    return _json_response(
        {
            "user": _config_user_payload(user),
            "token": str(user.get("token", "")).strip(),
        },
        status=201,
    )


async def _api_admin_user_token(request):
    guard = await _admin_guard(request, allowed_roles=("owner",))
    if guard:
        return guard
    user = find_user_by_id(_settings(), request.path_params["user_id"])
    if user is None:
        return _json_response({"error": "user not found"}, status=404)
    return _json_response(
        {
            "user": _config_user_payload(user),
            "token": str(user.get("token", "")).strip(),
        }
    )


async def _api_admin_user_disable(request):
    guard = await _admin_guard(request, allowed_roles=("owner",))
    if guard:
        return guard
    actor = _actor_from_request(request)
    user_id = request.path_params["user_id"]
    target_user = find_user_by_id(_settings(), user_id)
    if target_user is None:
        return _json_response({"error": "user not found"}, status=404)
    if str(target_user.get("id", "")).strip() == str(actor.get("id", "")).strip():
        return _json_response({"error": "cannot disable the current user"}, status=400)
    active_owner_count = sum(
        1
        for item in _configured_users()
        if item.get("role") == "owner" and not item.get("disabled")
    )
    if (
        target_user.get("role") == "owner"
        and not target_user.get("disabled")
        and active_owner_count <= 1
    ):
        return _json_response({"error": "cannot disable the last active owner"}, status=400)
    _payload, disabled_user = disable_config_user(CONFIG_PATH, user_id)
    _reload_runtime_settings()
    _platform_store().add_audit_log(
        actor_name=str(actor.get("name", "")),
        actor_id=str(actor.get("id", "")) or None,
        actor_role=str(actor.get("role", "")),
        action="user.disable",
        target_type="user",
        target_id=str(disabled_user.get("id", "")).strip(),
        details={"role": str(disabled_user.get("role", "")).strip()},
    )
    return _json_response({"user": _config_user_payload(disabled_user)})


class QuartzStaticApp:
    def __init__(self, site_dir: str | Path):
        self.site_dir = Path(site_dir).resolve()

    def _safe_candidate(self, relative_path: str) -> Path | None:
        candidate = (self.site_dir / relative_path).resolve()
        if candidate == self.site_dir:
            return None
        if self.site_dir not in candidate.parents:
            return None
        return candidate

    def _candidate_files(self, request_path: str) -> list[tuple[Path, int]]:
        raw_path = unquote(str(request_path or "/"))
        cleaned = raw_path.lstrip("/").rstrip("/")
        candidates: list[tuple[Path, int]] = []
        if not cleaned:
            index_path = self._safe_candidate("index.html")
            if index_path is not None:
                candidates.append((index_path, 200))
        else:
            for relative_path in (cleaned, f"{cleaned}.html", f"{cleaned}/index.html"):
                candidate = self._safe_candidate(relative_path)
                if candidate is not None:
                    candidates.append((candidate, 200))
        not_found = self._safe_candidate("404.html")
        if not_found is not None:
            candidates.append((not_found, 404))
        return candidates

    async def __call__(self, scope, receive, send):
        from starlette.requests import Request
        from starlette.responses import FileResponse, PlainTextResponse

        if scope["type"] != "http":
            await PlainTextResponse("unsupported scope", status_code=500)(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        path = str(scope.get("path", "/") or "/")
        if path == "/quartz":
            path = "/"
        elif path.startswith("/quartz/"):
            path = path.removeprefix("/quartz")
        if request.method not in {"GET", "HEAD"}:
            await PlainTextResponse("method not allowed", status_code=405)(scope, receive, send)
            return
        if not _quartz_site_available():
            if path in {"", "/"}:
                response = _html_response(
                    portal_graph_html(
                        knowledge_name=KNOWLEDGE_NAME,
                        instance_name=INSTANCE_NAME,
                        locale=_request_locale(request),
                        quartz=quartz_status(
                            runtime_dir=QUARTZ_RUNTIME_DIR,
                            site_dir=QUARTZ_SITE_DIR,
                        ),
                        admin_kb_path=_path_with_locale("/admin/system", _request_locale(request)),
                    )
                )
                await response(scope, receive, send)
                return
            await PlainTextResponse("Quartz site not built", status_code=404)(scope, receive, send)
            return
        for candidate, status in self._candidate_files(path):
            if candidate.is_file():
                await FileResponse(
                    str(candidate),
                    status_code=status,
                    media_type=mimetypes.guess_type(str(candidate))[0],
                )(scope, receive, send)
                return
        await PlainTextResponse("not found", status_code=404)(scope, receive, send)


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
                        "img-src 'self' data: blob: https:; "
                        "style-src 'self' 'unsafe-inline' https:; "
                        "script-src 'self' 'unsafe-inline' https: blob:; "
                        "connect-src 'self'; "
                        "worker-src 'self' blob:; "
                        "font-src 'self' data: https:; "
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

    _platform_store()
    sse = SseServerTransport("")
    routes = [
        Route("/", _root_page),
        Route("/healthz", _healthz),
        Route("/ui-assets/{asset_name:str}", _ui_asset),
        Route("/portal", _portal_page),
        Route("/search", _portal_search_page),
        Route("/entries/{name:str}", _portal_entry_page),
        Route("/submit", _portal_submit_page),
        Route("/portal/graph-view", _portal_graph_page),
        Route("/admin", _admin_page),
        Route("/admin/overview", _admin_overview_page),
        Route("/admin/kb", _admin_kb_page),
        Route("/admin/reviews", _admin_reviews_page),
        Route("/admin/users", _admin_users_page),
        Route("/admin/system", _admin_system_page),
        Route("/api/admin/session", _api_admin_session_status, methods=["GET"]),
        Route("/api/admin/session", _api_admin_session_create, methods=["POST"]),
        Route("/api/admin/session", _api_admin_session_delete, methods=["DELETE"]),
        Route("/api/portal/home", _api_portal_home),
        Route("/api/portal/search", _api_portal_search),
        Route("/api/portal/search/suggest", _api_portal_search_suggest),
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
        Route("/api/admin/users", _api_admin_users_list, methods=["GET"]),
        Route("/api/admin/users", _api_admin_users_create, methods=["POST"]),
        Route("/api/admin/users/{user_id:str}/token", _api_admin_user_token, methods=["GET"]),
        Route("/api/admin/users/{user_id:str}/disable", _api_admin_user_disable, methods=["POST"]),
        Route("/api/admin/quartz/status", _api_admin_quartz_status, methods=["GET"]),
        Route("/api/admin/quartz/build", _api_admin_quartz_build, methods=["POST"]),
        Mount(SSE_ENDPOINT, app=_make_router(sse), routes=False),
    ]
    routes.append(
        Mount(
            "/quartz",
            app=QuartzStaticApp(QUARTZ_SITE_DIR),
        )
    )
    return Starlette(
        middleware=[Middleware(SecurityHeadersMiddleware)],
        routes=routes,
    )


def main(argv: list[str] | None = None):
    import uvicorn

    refresh_runtime_state()
    starlette_app = create_starlette_app()
    print(f"Sediment MCP Server listening on http://{HOST}:{PORT}")
    print(f"Portal:        http://{HOST}:{PORT}/")
    print(f"Search:        http://{HOST}:{PORT}/search")
    print(f"Submit:        http://{HOST}:{PORT}/submit")
    print(f"Quartz:        http://{HOST}:{PORT}/quartz/")
    print(f"Admin:         http://{HOST}:{PORT}/admin/overview")
    print(f"Health:        http://{HOST}:{PORT}/healthz")
    print(f"SSE endpoint:  http://{HOST}:{PORT}{SSE_ENDPOINT}")
    print(f"POST endpoint: http://{HOST}:{PORT}{SSE_ENDPOINT}")
    print(f"In-process jobs: {'enabled' if RUN_JOBS_IN_PROCESS else 'disabled'}")
    uvicorn.run(starlette_app, host=HOST, port=PORT)


if __name__ == "__main__":
    raise SystemExit(main())
