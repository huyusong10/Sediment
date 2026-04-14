from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from starlette.applications import Starlette


@dataclass(slots=True)
class ServerHttpContext:
    kb_path: Path
    instance_name: str
    instance_root: Path
    knowledge_name: str
    config_path: Path
    host: str
    port: int
    sse_endpoint: str
    admin_session_cookie_name: str
    admin_session_ttl_seconds: int
    secure_cookies: bool
    trust_proxy_headers: bool
    trusted_proxy_cidrs: Any
    submission_rate_limit_count: int
    submission_rate_limit_window_seconds: int
    submission_dedupe_window_seconds: int
    max_text_submission_chars: int
    max_upload_bytes: int
    job_max_attempts: int
    job_stale_after_seconds: int
    run_jobs_in_process: bool
    project_root: Path
    quartz_site_dir: Path
    quartz_runtime_dir: Path
    platform_store: Callable[..., Any]
    platform_paths: Callable[..., Any]
    agent_runner: Callable[..., Any]
    request_locale: Callable[..., Any]
    path_with_locale: Callable[..., Any]
    admin_auth_required: Callable[..., Any]
    token_matches: Callable[..., Any]
    is_admin_authorized: Callable[..., Any]
    set_admin_session_cookie: Callable[..., Any]
    clear_admin_session_cookie: Callable[..., Any]
    portal_html: Callable[..., Any]
    portal_graph_html: Callable[..., Any]
    admin_login_html: Callable[..., Any]
    admin_html: Callable[..., Any]
    quartz_status: Callable[..., Any]
    build_quartz_site: Callable[..., Any]
    answer_question: Callable[..., Any]


def build_starlette_app(ctx: ServerHttpContext, *, mcp_app) -> Starlette:
    """Compatibility shim for the retired parallel HTTP layer.

    The canonical Web implementation now lives in `sediment.server.create_starlette_app`.
    This wrapper intentionally ignores the legacy context object and delegates to the
    single active implementation so routes, auth, and asset templates stay in sync.
    """

    from sediment.server import create_starlette_app

    return create_starlette_app()
