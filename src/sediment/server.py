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
import asyncio
import hashlib
import hmac
import json
import mimetypes
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
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
from sediment.diagnostics import DiagnosticLogger, bind_log_context
from sediment.i18n import tr
from sediment.instances import user_state_root
from sediment.kb import resolve_kb_document_path
from sediment.llm_cli import AgentCliInvocation, build_cli_command, collect_output
from sediment.package_data import read_asset_text, read_skill_text
from sediment.platform_services import (
    build_health_issue_queue,
    detect_submitter_ip,
    get_entry_detail,
    get_health_payload,
    get_portal_home,
    graph_payload,
    kb_document_browser_payload,
    kb_file_management_payload,
    list_reviews_with_jobs,
    save_entry,
    search_kb,
    search_kb_file_suggestions,
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
    public_base_url as runtime_public_base_url,
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
from sediment.settings import clear_settings_cache, load_settings, load_settings_for_path
from sediment.skills.explore.scripts.kb_query import (
    inventory,
    prepare_explore_context,
    validate_answer,
)
from sediment.web_ui import admin_html, admin_login_html, portal_graph_html, portal_html

SERVER_LOGGER = DiagnosticLogger("server")
HTTP_LOGGER = DiagnosticLogger("http")
EXPLORE_LOGGER = DiagnosticLogger("explore")

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
    global PUBLIC_BASE_URL
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
    PUBLIC_BASE_URL = runtime_public_base_url()
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
    return "en"


def _path_with_locale(path: str, locale: str) -> str:
    joiner = "&" if "?" in path else "?"
    return f"{path}{joiner}lang={locale}"


def _first_forwarded_value(raw: str) -> str:
    return str(raw or "").split(",", 1)[0].strip()


def _absolute_app_url(base_url: str, path: str) -> str:
    return f"{str(base_url or '').rstrip('/')}/{str(path or '/').lstrip('/')}"


def _request_origin(request) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/")
    if TRUST_PROXY_HEADERS:
        proto = _first_forwarded_value(request.headers.get("x-forwarded-proto", ""))
        host = _first_forwarded_value(request.headers.get("x-forwarded-host", ""))
        forwarded_port = _first_forwarded_value(request.headers.get("x-forwarded-port", ""))
        prefix = _first_forwarded_value(request.headers.get("x-forwarded-prefix", ""))
        if proto and host:
            authority = host
            if forwarded_port and ":" not in host and (
                (proto == "http" and forwarded_port != "80")
                or (proto == "https" and forwarded_port != "443")
            ):
                authority = f"{host}:{forwarded_port}"
            base_url = f"{proto}://{authority}"
            if prefix:
                base_url = _absolute_app_url(base_url, prefix)
            return base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def _tutorial_mcp_endpoint(request) -> str:
    return _absolute_app_url(_request_origin(request), SSE_ENDPOINT)


def _tutorial_skill_slug() -> str:
    return "mcp-explore"


def _tutorial_skill_download_name() -> str:
    return "sediment-mcp-explore-SKILL.md"


def _tutorial_skill_text(locale: str) -> str:
    is_zh = str(locale or "").strip().lower().startswith("zh")
    if is_zh:
        return "\n".join(
            [
                "---",
                "name: sediment-mcp-explore",
                "description: >",
                "  用 MCP `knowledge_list` / `knowledge_read` 在本地完成知识推导，不依赖 `knowledge_ask`。",
                "---",
                "",
                "# Sediment MCP Explore Skill",
                "",
                "这个 Skill 适用于你只暴露 Sediment 的读工具时。",
                "如果你只想快速拿答案，可以直接使用 `knowledge_ask`。",
                "这个 Skill 对应的是另一条路径：不调用 `knowledge_ask`，而是在本地白盒复刻 ask 的推导过程。",
                "",
                "## 默认工作流",
                "",
                "1. 先调用 `knowledge_list` 建立候选条目集合。",
                "2. 选择最相关的 1 到 5 个条目，再调用 `knowledge_read` 读取原文。",
                "3. 如果 `Related`、别名或 Scope 指向新的关键概念，再补读 1 到 2 跳。",
                "4. 在本地综合答案，并显式说明结论、推断和缺口。",
                "",
                "## 推导要求",
                "",
                "- 先回答问题，再补充搜索过程。",
                "- 优先抽取定义、范围、阈值、例外和 Related 关系。",
                "- 如果证据不足或条目互相冲突，要直接说出来。",
                "- 不要无限扩散阅读范围；通常 1 到 2 跳就够。",
                "",
                "## 简单例子",
                "",
                "问题：`热备份的前置条件是什么？`",
                "",
                "建议工具序列：",
                "",
                "- `knowledge_list()`",
                '- `knowledge_read(filename="热备份")`',
                '- 如果 `Related` 指向观测前提，再读 `knowledge_read(filename="回音壁")`',
                "",
                "最后在本地输出答案，并注明使用了哪些条目名。",
            ]
        )
    return "\n".join(
        [
            "---",
            "name: sediment-mcp-explore",
            "description: >",
            "  Use MCP `knowledge_list` / `knowledge_read` to reason locally without relying on `knowledge_ask`.",
            "---",
            "",
            "# Sediment MCP Explore Skill",
            "",
            "Use this Skill when Sediment exposes only its read tools.",
            "If you only need a fast answer, call `knowledge_ask` directly.",
            "This Skill is the other path: instead of calling `knowledge_ask`, reproduce that reasoning loop locally in a white-box way.",
            "",
            "## Default workflow",
            "",
            "1. Call `knowledge_list` first to build a candidate set.",
            "2. Pick the top 1-5 relevant entries, then read them with `knowledge_read`.",
            "3. If `Related`, aliases, or Scope point to another key concept, read 1-2 more hops.",
            "4. Synthesize the answer locally and separate conclusions, inferences, and gaps.",
            "",
            "## Reasoning rules",
            "",
            "- Answer the question first, then explain the search path if needed.",
            "- Prefer definitions, scope, thresholds, exceptions, and Related links.",
            "- Say so plainly when evidence is weak or conflicting.",
            "- Do not widen the read set indefinitely; 1-2 hops is usually enough.",
            "",
            "## Simple example",
            "",
            "Question: `What are the preconditions for hot backup?`",
            "",
            "Suggested tool sequence:",
            "",
            "- `knowledge_list()`",
            '- `knowledge_read(filename="hot-backup")`',
            '- If `Related` points to an observability prerequisite, also read `knowledge_read(filename="echo-wall")`',
            "",
            "Finish by answering locally and naming the entries you used.",
        ]
    )


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
    try:
        result = answer_question_agent_only(question, KB_PATH, _PROJECT_ROOT)
    except RuntimeError as exc:
        result = _error_payload(str(exc))
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
        public_base_url=PUBLIC_BASE_URL,
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


ExploreEventEmitter = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class ExploreRuntimeBundle:
    question: str
    skill_body: str
    runtime_contract: dict[str, Any]
    skill_label: str
    context: dict[str, Any]
    inventory_data: dict[str, Any]
    payload: dict[str, Any]
    project_root: Path


def _emit_explore_event(
    emit: ExploreEventEmitter | None,
    event_type: str,
    message: str,
    **extra: Any,
) -> None:
    level = "INFO"
    if event_type == "retry":
        level = "WARNING"
    elif event_type == "error":
        level = "ERROR"
    EXPLORE_LOGGER.log(
        level,
        f"explore.{event_type}",
        message,
        details=extra or None,
    )
    if emit is None:
        return
    payload = {
        "type": event_type,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(extra)
    emit(payload)


def _trim_explore_excerpt(text: str, limit: int = 400) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(limit - 3, 0)] + "..."


def _summarize_explore_command(invocation: AgentCliInvocation, *, cwd: Path) -> str:
    command = list(invocation.command)
    input_mode = "stdin" if invocation.stdin_data is not None else "argv"
    if "--json-schema" in command:
        schema_mode = "structured-json"
    else:
        schema_mode = "default-output"
    executable = Path(command[0]).name if command else invocation.backend
    return (
        "Launching agent CLI "
        f"{executable} ({invocation.backend}) · input={input_mode} · output={schema_mode} · cwd={cwd}"
    )


def _prepare_explore_runtime(
    question: str,
    *,
    kb_path: Path,
    project_root: Path,
    inventory_data: dict[str, Any] | None = None,
    emit: ExploreEventEmitter | None = None,
) -> ExploreRuntimeBundle:
    if inventory_data is None:
        inventory_data = inventory(kb_path)
    _emit_explore_event(
        emit,
        "status",
        "Loaded KB inventory.",
        formal_entry_count=len(inventory_data.get("entries", [])),
        placeholder_count=len(inventory_data.get("placeholders", [])),
        index_count=len(inventory_data.get("indexes", [])),
    )
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
    _emit_explore_event(
        emit,
        "status",
        "Prepared explore context.",
        shortlist_count=len(context.get("initial_shortlist", [])),
        candidate_count=len(context.get("expanded_candidates", [])),
        routed_index_count=len(context.get("routed_indexes", [])),
    )
    payload = {"question": question, "runtime_contract": runtime_contract, "context": context}
    return ExploreRuntimeBundle(
        question=question,
        skill_body=skill_body,
        runtime_contract=runtime_contract,
        skill_label=skill_label,
        context=context,
        inventory_data=inventory_data,
        payload=payload,
        project_root=project_root,
    )


def _run_explore_runtime_bundle(
    bundle: ExploreRuntimeBundle,
    *,
    emit: ExploreEventEmitter | None = None,
) -> dict[str, Any]:
    result = _run_validated_explore(
        question=bundle.question,
        skill_body=bundle.skill_body,
        runtime_contract=bundle.runtime_contract,
        context=bundle.context,
        payload=bundle.payload,
        project_root=bundle.project_root,
        skill_label=bundle.skill_label,
        inventory_data=bundle.inventory_data,
        emit=emit,
    )
    _emit_explore_event(
        emit,
        "status",
        "Explore completed with agent output.",
        confidence=result.get("confidence", ""),
        source_count=len(result.get("sources", [])),
    )
    return result


def answer_question(question: str, kb_path: Path, project_root: Path) -> dict[str, Any]:
    question = question.strip()
    if not question:
        return _error_payload("Question must not be empty.")

    material_answer = None
    if _explore_fast_only_enabled() and _material_fallback_enabled():
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
        bundle = _prepare_explore_runtime(
            question,
            kb_path=kb_path,
            project_root=project_root,
            inventory_data=inventory_data,
        )

        if not bundle.context["expanded_candidates"]:
            return {
                "answer": "No sufficiently relevant knowledge entries were found for this question.",
                "sources": [],
                "confidence": "low",
                "exploration_summary": {
                    "entries_scanned": len(bundle.inventory_data["entries"]),
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
                inventory_data=bundle.inventory_data,
                context=bundle.context,
                mode_label="local-fastpath",
            )
            if local_answer is not None:
                return local_answer

        return _run_explore_runtime_bundle(bundle)
    except RuntimeError as exc:
        return _error_payload(str(exc))


def answer_question_agent_only(
    question: str,
    kb_path: Path,
    project_root: Path,
    *,
    emit: ExploreEventEmitter | None = None,
) -> dict[str, Any]:
    question = question.strip()
    if not question:
        raise RuntimeError("Question must not be empty.")
    try:
        bundle = _prepare_explore_runtime(
            question,
            kb_path=kb_path,
            project_root=project_root,
            emit=emit,
        )
        return _run_explore_runtime_bundle(bundle, emit=emit)
    except RuntimeError as exc:
        _emit_explore_event(emit, "error", str(exc))
        raise


def _explore_fast_only_enabled() -> bool:
    return os.environ.get("SEDIMENT_EXPLORE_FAST_ONLY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _material_fallback_enabled() -> bool:
    return os.environ.get("SEDIMENT_RUNTIME_ALLOW_MATERIAL_FALLBACK", "").strip().lower() in {
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
        key=lambda item: _direct_candidate_sort_key(question, item),
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
    multi_definition = question_mode == "definition" and len(selected_candidates) > 1

    for item in selected_candidates:
        name = str(item.get("name", "")).strip()
        if not name or name in selected_names:
            continue
        snippet_payload = snippets_by_name.get(name, {})
        snippet_records = snippet_payload.get("snippets", [])
        if not snippet_records:
            doc = inventory_data.get("docs", {}).get(name, {}) or {}
            fallback_records: list[dict[str, str]] = []
            summary = str(doc.get("summary", "")).strip()
            if summary:
                fallback_records.append({"section": "Summary", "text": summary})
            for section_name, content in (doc.get("sections_map", {}) or {}).items():
                if section_name == "Related":
                    continue
                text = str(content).strip()
                if text:
                    fallback_records.append({"section": str(section_name), "text": text})
            snippet_records = fallback_records
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
            evidence_parts.extend(snippet_texts[:1] if multi_definition else snippet_texts[:2])
            if not multi_definition or len(selected_names) >= 2:
                break
            continue
        if direct_shortlist and item is selected_candidates[0]:
            evidence_parts.extend(snippet_texts[:3])
        else:
            evidence_parts.extend(snippet_texts[:2])
        limit = 6 if focus == "diagnosis" else 5
        if len(selected_names) >= 3 or len(evidence_parts) >= limit:
            break

    if not evidence_parts:
        return None

    if question_mode == "definition":
        answer = " ".join(_dedupe_text_parts(evidence_parts)[:2])
    else:
        if _question_prefers_scope_first(question, focus):
            answer = " ".join(_dedupe_text_parts(evidence_parts)[:3])
        else:
            answer = " ".join(_rank_local_evidence_parts(question, focus, evidence_parts)[:3])

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
    question_terms = {item.lower() for item in _local_question_keywords(question)}
    if not question_terms:
        return False
    return any(term in question_terms for term in _candidate_direct_terms(candidate))


_LOCAL_COMPARISON_MARKERS = (
    "关系",
    "关联",
    "联系",
    "区别",
    "差异",
    "对比",
    "relationship",
    "relation",
    "difference",
    "compare",
)
_LOCAL_GUIDANCE_MARKERS = (
    "流程",
    "步骤",
    "阶段",
    "如何",
    "怎么",
    "怎样",
    "判断",
    "评估",
    "process",
    "workflow",
    "step",
    "steps",
    "stage",
    "stages",
    "determine",
    "judge",
    "assess",
)
_LOCAL_SCOPE_MARKERS = (
    "有哪些",
    "多少",
    "多少个",
    "哪几种",
    "哪些类型",
    "范围",
    "区间",
    "安全运行区间",
    "消息类型",
    "路由策略",
    "部署策略",
    "故障类型",
    "监测点",
    "生命周期",
    "数据质量",
    "质量",
    "如何判断",
    "在什么条件下",
    "什么条件下",
    "在什么情况下",
    "什么情况下",
    "内容是什么",
    "规则是什么",
    "触发条件",
    "启动条件",
    "what types",
    "which types",
    "how many",
    "what does",
    "what is the rule",
    "what is the content",
    "data quality",
    "under what condition",
    "under what conditions",
    "what condition",
    "what conditions",
    "trigger condition",
    "trigger conditions",
    "start condition",
    "start conditions",
)
_LOCAL_DIAGNOSIS_MARKERS = (
    "可能是什么问题",
    "根因",
    "缺陷",
    "漏检",
    "误判",
    "延迟",
    "故障类型",
    "哪些类型的故障",
    "root cause",
    "defect",
    "fault type",
    "fault types",
    "failure type",
    "failure types",
    "what could be wrong",
    "misjudge",
    "misjudgment",
    "delay",
)
_LOCAL_WHY_MARKERS = (
    "为什么",
    "原因",
    "为何",
    "why",
    "reason",
    "reasons",
)
_LOCAL_HOW_MARKERS = (
    "如何",
    "怎么",
    "怎样",
    "步骤",
    "准备",
    "协作",
    "配合",
    "需要",
    "how",
    "prepare",
    "preparation",
    "coordinate",
    "coordination",
    "work together",
    "need",
)
_LOCAL_RISK_MARKERS = (
    "风险",
    "后果",
    "误区",
    "避免",
    "risk",
    "risks",
    "consequence",
    "consequences",
    "pitfall",
    "pitfalls",
    "avoid",
)
_LOCAL_DIRECT_MULTI_MARKERS = (
    "分别",
    "和",
    "与",
    "及",
    "之间",
    " and ",
    " with ",
    " between ",
)
_LOCAL_COMBINED_REASONING_MARKERS = (
    "过程",
    "过程中",
    "结合",
    "根据",
    "综合",
    "推断",
    "during",
    "combine",
    "combined",
    "based on",
    "infer",
    "inference",
)
_LOCAL_SCOPE_FIRST_MARKERS = (
    "有哪些",
    "多少",
    "多少个",
    "哪几种",
    "哪些类型",
    "范围",
    "区间",
    "安全运行区间",
    "消息类型",
    "路由策略",
    "部署策略",
    "故障类型",
    "监测点",
    "生命周期",
    "流程",
    "步骤",
    "阶段",
    "准备",
    "如何判断",
    "判断",
    "质量",
    "在什么条件下",
    "什么条件下",
    "内容是什么",
    "规则是什么",
    "触发条件",
    "启动条件",
    "what types",
    "which types",
    "how many",
    "process",
    "workflow",
    "step",
    "steps",
    "stage",
    "stages",
    "preparation",
    "data quality",
    "under what condition",
    "under what conditions",
    "trigger condition",
    "trigger conditions",
)
_LOCAL_QUERYABLE_TERM_SUFFIXES = (
    "节点的",
    "节点",
    "数据",
    "技术",
    "团队",
    "指标",
    "质量",
    "级别",
)
_LOCAL_SURFACE_FILLERS = (
    "完整",
    "当前",
    "默认",
    "整体",
    "全系统",
    "全局",
    "complete",
    "current",
    "default",
    "overall",
)
_LOCAL_STRUCTURED_SURFACE_GROUPS = {
    "消息类型": ("消息类型", "报文类型", "message type", "message types"),
    "路由策略": ("路由策略", "路由规则", "routing strategy", "routing strategies", "route strategy", "route strategies"),
    "故障类型": ("故障类型", "异常类", "类型的故障", "fault type", "fault types", "failure type", "failure types"),
    "设计哲学": ("设计哲学", "design philosophy", "system philosophy"),
    "生命周期": ("生命周期", "lifecycle", "life cycle"),
    "监测点": ("监测点", "监控点", "monitoring point", "monitor point"),
}
_LOCAL_ARTIFACT_WRAPPER_SUFFIXES = ("路由表", "报文定义", "监测点配置")
_LOCAL_LOW_SIGNAL_ENTRY_NAMES = {
    "技术",
    "系统",
    "指标",
    "调查",
    "报告",
    "事件",
    "流程",
    "步骤",
    "内容",
    "定义",
    "规则",
    "配置",
    "接口",
    "能力",
    "现状",
    "机制",
}
_LOCAL_LOW_SIGNAL_DEFINITION_MARKERS = (
    "一种模式或状态",
    "正式流程中的一个阶段",
    "用于表达当前处理阶段",
    "相关系统",
    "名称 定义 目标值 告警阈值",
)
_LOCAL_LOW_SIGNAL_NAME_PREFIXES = (
    "当前",
    "核心",
    "默认",
    "通知",
    "负责",
    "注册",
    "核对",
    "本人",
    "制定",
    "系统设计的",
)
_LOCAL_LOW_SIGNAL_NAME_SUFFIXES = ("检测", "执行", "记录", "归档", "通知")
_LOCAL_DEFINITION_MARKERS = (
    "是",
    "指",
    "用于",
    "负责",
    "衡量",
    "表示",
    "属于",
    "提供",
    "设备",
    "团队",
    "角色",
    "系统",
    "协议",
    "策略",
    "阈值",
    "指标",
)
_LOCAL_DEFINITION_SUPPORT_MARKERS = (
    "核心资源",
    "物质基础",
    "管理系统",
    "控制中枢",
    "异常现象",
    "触发",
    "阈值",
    "步骤",
    "阶段",
    "流程",
    "不能完全",
    "账房",
    "收支",
    "负载均衡",
    "中继",
    "缓冲",
    "留声机",
    "底噪",
    "峰谷差",
    "幽灵读数",
)


def _question_has_marker(question: str, markers: tuple[str, ...]) -> bool:
    lowered = question.lower()
    return any(marker in lowered for marker in markers)


def _local_question_focus(question: str, context: dict[str, Any]) -> str:
    if _question_has_marker(question, _LOCAL_COMPARISON_MARKERS):
        return "comparison"
    if _question_has_marker(question, _LOCAL_WHY_MARKERS):
        return "why"
    if _question_has_marker(question, _LOCAL_DIAGNOSIS_MARKERS):
        return "diagnosis"
    if _question_has_marker(question, _LOCAL_RISK_MARKERS):
        return "risk"
    if _question_has_marker(question, _LOCAL_SCOPE_MARKERS):
        return "scope"
    if _question_has_marker(question, _LOCAL_GUIDANCE_MARKERS):
        return "guidance"
    focus = str(context.get("question_analysis", {}).get("focus", "open"))
    if focus != "open":
        return focus
    if _question_has_marker(question, _LOCAL_HOW_MARKERS):
        return "guidance"
    return focus


def _local_question_mode(question: str, context: dict[str, Any]) -> str:
    if _question_has_marker(question, _LOCAL_DIAGNOSIS_MARKERS):
        return "open"
    if _question_has_marker(question, _LOCAL_GUIDANCE_MARKERS + _LOCAL_SCOPE_MARKERS):
        return "guidance"
    focus = str(context.get("question_analysis", {}).get("focus", "open"))
    if focus == "comparison":
        return "comparison"
    if focus == "diagnosis":
        return "open"
    if focus == "scope":
        return "open"
    if focus in {"why", "when"}:
        return "guidance"
    if focus == "risk":
        return "risk"
    if _question_has_marker(question, _LOCAL_COMPARISON_MARKERS):
        return "comparison"
    if any(
        marker in question.lower()
        for marker in (
            "什么是",
            "是什么",
            "是什么意思",
            "指什么",
            "是做什么的",
            "作用是什么",
            "负责什么",
            "衡量什么",
            "what is",
            "what does",
            "mean",
            "used for",
            "responsible for",
            "measure",
        )
    ):
        return "definition"
    if _question_has_marker(question, _LOCAL_WHY_MARKERS):
        return "guidance"
    if _question_has_marker(question, _LOCAL_HOW_MARKERS):
        return "guidance"
    if _question_has_marker(question, _LOCAL_RISK_MARKERS):
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
    cleaned_summary = _clean_local_snippet(fallback_summary, focus=focus, question=question)
    if question_mode == "definition":
        definition_snippet = _best_definition_snippet(
            question=question,
            candidate=candidate,
            snippet_records=snippet_records,
            fallback_summary=cleaned_summary,
        )
        if definition_snippet:
            support_snippet = _best_definition_support_snippet(
                question=question,
                candidate=candidate,
                snippet_records=snippet_records,
                fallback_summary=cleaned_summary,
                primary_snippet=definition_snippet,
            )
            if _should_append_definition_support(
                question=question,
                primary_snippet=definition_snippet,
                support_snippet=support_snippet,
            ):
                return [definition_snippet, support_snippet]
            return [definition_snippet]
        if cleaned_summary:
            return [_first_sentence(cleaned_summary)]

    direct_match = _is_direct_candidate_match(question, candidate)
    prefer_scope_first = _question_prefers_scope_first(question, focus)
    section_order = _local_section_priority(
        entry_type=str(candidate.get("entry_type", "")),
        question_mode=question_mode,
        focus=focus,
        direct_match=direct_match,
    )
    snippets_by_section = {
        str(record.get("section", "")): _clean_local_snippet(
            str(record.get("text", "")).strip(),
            focus=focus,
            question=question,
        )
        for record in snippet_records
        if str(record.get("text", "")).strip()
    }

    selected: list[str] = []
    if cleaned_summary and not prefer_scope_first:
        selected.append(cleaned_summary)
    for section in section_order:
        text = snippets_by_section.get(section)
        if text and text not in selected:
            selected.append(text)
    if cleaned_summary and prefer_scope_first and cleaned_summary not in selected:
        selected.append(cleaned_summary)

    for record in snippet_records:
        text = _clean_local_snippet(
            str(record.get("text", "")).strip(),
            focus=focus,
            question=question,
        )
        if text and text not in selected:
            selected.append(text)

    if not selected and cleaned_summary:
        selected.append(cleaned_summary)

    if direct_match and question_mode != "comparison":
        return selected[:3]
    return selected[:2]


def _normalize_local_surface(text: str) -> str:
    lowered = text.strip().lower().replace("的", "")
    for filler in _LOCAL_SURFACE_FILLERS:
        lowered = lowered.replace(filler, "")
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", lowered)


def _low_signal_name_summary(name: str, summary: str) -> int:
    penalty = 0
    if name in _LOCAL_LOW_SIGNAL_ENTRY_NAMES:
        penalty += 72
    if name.startswith(_LOCAL_LOW_SIGNAL_NAME_PREFIXES):
        penalty += 36
    if name.endswith(_LOCAL_LOW_SIGNAL_NAME_SUFFIXES) and len(name) <= 8:
        penalty += 28
    if "完整生命周期" in name and any(marker in name for marker in ("故障类型", "管理")):
        penalty += 56
    if any(marker in name for marker in ("中的", "里的", "时", "后", "前", "通知", "负责", "使用", "全部在", "加强了")):
        penalty += 36
    if name.endswith(("内容", "现状", "情况", "方式", "机制")) and len(name) <= 6:
        penalty += 24
    if any(marker in summary for marker in _LOCAL_LOW_SIGNAL_DEFINITION_MARKERS):
        penalty += 20
    return penalty


def _low_signal_candidate_penalty(candidate: dict[str, Any]) -> int:
    return _low_signal_name_summary(
        str(candidate.get("name", "")).strip(),
        str(candidate.get("summary", "")).strip(),
    )


def _split_local_sentences(text: str) -> list[str]:
    return [
        item.strip() + "。"
        for item in re.split(r"[。！？!?；;\n]", text)
        if item.strip()
    ]


def _definition_sentence_score(
    *,
    question: str,
    candidate: dict[str, Any],
    sentence: str,
    section: str,
) -> tuple[int, int]:
    value = 0
    lowered = sentence.lower()
    question_keywords = _local_question_keywords(question)
    if any(keyword and keyword in sentence for keyword in question_keywords):
        value += 4
    if any(term and term in lowered for term in _candidate_direct_terms(candidate)):
        value += 3
    if any(marker in sentence for marker in _LOCAL_DEFINITION_MARKERS):
        value += 3
    if section == "Summary":
        value += 2
    if section == "Scope":
        value += 1
    value -= _low_signal_name_summary(str(candidate.get("name", "")).strip(), sentence)
    if 12 <= len(sentence) <= 100:
        value += 1
    return value, -len(sentence)


def _best_definition_snippet(
    *,
    question: str,
    candidate: dict[str, Any],
    snippet_records: list[dict[str, Any]],
    fallback_summary: str,
) -> str:
    options: list[tuple[tuple[int, int], str]] = []
    seen: set[str] = set()

    def add_option(text: str, section: str) -> None:
        cleaned = _clean_local_snippet(text, focus="definition", question=question)
        for sentence in _split_local_sentences(cleaned):
            if sentence in seen:
                continue
            seen.add(sentence)
            options.append(
                (
                    _definition_sentence_score(
                        question=question,
                        candidate=candidate,
                        sentence=sentence,
                        section=section,
                    ),
                    sentence,
                )
            )

    for record in snippet_records:
        add_option(str(record.get("text", "")).strip(), str(record.get("section", "")))
    if fallback_summary:
        add_option(fallback_summary, "Summary")
    if not options:
        return ""
    options.sort(key=lambda item: item[0], reverse=True)
    return options[0][1]


def _definition_support_sentence_score(
    *,
    question: str,
    candidate: dict[str, Any],
    sentence: str,
    section: str,
    primary_snippet: str,
) -> tuple[int, int]:
    value = 0
    question_keywords = _local_question_keywords(question)
    primary_keywords = {
        keyword for keyword in question_keywords if keyword and keyword in primary_snippet
    }
    if any(keyword and keyword in sentence and keyword not in primary_keywords for keyword in question_keywords):
        value += 4
    if any(marker in sentence for marker in _LOCAL_DEFINITION_SUPPORT_MARKERS):
        value += 3
    if any(term and term in sentence.lower() for term in _candidate_direct_terms(candidate)):
        value += 2
    if section == "Scope":
        value += 2
    if 16 <= len(sentence) <= 140:
        value += 1
    value -= _low_signal_name_summary(str(candidate.get("name", "")).strip(), sentence)
    return value, -len(sentence)


def _best_definition_support_snippet(
    *,
    question: str,
    candidate: dict[str, Any],
    snippet_records: list[dict[str, Any]],
    fallback_summary: str,
    primary_snippet: str,
) -> str:
    if not primary_snippet:
        return ""

    options: list[tuple[tuple[int, int], str]] = []
    seen: set[str] = {primary_snippet}

    def add_option(text: str, section: str) -> None:
        cleaned = _clean_local_snippet(text, focus="definition", question=question)
        for sentence in _split_local_sentences(cleaned):
            if (
                sentence in seen
                or sentence in primary_snippet
                or primary_snippet in sentence
            ):
                continue
            seen.add(sentence)
            options.append(
                (
                    _definition_support_sentence_score(
                        question=question,
                        candidate=candidate,
                        sentence=sentence,
                        section=section,
                        primary_snippet=primary_snippet,
                    ),
                    sentence,
                )
            )

    for record in snippet_records:
        add_option(str(record.get("text", "")).strip(), str(record.get("section", "")))
    if fallback_summary:
        add_option(fallback_summary, "Summary")
    if not options:
        return ""
    options.sort(key=lambda item: item[0], reverse=True)
    best_score, best_sentence = options[0]
    if best_score[0] <= 0:
        return ""
    return best_sentence


def _should_append_definition_support(
    *,
    question: str,
    primary_snippet: str,
    support_snippet: str,
) -> bool:
    if not support_snippet:
        return False
    if support_snippet in primary_snippet or primary_snippet in support_snippet:
        return False
    if len(primary_snippet) <= 24:
        return True
    if any(marker in question for marker in ("负责什么", "是什么系统", "是否", "能完全", "衡量什么")):
        return True
    if any(marker in support_snippet for marker in _LOCAL_DEFINITION_SUPPORT_MARKERS):
        return True
    primary_keywords = set(_local_question_keywords(primary_snippet))
    support_keywords = set(_local_question_keywords(support_snippet))
    question_keywords = set(_local_question_keywords(question))
    return bool((support_keywords - primary_keywords) & question_keywords)


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
    if focus == "diagnosis":
        return ["Scope", "Why", "Risks", "Summary", "Trigger", "Related"]
    if focus == "scope":
        return ["Scope", "Summary", "Why", "Trigger", "Risks", "Related"]
    if focus == "why":
        return ["Summary", "Why", "Scope", "Trigger", "Risks", "Related"]
    if focus == "risk":
        return ["Summary", "Risks", "Scope", "Why", "Trigger", "Related"]
    if focus == "guidance":
        if entry_type == "lesson":
            return ["Scope", "Trigger", "Why", "Risks", "Summary", "Related"]
        return ["Scope", "Summary", "Trigger", "Why", "Risks", "Related"]
    if direct_match:
        return ["Summary", "Scope", "Why", "Trigger", "Risks", "Related"]
    return ["Summary", "Scope", "Why", "Trigger", "Risks", "Related"]


def _clean_local_snippet(text: str, *, focus: str, question: str = "") -> str:
    cleaned = _strip_wikilinks(text.strip())
    if not cleaned:
        return ""
    if focus != "comparison":
        cleaned = re.sub(r"而不是[^。；]*", "", cleaned)
        cleaned = re.sub(r"不等于[^。；]*", "", cleaned)
    sentences = [
        item.strip()
        for item in re.split(r"[。！？!?]", cleaned)
        if item.strip()
    ]
    preferred = [item for item in sentences if not item.startswith("适用于")]
    chosen = preferred or sentences
    question_keywords = _local_question_keywords(question)
    wants_decision_evidence = _question_requests_decision_evidence(question)
    if focus == "guidance" and _question_prefers_scope_first(question, focus):
        ordered = chosen[:3]
        if ordered:
            return "。".join(ordered).strip() + "。"

    def score(sentence: str) -> tuple[int, int]:
        value = 0
        if any(keyword and keyword in sentence for keyword in question_keywords):
            value += 4
        if focus == "why" and any(
            marker in sentence for marker in ("因为", "因此", "导致", "原因", "误判", "漏检", "高发", "风险")
        ):
            value += 3
        if focus == "diagnosis" and any(marker in sentence for marker in ("导致", "根因", "误判", "盲区", "晦暗", "泄漏", "故障", "异常", "漏检")):
            value += 3
        if focus == "risk" and any(
            marker in sentence for marker in ("不能", "无法", "仍会", "仍然", "暴露", "只能", "绕过", "交叉验证")
        ):
            value += 3
        if focus == "guidance" and any(
            marker in sentence
            for marker in ("步骤", "流程", "先", "再", "然后", "执行", "启动", "确认", "通知", "创建", "监测")
        ):
            value += 2
        if focus == "scope" and any(marker in sentence for marker in ("阈值", "范围", "周期", "数量", "类型")):
            value += 2
        if _question_has_marker(question, ("触发条件", "启动条件", "在什么条件下", "什么条件下", "在什么情况下", "什么情况下")):
            condition_hits = sum(
                1
                for marker in ("阈值", "突破", "超过", "低于", "是否需要", "决定", "泄洪", "红线", "晦暗", "反射率")
                if marker in sentence
            )
            if condition_hits:
                value += min(condition_hits, 4) + 2
        if _question_has_marker(question, ("质量", "如何判断", "数据质量")):
            quality_hits = sum(
                1
                for marker in ("底噪", "毛刺", "峰谷差", "幽灵读数", "留声机", "趋势")
                if marker in sentence
            )
            if quality_hits:
                value += quality_hits * 3 + 1
        if _question_has_marker(question, ("范围", "区间", "安全运行区间")):
            boundary_hits = sum(
                1
                for marker in ("底噪", "共振峰", "红线", "安全弦", "420.0", "580.0", "720.0")
                if marker in sentence
            )
            if boundary_hits:
                value += boundary_hits * 3 + 1
        if _question_has_marker(question, ("部署策略", "路由表", "部署", "监测点")):
            deployment_hits = sum(
                1
                for marker in ("高频路径", "双中继", "跨区边界", "偏远", "种月", "负载均衡", "缓冲", "覆盖", "埋点")
                if marker in sentence
            )
            if deployment_hits:
                value += deployment_hits * 3
        if _question_has_marker(question, ("故障类型", "异常类", "哪些类型的故障")):
            fault_hits = sum(
                1
                for marker in ("坍缩", "红线", "镀层缺陷", "饱和度", "异常", "故障")
                if marker in sentence
            )
            if fault_hits:
                value += fault_hits * 2 + 1
        if _question_has_marker(question, ("生命周期", "阶段")):
            lifecycle_hits = sum(
                1
                for marker in ("阶段", "建设验收", "开光启用", "正常运行", "维护更新", "退役处置")
                if marker in sentence
            )
            if lifecycle_hits:
                value += min(lifecycle_hits, 4) + 2
        if _question_has_marker(question, ("缺陷", "漏检", "盲区")):
            gap_hits = sum(
                1
                for marker in ("盲区", "漏检", "覆盖", "死角")
                if marker in sentence
            )
            if gap_hits:
                value += min(gap_hits, 3) + 2
        if wants_decision_evidence and any(
            marker in sentence for marker in ("不能", "无法", "仍会", "仍然", "暴露", "只要")
        ):
            value += 3
        return value, -len(sentence)

    chosen = sorted(chosen, key=score, reverse=True)[:2] or chosen
    if not chosen:
        return ""
    return "。".join(chosen[:2]).strip() + "。"


def _local_question_keywords(question: str) -> list[str]:
    stopwords = {
        "什么",
        "哪些",
        "为什么",
        "内容",
        "根据",
        "综合",
        "推断",
        "完整流程",
        "流程",
        "步骤",
        "阶段",
        "条件",
        "问题",
        "原因",
        "根因",
        "系统",
        "代码",
        "定义",
        "处理",
        "方法",
        "逻辑",
        "what",
        "which",
        "why",
        "content",
        "based",
        "infer",
        "question",
        "questions",
        "reason",
        "reasons",
        "system",
        "code",
        "definition",
        "define",
        "process",
        "workflow",
        "step",
        "steps",
        "stage",
        "stages",
        "condition",
        "conditions",
        "method",
        "logic",
    }
    keywords: list[str] = []
    candidates: list[str] = []
    target_hint = _question_target_hint(question)
    if target_hint:
        candidates.append(target_hint)

    normalized = question.strip().strip("？?")
    for clause in re.split(r"[，,；;。]", normalized):
        clause = clause.strip()
        if not clause:
            continue
        candidates.append(clause)
        trimmed = _trim_target_phrase(clause)
        if trimmed and trimmed != clause:
            candidates.append(trimmed)

    for item in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{1,47}", normalized):
        candidates.append(item.lower())

    for candidate in candidates:
        for item in _question_keyword_components(candidate):
            lowered = item.lower()
            if lowered in stopwords or len(item) < 2:
                continue
            if item not in keywords:
                keywords.append(item)
    return keywords


def _question_keyword_components(text: str) -> list[str]:
    cleaned = text.strip().strip("？?")
    if not cleaned:
        return []
    for prefix in (
        "什么是",
        "什么叫",
        "请问",
        "为什么",
        "如何判断",
        "怎么判断",
        "怎样判断",
        "如何评估",
        "怎么评估",
        "怎样评估",
        "根据",
        "结合",
        "综合",
        "从",
        "对",
        "按",
        "基于",
        "如果",
        "当前",
        "一个",
        "请",
    ):
        if cleaned.startswith(prefix) and len(cleaned) > len(prefix) + 1:
            cleaned = cleaned[len(prefix):].strip()
    cleaned = _trim_target_phrase(cleaned)
    if not cleaned:
        return []

    parts = [cleaned]
    for splitter in ("和", "与", "及", "以及", "、", "从", "且", "并且"):
        next_parts: list[str] = []
        for part in parts:
            next_parts.extend(chunk for chunk in part.split(splitter) if chunk)
        parts = next_parts or parts

    results: list[str] = []

    def append_variant(value: str) -> None:
        compact_value = value.strip(" ，。；：:").strip()
        if not compact_value:
            return
        if compact_value not in results:
            results.append(compact_value)
        for suffix in _LOCAL_QUERYABLE_TERM_SUFFIXES:
            if compact_value.endswith(suffix) and len(compact_value) > len(suffix) + 1:
                trimmed = compact_value[: -len(suffix)].strip()
                if len(trimmed) >= 2 and trimmed not in results:
                    results.append(trimmed)

    def append_structured_projection(value: str) -> None:
        compact_value = value.strip(" ，。；：:").strip()
        if not compact_value:
            return
        projected = compact_value
        for prefix in ("管理", "完整", "当前", "默认", "整体", "全系统", "全局"):
            if projected.startswith(prefix) and len(projected) > len(prefix) + 1:
                projected = projected[len(prefix):].strip()
        projected = projected.replace("完整", "").replace("当前", "").replace("默认", "")
        projected = projected.replace("的", "")
        if projected != compact_value and any(
            marker in projected
            for marker in ("生命周期", "路由策略", "故障类型", "消息类型", "监测点", "设计哲学")
        ):
            append_variant(projected)

    for part in parts:
        compact = part.strip(" ，。；：:").strip()
        for prefix in ("一个", "当前", "该", "此", "其"):
            if compact.startswith(prefix) and len(compact) > len(prefix) + 1:
                compact = compact[len(prefix):].strip()
        for suffix in ("前", "后"):
            if compact.endswith(suffix) and len(compact) > 2:
                compact = compact[: -len(suffix)].strip()
        if not compact:
            continue
        append_variant(compact)
        append_structured_projection(compact)
        for marker in ("建议增加", "建议扩展", "建议新增", "建议加装", "可能遇到", "可能出现", "增加", "新增", "加装", "扩展", "部署", "启用", "停用", "避免", "确认", "执行", "完成", "恢复", "触发"):
            if marker in compact:
                prefix = compact.split(marker, 1)[0].strip(" ，。；：:")
                suffix = compact.split(marker, 1)[1].strip(" ，。；：:")
                if len(prefix) >= 2:
                    append_variant(prefix)
                    append_structured_projection(prefix)
                if len(suffix) >= 2:
                    append_variant(suffix)
                    append_structured_projection(suffix)
        for marker in ("目前", "现在"):
            if marker in compact:
                prefix = compact.split(marker, 1)[0].strip(" ，。；：:")
                if len(prefix) >= 2:
                    append_variant(prefix)
                    append_structured_projection(prefix)
        for marker in ("持续下降", "出现", "发生", "执行", "完成", "触发", "进入", "恢复", "升级", "降低"):
            if marker in compact:
                prefix = compact.split(marker, 1)[0].strip(" ，。；：:")
                if len(prefix) >= 2:
                    append_variant(prefix)
                    append_structured_projection(prefix)
        if "的" in compact and len(compact) >= 6:
            for piece in compact.split("的"):
                piece = piece.strip()
                if len(piece) >= 2:
                    append_variant(piece)
                    append_structured_projection(piece)
    return results


def _question_prefers_scope_first(question: str, focus: str) -> bool:
    if focus not in {"guidance", "scope"}:
        return False
    return _question_has_marker(question, _LOCAL_SCOPE_FIRST_MARKERS)


def _question_requests_decision_evidence(question: str) -> bool:
    return _question_has_marker(
        question,
        (
            "是否",
            "能完全",
            "完全避免",
            "能否",
            "可否",
            "可以避免",
            "会不会",
            "will it",
            "can it",
            "can avoid",
        ),
    )


def _dedupe_text_parts(parts: list[str]) -> list[str]:
    deduped: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue
        if any(cleaned in existing or existing in cleaned for existing in deduped):
            continue
        deduped.append(cleaned)
    return deduped


def _rank_local_evidence_parts(question: str, focus: str, parts: list[str]) -> list[str]:
    deduped = _dedupe_text_parts(parts)
    keywords = _local_question_keywords(question)
    wants_decision_evidence = _question_requests_decision_evidence(question)

    def score(part: str) -> tuple[int, int]:
        value = 0
        if any(keyword and keyword in part for keyword in keywords):
            value += 4
        if focus == "why" and any(
            marker in part
            for marker in ("因为", "因此", "导致", "原因", "误判", "漏检", "高发", "风险")
        ):
            value += 3
        if focus == "diagnosis" and any(
            marker in part for marker in ("导致", "根因", "盲区", "晦暗", "泄漏", "故障", "异常", "换羽")
        ):
            value += 3
        if focus == "risk" and any(
            marker in part
            for marker in ("不能", "无法", "仍会", "仍然", "暴露", "只能", "绕过", "交叉验证")
        ):
            value += 3
        if focus == "guidance" and any(
            marker in part
            for marker in ("步骤", "流程", "先", "再", "然后", "执行", "启动", "确认", "通知", "创建", "监测")
        ):
            value += 2
        if focus == "scope" and any(marker in part for marker in ("阈值", "范围", "周期", "数量", "类型")):
            value += 2
        if _question_has_marker(question, ("质量", "如何判断", "数据质量")):
            quality_hits = sum(
                1
                for marker in ("底噪", "毛刺", "峰谷差", "幽灵读数", "留声机", "趋势")
                if marker in part
            )
            if quality_hits:
                value += quality_hits * 3 + 1
        if _question_has_marker(question, ("范围", "区间", "安全运行区间")):
            boundary_hits = sum(
                1
                for marker in ("底噪", "共振峰", "红线", "安全弦", "420.0", "580.0", "720.0")
                if marker in part
            )
            if boundary_hits:
                value += boundary_hits * 3 + 1
        if _question_has_marker(question, ("部署策略", "路由表", "部署", "监测点")):
            deployment_hits = sum(
                1
                for marker in ("高频路径", "双中继", "跨区边界", "偏远", "种月", "负载均衡", "缓冲", "覆盖", "埋点")
                if marker in part
            )
            if deployment_hits:
                value += deployment_hits * 3
        if _question_has_marker(question, ("故障类型", "异常类", "哪些类型的故障")):
            fault_hits = sum(
                1
                for marker in ("坍缩", "红线", "镀层缺陷", "饱和度", "异常", "故障")
                if marker in part
            )
            if fault_hits:
                value += fault_hits * 2 + 1
        if wants_decision_evidence and any(
            marker in part for marker in ("不能", "无法", "仍会", "仍然", "暴露", "只要")
        ):
            value += 3
        return value, -len(part)

    return sorted(deduped, key=score, reverse=True)


def _question_target_surface(question: str) -> str:
    target_hint = _question_target_hint(question)
    if target_hint:
        return target_hint
    return _trim_target_phrase(question)


def _question_target_has_multiple_entities(question: str) -> bool:
    surface = _question_target_surface(question)
    if not surface:
        return False
    if not any(splitter in surface for splitter in ("和", "与", "及", "以及", "、", " and ", " with ", " between ")):
        return False
    components = [
        item
        for item in _question_keyword_components(surface)
        if len(item) >= 2
    ]
    distinct: list[str] = []
    for item in components:
        if any(item in existing or existing in item for existing in distinct):
            continue
        distinct.append(item)
    return len(distinct) >= 2


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
    primary_doc = docs.get(primary_name, {}) or {}
    primary_links = set(primary_doc.get("graph_links", ()) or primary_doc.get("links", ()) or ())
    direct_graph_neighbors: set[str] = set(primary_links)
    secondary_graph_neighbors: set[str] = set()
    for selected_name in selected_names:
        selected_doc = docs.get(selected_name, {}) or {}
        selected_links = set(selected_doc.get("graph_links", ()) or selected_doc.get("links", ()) or ())
        direct_graph_neighbors.update(selected_links)
    for neighbor_name in direct_graph_neighbors:
        neighbor_doc = docs.get(neighbor_name, {}) or {}
        secondary_graph_neighbors.update(
            set(neighbor_doc.get("graph_links", ()) or neighbor_doc.get("links", ()) or ())
        )
    supplemented: list[tuple[int, dict[str, Any]]] = []
    question_keywords = _local_question_keywords(question)
    wants_decision_evidence = _question_requests_decision_evidence(question)

    for name, doc in docs.items():
        if name in selected_names or doc.get("kind") != "formal":
            continue
        if any(name != existing and name in existing for existing in selected_names):
            continue
        summary = str(doc.get("summary", "")).strip()
        low_signal_penalty = _low_signal_name_summary(name, summary)
        if low_signal_penalty >= 72 and name not in question:
            continue
        sections_map = doc.get("sections_map", {}) or {}
        evidence_text = " ".join([summary, *[str(value) for value in sections_map.values()]])
        rank = 0
        rank += _local_structured_surface_bonus(
            question,
            {
                "name": name,
                "matched_terms": [],
            },
        ) // 14
        rank -= _local_artifact_wrapper_penalty(
            question,
            {
                "name": name,
                "matched_terms": [],
            },
        ) // 14
        if any(marker in summary for marker in ("角色", "负责", "主持", "权限", "团队")):
            rank += 2
        if any(marker in question for marker in ("谁", "权限", "角色")):
            rank += 1
        if name in primary_text:
            rank += 3
        if primary_name and primary_name in evidence_text:
            rank += 2
        doc_links = set(doc.get("graph_links", ()) or doc.get("links", ()) or ())
        if name in primary_links or primary_name in doc_links:
            rank += 4
        if name in direct_graph_neighbors or doc_links & selected_names:
            rank += 6
        if name in secondary_graph_neighbors or doc_links & direct_graph_neighbors:
            rank += 4
        if name in question:
            rank += 4
        if any(keyword and keyword in evidence_text for keyword in question_keywords):
            rank += 2
        if focus == "why" and any(
            marker in evidence_text
            for marker in ("因为", "因此", "导致", "原因", "误判", "漏检", "高发", "风险", "建议")
        ):
            rank += 3
        if focus in {"guidance", "scope"} and _question_has_marker(question, ("流程", "步骤", "阶段", "顺序", "经历")):
            if any(marker in evidence_text for marker in ("流程", "步骤", "阶段", "顺序", "生命周期", "开光", "试音", "启明", "正式运行")):
                rank += 3
        if _question_has_marker(question, ("生命周期", "阶段")):
            if "生命周期" in name and not any(marker in name for marker in ("管理", "完整")):
                rank += 4
            if any(marker in name for marker in ("管理", "完整生命周期故障类型")):
                rank -= 3
        if _question_has_marker(question, ("质量", "如何判断", "数据质量")):
            quality_hits = sum(
                1
                for marker in ("底噪", "毛刺", "峰谷差", "幽灵读数", "留声机")
                if marker in evidence_text
            )
            rank += quality_hits * 3
            if name in {"底噪", "毛刺", "峰谷差", "幽灵读数", "留声机"}:
                rank += 8
        if _question_has_marker(question, ("部署策略", "部署", "监测点", "盲区", "漏检", "最大缺陷")):
            deployment_hits = sum(
                1
                for marker in ("部署", "负载均衡", "中继", "缓冲", "覆盖", "盲区", "漏检", "埋点", "高频路径", "双中继", "跨区边界", "偏远", "种月")
                if marker in evidence_text
            )
            if deployment_hits:
                rank += deployment_hits * 2 + 2
        if focus == "diagnosis" and _question_has_marker(question, ("缺陷", "漏检", "盲区")):
            if any(marker in evidence_text for marker in ("盲区", "漏检", "覆盖", "死角")):
                rank += 5
        if _question_has_marker(question, ("范围", "区间", "安全运行区间")):
            boundary_hits = sum(
                1
                for marker in ("底噪", "共振峰", "红线", "安全弦", "420.0", "580.0", "720.0")
                if marker in evidence_text
            )
            if boundary_hits:
                rank += boundary_hits * 3 + 2
        if _question_has_marker(question, ("触发条件", "启动条件", "在什么条件下", "什么条件下", "在什么情况下", "什么情况下")):
            if any(marker in evidence_text for marker in ("阈值", "晦暗", "反射率", "老化", "触发", "判官", "红线", "超过", "低于")):
                rank += 4
            if any(marker in name for marker in ("晦暗", "红线", "判官", "饱和度")):
                rank += 4
        if _question_has_marker(question, ("故障类型", "异常类", "哪些类型的故障")):
            fault_hits = sum(
                1
                for marker in ("坍缩", "红线", "镀层缺陷", "饱和度", "异常", "故障")
                if marker in evidence_text
            )
            if fault_hits:
                rank += fault_hits * 2 + 2
        if any(marker in question for marker in ("质量", "判断", "是否", "能完全", "完全避免")):
            if any(marker in evidence_text for marker in ("阈值", "趋势", "峰谷差", "毛刺", "底噪", "幽灵读数", "留声机", "告警", "不能完全", "只能", "仍会", "仍然")):
                rank += 3
        if focus == "risk" and any(
            marker in evidence_text
            for marker in ("不能", "无法", "仍会", "仍然", "暴露", "只能", "绕过", "交叉验证", "审计")
        ):
            rank += 3
        if wants_decision_evidence and any(
            marker in evidence_text
            for marker in ("不能", "无法", "仍会", "仍然", "暴露", "只要", "审计", "交叉验证")
        ):
            rank += 2
        if focus == "diagnosis" and any(
            marker in evidence_text
            for marker in ("导致", "根因", "误判", "盲区", "晦暗", "泄漏", "故障", "异常", "换羽")
        ):
            rank += 3
        rank -= low_signal_penalty // 12
        if rank == 0:
            continue
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
    limit = 2 if focus in {"diagnosis", "why", "guidance", "risk"} else 1
    return [item for _, item in supplemented[:limit]]


def _question_needs_multiple_direct_matches(question: str, focus: str) -> bool:
    if focus == "comparison":
        return True
    if "分别" in question and focus in {"definition", "scope", "guidance"}:
        return True
    if _question_target_has_multiple_entities(question) and focus in {
        "definition",
        "guidance",
        "open",
        "scope",
        "why",
    }:
        return True
    if _question_has_marker(question, _LOCAL_COMBINED_REASONING_MARKERS) and _question_target_has_multiple_entities(question):
        return True
    return False


def _structured_target_excess_penalty(question: str, candidate: dict[str, Any]) -> int:
    lowered = question.lower()
    target_hint = _question_target_hint(question)
    if not target_hint:
        return 0
    normalized_hint = _normalize_local_surface(target_hint)
    normalized_name = _normalize_local_surface(str(candidate.get("name", "")).strip())
    if not normalized_hint or not normalized_name or normalized_hint not in normalized_name:
        return 0

    penalty = 0
    for canonical_surface, triggers in _LOCAL_STRUCTURED_SURFACE_GROUPS.items():
        if not any(trigger in lowered for trigger in triggers):
            continue
        surface_norm = _normalize_local_surface(canonical_surface)
        if not surface_norm or surface_norm not in normalized_name:
            continue
        reduced = normalized_name.replace(normalized_hint, "", 1)
        reduced = reduced.replace(surface_norm, "", 1)
        if reduced:
            penalty = max(penalty, min(len(reduced) * 6, 48))
    return penalty


def _local_structured_surface_bonus(question: str, candidate: dict[str, Any]) -> int:
    lowered = question.lower()
    surfaces = [str(candidate.get("name", "")).strip(), *(candidate.get("matched_terms", []) or [])]
    bonus = 0
    for canonical_surface, triggers in _LOCAL_STRUCTURED_SURFACE_GROUPS.items():
        if not any(trigger in lowered for trigger in triggers):
            continue
        if any(canonical_surface in surface for surface in surfaces):
            bonus = max(bonus, 56)
    return bonus


def _local_structured_base_term_penalty(question: str, candidate: dict[str, Any]) -> int:
    lowered = question.lower()
    surfaces = [str(candidate.get("name", "")).strip(), *(candidate.get("matched_terms", []) or [])]
    normalized_name = _normalize_local_surface(str(candidate.get("name", "")).strip())
    if not normalized_name:
        return 0
    penalty = 0
    normalized_question = _normalize_local_surface(question)
    for canonical_surface, triggers in _LOCAL_STRUCTURED_SURFACE_GROUPS.items():
        if not any(trigger in lowered for trigger in triggers):
            continue
        if any(canonical_surface in surface for surface in surfaces):
            continue
        if normalized_name in normalized_question:
            penalty = max(penalty, 136 if len(normalized_name) <= 6 else 112)
    return penalty


def _local_artifact_wrapper_penalty(question: str, candidate: dict[str, Any]) -> int:
    lowered = question.lower()
    if not any(trigger in lowered for triggers in _LOCAL_STRUCTURED_SURFACE_GROUPS.values() for trigger in triggers):
        return 0
    name = str(candidate.get("name", "")).strip()
    if any(name.endswith(suffix) for suffix in _LOCAL_ARTIFACT_WRAPPER_SUFFIXES):
        return 42
    return 0


def _direct_candidate_sort_key(
    question: str,
    candidate: dict[str, Any],
) -> tuple[int, int, int, int, float, int, int]:
    target_hint = _question_target_hint(question)
    target_priority, target_specificity = _candidate_target_priority(candidate, target_hint)
    structured_bonus = _local_structured_surface_bonus(question, candidate)
    wrapper_penalty = _local_artifact_wrapper_penalty(question, candidate)
    base_term_penalty = _local_structured_base_term_penalty(question, candidate)
    excess_penalty = _structured_target_excess_penalty(question, candidate)
    low_signal_penalty = _low_signal_candidate_penalty(candidate)
    score = -float(candidate.get("score", 0) or 0)
    match_index = _direct_candidate_match_index(question, candidate)
    if match_index < 0:
        match_index = 10**6
    name_length = -len(str(candidate.get("name", "")).strip())
    return (
        target_priority,
        -target_specificity,
        -structured_bonus,
        wrapper_penalty + base_term_penalty + excess_penalty + low_signal_penalty,
        score,
        match_index,
        name_length,
    )


def _question_target_hint(question: str) -> str:
    normalized = question.strip().strip("？?")
    if not normalized:
        return ""

    for delimiter in ("，", ",", "：", ":"):
        if delimiter not in normalized:
            continue
        tail = normalized.rsplit(delimiter, 1)[-1]
        extracted = _trim_target_phrase(tail)
        if extracted:
            return extracted

    for marker in ("中定义", "中，", "中", "里定义", "里"):
        if marker in normalized:
            head = normalized.split(marker, 1)[0]
            extracted = _trim_target_phrase(head)
            if extracted:
                return extracted
    return _trim_target_phrase(normalized)


def _trim_target_phrase(text: str) -> str:
    candidate = text.strip()
    for prefix in (
        "什么是",
        "什么叫",
        "请问",
        "为什么",
        "如何判断",
        "怎么判断",
        "怎样判断",
        "如何评估",
        "怎么评估",
        "怎样评估",
        "如果",
        "从",
        "根据",
        "结合",
        "综合",
        "对",
        "按",
        "基于",
    ):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix):]
    for marker in ("目前", "现在"):
        if marker in candidate:
            prefix = candidate.split(marker, 1)[0].strip()
            if len(prefix) >= 2:
                candidate = prefix
                break
    for marker in (
        "可能是什么问题",
        "可能遇到哪些类型的故障",
        "的范围",
        "的区间",
        "的安全运行区间是如何定义的",
        "的安全运行区间",
        "的单位",
        "的执行周期",
        "的周期",
        "的类型",
        "的部署策略",
        "的路由策略",
        "的条件",
        "的触发条件",
        "在什么条件下会决定",
        "在什么条件下会",
        "在什么条件下",
        "在什么情况下会",
        "在什么情况下",
        "什么条件下会决定",
        "什么条件下会",
        "什么条件下",
        "什么情况下会",
        "什么情况下",
        "会经历哪些阶段",
        "会经历什么阶段",
        "经历哪些阶段",
        "经历什么阶段",
        "的数据质量",
        "的质量",
        "的最大缺陷",
        "的主要缺陷",
        "的完整流程",
        "是什么",
        "是什么意思",
        "有哪些",
        "多少",
        "分别指什么",
        "负责什么",
        "需要完成哪些准备",
        "需要哪些准备",
        "如何配合工作",
        "如何配合",
        "如何协作",
        "有什么关系",
        "之间有什么关系",
        "之间是什么关系",
        "需要经历哪些阶段",
        "应该采取哪些应对策略",
        "应该采取哪些策略",
        "衡量什么",
        "如何避免",
        "能完全避免检测",
        "能完全避免",
        "能否避免",
        "是否能",
        "是否可以",
    ):
        if marker in candidate:
            candidate = candidate.split(marker, 1)[0]
    return candidate.strip(" ，。；：:").strip()


def _candidate_target_priority(candidate: dict[str, Any], target_hint: str) -> tuple[int, int]:
    if not target_hint:
        return 3, 0
    normalized_hint = _normalize_local_surface(target_hint)
    projected_hint = _projected_local_target_surface(target_hint)
    best_rank = 3
    best_specificity = 0
    for raw in [candidate.get("name", ""), *(candidate.get("matched_terms", []) or [])]:
        normalized = _normalize_local_surface(str(raw))
        if not normalized:
            continue
        if projected_hint and normalized == projected_hint and projected_hint != normalized_hint:
            return 0, len(normalized_hint) + 8
        if normalized == normalized_hint:
            return 0, len(normalized)
        if normalized_hint and normalized_hint in normalized:
            if len(normalized) > best_specificity or best_rank > 1:
                best_rank = 1
                best_specificity = len(normalized)
            continue
        if normalized and normalized in normalized_hint:
            rank = 1 if len(normalized) >= max(4, len(normalized_hint) // 2) else 2
            if rank < best_rank or (rank == best_rank and len(normalized) > best_specificity):
                best_rank = rank
                best_specificity = len(normalized)
    return best_rank, best_specificity


def _projected_local_target_surface(text: str) -> str:
    projected = str(text or "").strip()
    if not projected:
        return ""
    for prefix in ("管理", "完整", "当前", "默认", "整体", "全系统", "全局"):
        if projected.startswith(prefix) and len(projected) > len(prefix) + 1:
            projected = projected[len(prefix):].strip()
    projected = projected.replace("完整", "").replace("当前", "").replace("默认", "")
    projected = projected.replace("的", "")
    changed = True
    while changed:
        changed = False
        for suffix in _LOCAL_QUERYABLE_TERM_SUFFIXES:
            if projected.endswith(suffix) and len(projected) > len(suffix) + 1:
                projected = projected[: -len(suffix)].strip()
                changed = True
                break
    return _normalize_local_surface(projected)


def _question_benefits_from_supporting_candidate(question: str, focus: str) -> bool:
    if focus in {"why", "comparison", "diagnosis", "risk"}:
        return True
    if _question_has_marker(question, _LOCAL_COMBINED_REASONING_MARKERS):
        return True
    if focus == "guidance" and _question_has_marker(
        question,
        (
            "流程",
            "步骤",
            "阶段",
            "配合",
            "协作",
            "经历",
            "如何",
            "怎么",
            "怎样",
            "判断",
        ),
    ):
        return True
    if _question_has_marker(
        question,
        (
            "触发条件",
            "启动条件",
            "在什么条件下",
            "什么条件下",
            "在什么情况下",
            "什么情况下",
            "质量",
            "数据质量",
            "部署策略",
            "是否",
            "能完全",
            "完全避免",
        ),
    ):
        return True
    return any(marker in question for marker in ("谁", "权限", "角色", "负责", "主持"))


def _direct_candidate_match_index(question: str, candidate: dict[str, Any]) -> int:
    question_lower = question.lower()
    question_terms = {item.lower() for item in _local_question_keywords(question)}
    positions: list[int] = []
    for term in _candidate_direct_terms(candidate):
        if term not in question_terms:
            continue
        index = question_lower.find(term)
        if index >= 0:
            positions.append(index)
    return min(positions) if positions else -1


def _candidate_direct_terms(candidate: dict[str, Any]) -> list[str]:
    direct_terms: list[str] = []
    for raw in [candidate.get("name", ""), *(candidate.get("matched_terms", []) or [])]:
        lowered = str(raw).strip().lower()
        if lowered and lowered not in direct_terms:
            direct_terms.append(lowered)
    return direct_terms


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
    if question_mode == "risk":
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


_STRUCTURED_OUTPUT_NOTICE_PATTERN = re.compile(
    r"^The response has been provided as a structured JSON object via the StructuredOutput tool\.?\s*",
    re.IGNORECASE,
)
_STRUCTURED_SUMMARY_SOURCE_LABELS = {
    "key sources",
    "sources",
    "source",
    "关键来源",
    "来源",
    "参考来源",
}
_STRUCTURED_SUMMARY_CONFIDENCE_LABELS = {
    "confidence",
    "置信度",
    "可信度",
}


def _normalize_structured_summary_label(label: str) -> str:
    normalized = re.sub(r"[*`_]+", "", str(label or "")).strip().lower()
    normalized = normalized.replace("：", ":")
    return normalized


def _parse_structured_summary_sources(
    value: str,
    *,
    inventory_data: dict[str, Any],
) -> list[str]:
    docs = inventory_data.get("docs", {}) or {}
    candidates = [
        re.sub(r"^[•*\-]+", "", item).strip().strip(".。")
        for item in re.split(r"[，,、|]+", str(value or ""))
    ]
    sources: list[str] = []
    for candidate in candidates:
        if candidate and candidate in docs and candidate not in sources:
            sources.append(candidate)
    return sources


def _parse_structured_summary_confidence(value: str) -> str:
    lowered = str(value or "").lower()
    for label in ("high", "medium", "low"):
        if re.search(rf"\b{label}\b", lowered):
            return label
    zh_map = {
        "高": "high",
        "中": "medium",
        "低": "low",
    }
    for marker, label in zh_map.items():
        if marker in str(value or ""):
            return label
    return ""


def _recover_structured_summary_payload(
    raw_output: str,
    *,
    question: str,
    context: dict[str, Any],
    inventory_data: dict[str, Any],
) -> dict[str, Any] | None:
    text = str(raw_output or "").strip()
    lowered = text.lower()
    if "structuredoutput tool" not in lowered and "structured json object" not in lowered:
        return None

    answer_lines: list[str] = []
    sources: list[str] = []
    confidence = ""

    for raw_line in text.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        line = _STRUCTURED_OUTPUT_NOTICE_PATTERN.sub("", line).strip()
        if not line:
            continue

        bullet = re.sub(r"^[-•]\s*", "", line).strip()
        match = re.match(r"\*\*(.+?)\*\*\s*[:：]\s*(.+)", bullet)
        if match:
            raw_label = match.group(1).strip()
            label = _normalize_structured_summary_label(raw_label)
            value = match.group(2).strip()
            if label in _STRUCTURED_SUMMARY_SOURCE_LABELS:
                sources = _parse_structured_summary_sources(value, inventory_data=inventory_data)
                continue
            if label in _STRUCTURED_SUMMARY_CONFIDENCE_LABELS:
                confidence = _parse_structured_summary_confidence(value)
                continue
            answer_lines.append(f"- {raw_label}: {value}")
            continue

        answer_lines.append(bullet)

    answer_text = "\n".join(answer_lines).strip()
    if not answer_text:
        return None

    payload = {
        "answer": answer_text,
        "sources": sources,
        "confidence": confidence or "medium",
        "exploration_summary": {
            "entries_scanned": len(inventory_data.get("entries", [])),
            "entries_read": len(sources),
            "links_followed": max(
                0,
                len(context.get("expanded_candidates", [])) - len(context.get("initial_shortlist", [])),
            ),
            "mode": "structured-output-summary",
        },
        "gaps": [],
        "contradictions": [],
    }
    validation = validate_answer(payload, inventory_data=inventory_data)
    if validation["valid"]:
        return validation["normalized"]

    return _build_local_explore_answer(
        question,
        inventory_data=inventory_data,
        context=context,
        mode_label="structured-output-summary-fallback",
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
    emit: ExploreEventEmitter | None = None,
) -> dict[str, Any]:
    retry_reason = None
    for attempt in range(1, 3):
        _emit_explore_event(
            emit,
            "status",
            f"Starting agent attempt {attempt}/2.",
            attempt=attempt,
        )
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
            emit=emit,
            attempt=attempt,
        )

        try:
            parsed_output = _parse_cli_json(raw_output)
        except RuntimeError:
            recovered = _recover_structured_summary_payload(
                raw_output,
                question=question,
                context=context,
                inventory_data=inventory_data,
            )
            if recovered is not None:
                _emit_explore_event(
                    emit,
                    "status",
                    (
                        "Attempt "
                        f"{attempt} returned a structured-output summary; recovered a valid payload."
                    ),
                    attempt=attempt,
                    mode=recovered.get("exploration_summary", {}).get("mode", ""),
                )
                return recovered
            retry_reason = "response was not a valid JSON object"
            _emit_explore_event(
                emit,
                "retry",
                f"Attempt {attempt} returned non-JSON output; retrying.",
                attempt=attempt,
                reason=retry_reason,
                raw_excerpt=_trim_explore_excerpt(raw_output),
            )
            continue

        validation = validate_answer(parsed_output, inventory_data=inventory_data)
        if validation["valid"]:
            _emit_explore_event(
                emit,
                "status",
                f"Attempt {attempt} produced a valid explore payload.",
                attempt=attempt,
                confidence=validation["normalized"].get("confidence", ""),
            )
            return validation["normalized"]
        retry_reason = "; ".join(validation["errors"])
        _emit_explore_event(
            emit,
            "retry",
            f"Attempt {attempt} returned an invalid explore payload; retrying.",
            attempt=attempt,
            reason=retry_reason,
            raw_excerpt=_trim_explore_excerpt(raw_output),
        )

    raise RuntimeError(f"Explore runtime returned invalid JSON: {retry_reason}")


def _run_explore_cli(
    *,
    prompt: str,
    skill_body: str,
    project_root: Path,
    skill_label: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    emit: ExploreEventEmitter | None = None,
    attempt: int | None = None,
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
        _emit_explore_event(
            emit,
            "command",
            _summarize_explore_command(invocation, cwd=project_root),
            attempt=attempt,
            backend=invocation.backend,
            cwd=str(project_root),
            prompt_file=str(prompt_file),
            payload_file=str(payload_file),
            skill_file=str(skill_file),
            command_summary=_summarize_explore_command(invocation, cwd=project_root),
        )
        try:
            process = subprocess.Popen(
                invocation.command,
                stdin=subprocess.PIPE if invocation.stdin_data is not None else None,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(project_root),
                bufsize=1,
            )
        except FileNotFoundError as exc:
            backend = settings["agent"]["backend"]
            raise RuntimeError(
                f"Explore runtime CLI is unavailable for backend {backend}: "
                f"{exc.filename or invocation.command[0]}"
            ) from exc

        if invocation.stdin_data is not None and process.stdin is not None:
            try:
                process.stdin.write(invocation.stdin_data)
            except BrokenPipeError:
                pass
            finally:
                process.stdin.close()
            _emit_explore_event(
                emit,
                "status",
                "Prompt streamed to agent CLI.",
                attempt=attempt,
                prompt_chars=len(invocation.stdin_data),
            )

        stdout_text, stderr_text = _stream_explore_process_output(
            process,
            timeout_seconds=timeout_seconds,
            emit=emit,
            attempt=attempt,
        )

        if process.returncode != 0:
            stderr = stderr_text.strip()
            stdout = stdout_text.strip()
            detail = stderr or stdout or f"exit code {process.returncode}"
            raise RuntimeError(f"Explore runtime CLI failed: {detail}")

        file_output = ""
        if invocation.output_file is not None and invocation.output_file.exists():
            file_output = invocation.output_file.read_text(encoding="utf-8").strip()
            if file_output and file_output != stdout_text.strip():
                _emit_explore_event(
                    emit,
                    "cli-output",
                    file_output,
                    attempt=attempt,
                    stream="assistant-file",
                )

        output = collect_output(invocation, stdout=stdout_text, stderr=stderr_text)
        if not output:
            raise RuntimeError("Explore runtime CLI returned no output.")
        return output


def _stream_explore_process_output(
    process: subprocess.Popen[str],
    *,
    timeout_seconds: int,
    emit: ExploreEventEmitter | None = None,
    attempt: int | None = None,
) -> tuple[str, str]:
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Explore runtime CLI did not expose stdout/stderr pipes.")

    chunks: dict[str, list[str]] = {"stdout": [], "stderr": []}
    stream_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()

    def _reader(stream_name: str, pipe) -> None:
        try:
            for chunk in iter(pipe.readline, ""):
                stream_queue.put((stream_name, chunk))
        finally:
            pipe.close()
            stream_queue.put((stream_name, None))

    stdout_thread = threading.Thread(
        target=_reader,
        args=("stdout", process.stdout),
        daemon=True,
        name="sediment-explore-stdout",
    )
    stderr_thread = threading.Thread(
        target=_reader,
        args=("stderr", process.stderr),
        daemon=True,
        name="sediment-explore-stderr",
    )
    stdout_thread.start()
    stderr_thread.start()

    deadline = time.monotonic() + timeout_seconds
    last_heartbeat = time.monotonic()
    completed_readers = 0

    while completed_readers < 2:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            process.kill()
            process.wait(timeout=5)
            raise RuntimeError(
                f"Explore runtime timed out after {timeout_seconds} seconds."
            )
        try:
            stream_name, chunk = stream_queue.get(timeout=min(0.5, remaining))
        except queue.Empty:
            if process.poll() is None and time.monotonic() - last_heartbeat >= 5:
                _emit_explore_event(
                    emit,
                    "heartbeat",
                    "Agent CLI is still running and has not emitted a new line yet.",
                    attempt=attempt,
                )
                last_heartbeat = time.monotonic()
            continue

        if chunk is None:
            completed_readers += 1
            continue

        chunks[stream_name].append(chunk)
        _emit_explore_event(
            emit,
            "cli-output",
            chunk.rstrip("\n"),
            attempt=attempt,
            stream=stream_name,
        )

    process.wait(timeout=5)
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    return "".join(chunks["stdout"]), "".join(chunks["stderr"])


def _parse_cli_json(raw_output: str) -> dict[str, Any]:
    # Strip common non-JSON wrappers that LLMs often emit
    cleaned = raw_output.strip()

    # Remove XML-style thinking tags (e.g. <thinking>...</thinking>)
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.DOTALL).strip()

    # Remove markdown thinking blocks (e.g. **Thinking:** ... or *Thoughts:* ...)
    cleaned = re.sub(r"\*\*Thinking:?\*\*.*?(?=\{|\Z)", "", cleaned, flags=re.DOTALL).strip()
    cleaned = re.sub(r"\*Thoughts?:\*.*?(?=\{|\Z)", "", cleaned, flags=re.DOTALL).strip()

    # Remove leading prose before the first JSON object
    # Common patterns: "Here is the answer:", "Sure!", "Based on the context:", etc.
    brace_start = cleaned.find("{")
    if brace_start > 0:
        # Only strip if there's likely preamble text (not just whitespace)
        preamble = cleaned[:brace_start].strip()
        if preamble and len(preamble) > 2:
            cleaned = cleaned[brace_start:]

    candidates = [cleaned]

    # Try fenced code blocks
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())

    # Also try any ``` without language specifier
    fenced_plain = re.search(r"```\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced_plain:
        candidates.append(fenced_plain.group(1).strip())

    # Extract from first { to last } (handles trailing text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(cleaned[start : end + 1].strip())

    # Try the original raw output directly as a fallback
    candidates.append(raw_output.strip())

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


def _stream_response(body, *, media_type: str, status: int = 200):
    from starlette.responses import StreamingResponse

    return StreamingResponse(body, status_code=status, media_type=media_type)


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


def _config_raw_text() -> str:
    if CONFIG_PATH.exists():
        return CONFIG_PATH.read_text(encoding="utf-8")
    return yaml.safe_dump(_settings().get("raw") or {}, allow_unicode=True, sort_keys=False)


def _yaml_friendly(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _admin_settings_payload(store: PlatformStore) -> dict[str, Any]:
    effective = _settings()
    return {
        "config_path": str(CONFIG_PATH.resolve()),
        "raw_text": _config_raw_text(),
        "effective_config_text": yaml.safe_dump(
            _yaml_friendly(effective),
            allow_unicode=True,
            sort_keys=False,
        ),
        "status": _system_status_payload(store),
    }


def _reload_runtime_settings() -> None:
    clear_settings_cache()
    refresh_runtime_state()


def _schedule_admin_restart() -> dict[str, Any]:
    from sediment.cli import daemon_status

    status = daemon_status()
    if not status.get("running"):
        raise RuntimeError("restart is only available when Sediment runs as a managed daemon")

    source_root = str(Path(__file__).resolve().parents[1])
    python_path = os.environ.get("PYTHONPATH", "").strip()
    if python_path:
        python_path = f"{source_root}{os.pathsep}{python_path}"
    else:
        python_path = source_root
    restart_command = [
        sys.executable,
        "-m",
        "sediment.cli",
        "--config",
        str(CONFIG_PATH.resolve()),
        "server",
        "restart",
        "--skip-checks",
    ]
    wrapper = [
        sys.executable,
        "-c",
        (
            "import subprocess, sys, time; "
            "time.sleep(0.75); "
            "subprocess.run(sys.argv[1:], check=False)"
        ),
        *restart_command,
    ]
    log_path = _platform_paths()["log_dir"] / "platform.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            wrapper,
            cwd=str(INSTANCE_ROOT),
            env={**os.environ, "PYTHONPATH": python_path},
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    SERVER_LOGGER.info(
        "admin.restart_scheduled",
        "Scheduled a managed daemon restart from the admin surface.",
        details={
            "config_path": CONFIG_PATH.resolve(),
            "log_path": log_path,
            "command": restart_command,
        },
    )
    return {
        "scheduled": True,
        "config_path": str(CONFIG_PATH.resolve()),
        "message": "restart scheduled",
    }


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
        )
    )


async def _portal_tutorial_page(request):
    locale = _request_locale(request)
    return _html_response(
        portal_html(
            knowledge_name=KNOWLEDGE_NAME,
            instance_name=INSTANCE_NAME,
            locale=locale,
            page="tutorial",
            mcp_endpoint=_tutorial_mcp_endpoint(request),
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


async def _skill_download(request):
    from starlette.responses import Response

    skill_name = str(request.path_params["skill_name"]).strip()
    if skill_name != _tutorial_skill_slug():
        return _text_response("skill not found", media_type="text/plain; charset=utf-8", status=404)
    return Response(
        _tutorial_skill_text(_request_locale(request)),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_tutorial_skill_download_name()}"'},
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


async def _admin_files_page(request):
    return await _admin_section_page(request, section="files")


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
        public_base_url=PUBLIC_BASE_URL,
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


async def _api_admin_ingest_document(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    actor = _actor_from_request(request)
    body = await _request_json_or_empty(request)
    submitter_name = str(body.get("submitter_name", "")).strip() or str(
        actor.get("name", "")
    ).strip()
    try:
        decoded_files = _decode_uploaded_files(body.get("files") or [])
        submission = submit_document_request(
            store=_platform_store(),
            uploads_dir=_platform_paths()["uploads_dir"],
            filename=str(body.get("filename", "")),
            mime_type=str(body.get("mime_type", "")),
            file_bytes=b"",
            uploads=decoded_files,
            submitter_name=submitter_name,
            submitter_ip=detect_submitter_ip(
                dict(request.headers),
                request.client.host if request.client else None,
                trust_proxy_headers=TRUST_PROXY_HEADERS,
                trusted_proxy_cidrs=TRUSTED_PROXY_CIDRS,
            ),
            submitter_user_id=str(actor.get("id", "")).strip() or None,
            notes="admin ingest upload",
            rate_limit_count=1_000_000,
            rate_limit_window_seconds=1,
            max_upload_bytes=MAX_UPLOAD_BYTES,
            dedupe_window_seconds=SUBMISSION_DEDUPE_WINDOW_SECONDS,
        )
        job = enqueue_ingest_job(
            store=_platform_store(),
            submission_id=submission["id"],
            actor_name=str(actor.get("name", "")),
            actor_id=str(actor.get("id", "")) or None,
            actor_role=str(actor.get("role", "")),
            max_attempts=JOB_MAX_ATTEMPTS,
        )
    except FileExistsError as exc:
        return _json_response({"error": str(exc)}, status=409)
    except (ValueError, binascii.Error) as exc:
        return _json_response({"error": str(exc)}, status=400)
    if RUN_JOBS_IN_PROCESS:
        _agent_runner().submit(job["id"])
    return _json_response({"submission": submission, "job": job}, status=202)


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


async def _api_admin_settings_config(request):
    guard = await _admin_guard(request, allowed_roles=("owner",))
    if guard:
        return guard
    return _json_response(_admin_settings_payload(_platform_store()))


async def _api_admin_settings_save(request):
    guard = await _admin_guard(request, allowed_roles=("owner",))
    if guard:
        return guard
    actor = _actor_from_request(request)
    body = await _request_json_or_empty(request)
    raw_text = str(body.get("raw_text", "")).strip()
    if not raw_text:
        return _json_response({"error": "raw_text must not be empty"}, status=400)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        suffix=".yaml",
        dir=CONFIG_PATH.parent,
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(raw_text if raw_text.endswith("\n") else f"{raw_text}\n")
    try:
        validated = load_settings_for_path(temp_path, argv=[])
        if not isinstance(validated, dict):
            raise RuntimeError("config must produce a mapping")
    except (RuntimeError, ValueError, yaml.YAMLError) as exc:
        temp_path.unlink(missing_ok=True)
        return _json_response({"error": str(exc)}, status=400)
    temp_path.unlink(missing_ok=True)
    CONFIG_PATH.write_text(
        raw_text if raw_text.endswith("\n") else f"{raw_text}\n",
        encoding="utf-8",
    )
    _reload_runtime_settings()
    _platform_store().add_audit_log(
        actor_name=str(actor.get("name", "")),
        actor_id=str(actor.get("id", "")) or None,
        actor_role=str(actor.get("role", "")),
        action="settings.update",
        target_type="config",
        target_id=str(CONFIG_PATH.resolve()),
        details={"public_base_url": _settings()["server"].get("public_base_url", "")},
    )
    return _json_response(_admin_settings_payload(_platform_store()))


async def _api_admin_settings_restart(request):
    guard = await _admin_guard(request, allowed_roles=("owner",))
    if guard:
        return guard
    actor = _actor_from_request(request)
    try:
        payload = _schedule_admin_restart()
    except RuntimeError as exc:
        return _json_response({"error": str(exc)}, status=400)
    _platform_store().add_audit_log(
        actor_name=str(actor.get("name", "")),
        actor_id=str(actor.get("id", "")) or None,
        actor_role=str(actor.get("role", "")),
        action="settings.restart",
        target_type="config",
        target_id=str(CONFIG_PATH.resolve()),
        details={"scheduled": True},
    )
    return _json_response(payload, status=202)


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


async def _api_admin_kb_documents(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    return _json_response(kb_document_browser_payload(KB_PATH))


async def _api_admin_files(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    return _json_response(kb_file_management_payload(KB_PATH))


async def _api_admin_files_suggest(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    query = str(request.query_params.get("q", "")).strip()
    return _json_response({"suggestions": search_kb_file_suggestions(KB_PATH, query)})


async def _api_admin_explore(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    body = await _request_json_or_empty(request)
    question = str(body.get("question", "")).strip()
    if not question:
        return _json_response({"error": "question must not be empty"}, status=400)
    try:
        return _json_response(
            answer_question_agent_only(question, KB_PATH, _PROJECT_ROOT)
        )
    except RuntimeError as exc:
        return _json_response({"error": str(exc)}, status=502)


async def _api_admin_explore_live(request):
    guard = await _admin_guard(request)
    if guard:
        return guard
    body = await _request_json_or_empty(request)
    question = str(body.get("question", "")).strip()
    if not question:
        return _json_response({"error": "question must not be empty"}, status=400)

    async def _stream():
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue[str | None] = asyncio.Queue()

        def emit(event: dict[str, Any]) -> None:
            line = json.dumps(event, ensure_ascii=False)
            loop.call_soon_threadsafe(event_queue.put_nowait, line)

        def worker() -> None:
            try:
                result = answer_question_agent_only(
                    question,
                    KB_PATH,
                    _PROJECT_ROOT,
                    emit=emit,
                )
                emit({"type": "result", "payload": result, "message": "Explore completed."})
                emit({"type": "done", "ok": True, "message": "Explore stream closed."})
            except RuntimeError as exc:
                emit({"type": "error", "message": str(exc)})
                emit({"type": "done", "ok": False, "message": "Explore stream closed."})
            finally:
                loop.call_soon_threadsafe(event_queue.put_nowait, None)

        threading.Thread(
            target=worker,
            daemon=True,
            name="sediment-admin-explore-live",
        ).start()

        while True:
            line = await event_queue.get()
            if line is None:
                break
            yield line + "\n"

    return _stream_response(_stream(), media_type="application/x-ndjson")


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
                    # Quartz graph rendering uses Pixi's runtime, which currently needs
                    # script evaluation enabled in the hosted Quartz route.
                    headers.setdefault(
                        "Content-Security-Policy",
                        "default-src 'self'; "
                        "img-src 'self' data: blob: https:; "
                        "style-src 'self' 'unsafe-inline' https:; "
                        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https: blob:; "
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


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", "")).strip() or "/"
        if path.startswith("/ui-assets/") or path.startswith("/quartz") or path == "/healthz":
            await self.app(scope, receive, send)
            return

        request_id = hashlib.sha1(
            f"{time.time_ns()}:{path}:{id(scope)}".encode("utf-8")
        ).hexdigest()[:12]
        scope["sediment.request_id"] = request_id
        method = str(scope.get("method", "GET")).upper()
        client = scope.get("client") or ("unknown", 0)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                from starlette.datastructures import MutableHeaders

                status_code = int(message.get("status", 500))
                headers = MutableHeaders(raw=message["headers"])
                headers.setdefault("X-Request-ID", request_id)
            await send(message)

        try:
            with bind_log_context(request_id=request_id):
                await self.app(scope, receive, send_wrapper)
        except Exception as exc:  # noqa: BLE001
            HTTP_LOGGER.error(
                "request.failed",
                "HTTP request raised an exception.",
                error=exc,
                request_id=request_id,
                details={
                    "method": method,
                    "path": path,
                    "client_ip": client[0],
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise

        HTTP_LOGGER.log(
            "ERROR" if status_code >= 500 else ("WARNING" if status_code >= 400 else "INFO"),
            "request.completed",
            "HTTP request completed.",
            request_id=request_id,
            details={
                "method": method,
                "path": path,
                "status_code": status_code,
                "client_ip": client[0],
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )


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
        Route("/tutorial", _portal_tutorial_page),
        Route("/entries/{name:str}", _portal_entry_page),
        Route("/submit", _portal_submit_page),
        Route("/downloads/skills/{skill_name:str}", _skill_download),
        Route("/portal/graph-view", _portal_graph_page),
        Route("/admin", _admin_page),
        Route("/admin/overview", _admin_overview_page),
        Route("/admin/kb", _admin_kb_page),
        Route("/admin/files", _admin_files_page),
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
        Route("/api/admin/ingest/document", _api_admin_ingest_document, methods=["POST"]),
        Route("/api/admin/jobs", _api_admin_jobs),
        Route("/api/admin/jobs/{job_id:str}", _api_admin_job_detail),
        Route("/api/admin/jobs/{job_id:str}/retry", _api_admin_job_retry, methods=["POST"]),
        Route("/api/admin/jobs/{job_id:str}/cancel", _api_admin_job_cancel, methods=["POST"]),
        Route("/api/admin/tidy", _api_admin_tidy, methods=["POST"]),
        Route("/api/admin/kb/documents", _api_admin_kb_documents, methods=["GET"]),
        Route("/api/admin/files", _api_admin_files, methods=["GET"]),
        Route("/api/admin/files/suggest", _api_admin_files_suggest, methods=["GET"]),
        Route("/api/admin/reviews", _api_admin_reviews),
        Route("/api/admin/reviews/{review_id:str}", _api_admin_review_detail),
        Route("/api/admin/reviews/{review_id:str}/approve", _api_admin_review_approve, methods=["POST"]),
        Route("/api/admin/reviews/{review_id:str}/reject", _api_admin_review_reject, methods=["POST"]),
        Route("/api/admin/entries/{name:str}", _api_admin_entry_detail, methods=["GET"]),
        Route("/api/admin/entries/{name:str}", _api_admin_entry_save, methods=["PUT"]),
        Route("/api/admin/explore", _api_admin_explore, methods=["POST"]),
        Route("/api/admin/explore/live", _api_admin_explore_live, methods=["POST"]),
        Route("/api/admin/settings/config", _api_admin_settings_config, methods=["GET"]),
        Route("/api/admin/settings/config", _api_admin_settings_save, methods=["PUT"]),
        Route("/api/admin/settings/restart", _api_admin_settings_restart, methods=["POST"]),
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
        middleware=[
            Middleware(RequestLoggingMiddleware),
            Middleware(SecurityHeadersMiddleware),
        ],
        routes=routes,
    )


def main(argv: list[str] | None = None):
    import uvicorn

    refresh_runtime_state()
    starlette_app = create_starlette_app()
    SERVER_LOGGER.info(
        "startup.ready",
        "Sediment MCP server is starting.",
        details={
            "listen_url": f"http://{HOST}:{PORT}",
            "portal_url": f"http://{HOST}:{PORT}/",
            "search_url": f"http://{HOST}:{PORT}/search",
            "submit_url": f"http://{HOST}:{PORT}/submit",
            "quartz_url": f"http://{HOST}:{PORT}/quartz/",
            "admin_url": f"http://{HOST}:{PORT}/admin/overview",
            "health_url": f"http://{HOST}:{PORT}/healthz",
            "sse_endpoint": f"http://{HOST}:{PORT}{SSE_ENDPOINT}",
            "post_endpoint": f"http://{HOST}:{PORT}{SSE_ENDPOINT}",
            "run_jobs_in_process": RUN_JOBS_IN_PROCESS,
        },
    )
    uvicorn.run(starlette_app, host=HOST, port=PORT, access_log=False, log_level="warning")


if __name__ == "__main__":
    raise SystemExit(main())
