from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from sediment.control import (
    admin_overview_payload,
    apply_review_decision,
    enqueue_ingest_job,
    enqueue_tidy_job,
    review_detail_payload,
    submit_document_request,
    submit_text_request,
    system_status_payload,
)
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
    platform_store: Callable[[], PlatformStore]
    platform_paths: Callable[[], dict[str, Path]]
    agent_runner: Callable[[], Any]
    request_locale: Callable[[Any], str]
    path_with_locale: Callable[[str, str], str]
    admin_auth_required: Callable[[], bool]
    token_matches: Callable[[str], bool]
    is_admin_authorized: Callable[[Any], bool]
    set_admin_session_cookie: Callable[[Any], None]
    clear_admin_session_cookie: Callable[[Any], None]
    portal_html: Callable[..., str]
    portal_graph_html: Callable[..., str]
    admin_login_html: Callable[..., str]
    admin_html: Callable[..., str]
    quartz_status: Callable[..., dict[str, Any]]
    build_quartz_site: Callable[..., dict[str, Any]]
    answer_question: Callable[[str, Path, Path], dict[str, Any]]


def build_starlette_app(ctx: ServerHttpContext, *, mcp_app) -> Starlette:
    async def request_json_or_empty(request) -> dict[str, Any]:
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

    def json_response(payload: Any, status: int = 200):
        return JSONResponse(payload, status_code=status)

    def html_response(html: str, status: int = 200):
        return HTMLResponse(html, status_code=status)

    def redirect(url: str):
        return RedirectResponse(url)

    def decode_uploaded_files(raw_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

    def system_status_payload_for_store(store: PlatformStore) -> dict[str, Any]:
        paths = ctx.platform_paths()
        return system_status_payload(
            store=store,
            kb_path=ctx.kb_path,
            paths=paths,
            instance_name=ctx.instance_name,
            knowledge_name=ctx.knowledge_name,
            instance_root=ctx.instance_root,
            config_path=ctx.config_path,
            host=ctx.host,
            port=ctx.port,
            sse_endpoint=ctx.sse_endpoint,
            auth_required=ctx.admin_auth_required(),
            run_jobs_in_process=ctx.run_jobs_in_process,
            submission_rate_limit_count=ctx.submission_rate_limit_count,
            submission_rate_limit_window_seconds=ctx.submission_rate_limit_window_seconds,
            submission_dedupe_window_seconds=ctx.submission_dedupe_window_seconds,
            max_text_submission_chars=ctx.max_text_submission_chars,
            max_upload_bytes=ctx.max_upload_bytes,
            job_max_attempts=ctx.job_max_attempts,
            job_stale_after_seconds=ctx.job_stale_after_seconds,
            trust_proxy_headers=ctx.trust_proxy_headers,
            trusted_proxy_cidrs=[str(item) for item in ctx.trusted_proxy_cidrs],
        )

    async def admin_guard(request):
        if not ctx.is_admin_authorized(request):
            return json_response(
                {
                    "error": "admin authentication is required",
                    "auth_required": True,
                    "login_path": "/admin",
                },
                status=401,
            )
        return None

    async def portal_page(request):
        return html_response(
            ctx.portal_html(
                knowledge_name=ctx.knowledge_name,
                instance_name=ctx.instance_name,
                locale=ctx.request_locale(request),
            )
        )

    async def portal_graph_page(request):
        locale = ctx.request_locale(request)
        return html_response(
            ctx.portal_graph_html(
                knowledge_name=ctx.knowledge_name,
                instance_name=ctx.instance_name,
                locale=locale,
                quartz=ctx.quartz_status(
                    runtime_dir=ctx.quartz_runtime_dir,
                    site_dir=ctx.quartz_site_dir,
                ),
                admin_kb_path=ctx.path_with_locale("/admin/kb", locale),
            )
        )

    async def admin_page(request):
        return await admin_overview_page(request)

    async def admin_overview_page(request):
        locale = ctx.request_locale(request)
        if not ctx.is_admin_authorized(request):
            return html_response(
                ctx.admin_login_html(
                    knowledge_name=ctx.knowledge_name,
                    instance_name=ctx.instance_name,
                    locale=locale,
                    next_path=ctx.path_with_locale("/admin", locale),
                ),
                status=200,
            )
        return html_response(
            ctx.admin_html(
                knowledge_name=ctx.knowledge_name,
                instance_name=ctx.instance_name,
                locale=locale,
                section="overview",
                quartz=ctx.quartz_status(
                    runtime_dir=ctx.quartz_runtime_dir,
                    site_dir=ctx.quartz_site_dir,
                ),
            )
        )

    async def admin_kb_page(request):
        locale = ctx.request_locale(request)
        if not ctx.is_admin_authorized(request):
            return html_response(
                ctx.admin_login_html(
                    knowledge_name=ctx.knowledge_name,
                    instance_name=ctx.instance_name,
                    locale=locale,
                    next_path=ctx.path_with_locale("/admin/kb", locale),
                ),
                status=200,
            )
        return html_response(
            ctx.admin_html(
                knowledge_name=ctx.knowledge_name,
                instance_name=ctx.instance_name,
                locale=locale,
                section="kb",
                quartz=ctx.quartz_status(
                    runtime_dir=ctx.quartz_runtime_dir,
                    site_dir=ctx.quartz_site_dir,
                ),
            )
        )

    async def admin_reviews_page(request):
        locale = ctx.request_locale(request)
        if not ctx.is_admin_authorized(request):
            return html_response(
                ctx.admin_login_html(
                    knowledge_name=ctx.knowledge_name,
                    instance_name=ctx.instance_name,
                    locale=locale,
                    next_path=ctx.path_with_locale("/admin/reviews", locale),
                ),
                status=200,
            )
        return html_response(
            ctx.admin_html(
                knowledge_name=ctx.knowledge_name,
                instance_name=ctx.instance_name,
                locale=locale,
                section="reviews",
                quartz=ctx.quartz_status(
                    runtime_dir=ctx.quartz_runtime_dir,
                    site_dir=ctx.quartz_site_dir,
                ),
            )
        )

    async def root_page(request):
        return redirect("/portal")

    async def healthz(request):
        return json_response(
            {
                "status": "ok",
                "server_time": utc_now(),
                "worker_mode": "in_process" if ctx.run_jobs_in_process else "queue",
            }
        )

    async def api_portal_home(request):
        return json_response(get_portal_home(ctx.kb_path, store=ctx.platform_store()))

    async def api_portal_search(request):
        query = request.query_params.get("q", "")
        return json_response(search_kb(ctx.kb_path, query))

    async def api_portal_entry(request):
        try:
            payload = get_entry_detail(ctx.kb_path, request.path_params["name"])
        except FileNotFoundError:
            return json_response({"error": "entry not found"}, status=404)
        return json_response(payload)

    async def api_portal_graph(request):
        return json_response(graph_payload(ctx.kb_path))

    async def api_portal_submit_text(request):
        body = await request.json()
        try:
            record = submit_text_request(
                store=ctx.platform_store(),
                kb_path=ctx.kb_path,
                title=str(body.get("title", "")),
                content=str(body.get("content", "")),
                submitter_name=str(body.get("submitter_name", "")),
                submitter_ip=detect_submitter_ip(
                    dict(request.headers),
                    request.client.host if request.client else None,
                    trust_proxy_headers=ctx.trust_proxy_headers,
                    trusted_proxy_cidrs=ctx.trusted_proxy_cidrs,
                ),
                submission_type=str(body.get("submission_type", "text")),
                submitter_user_id=None,
                rate_limit_count=ctx.submission_rate_limit_count,
                rate_limit_window_seconds=ctx.submission_rate_limit_window_seconds,
                max_text_chars=ctx.max_text_submission_chars,
                dedupe_window_seconds=ctx.submission_dedupe_window_seconds,
            )
        except PermissionError as exc:
            return json_response({"error": str(exc)}, status=429)
        except FileExistsError as exc:
            return json_response({"error": str(exc)}, status=409)
        except ValueError as exc:
            return json_response({"error": str(exc)}, status=400)
        return json_response(record, status=201)

    async def api_portal_submit_document(request):
        body = await request.json()
        try:
            file_bytes = (
                base64.b64decode(str(body.get("content_base64", "")), validate=True)
                if str(body.get("content_base64", "")).strip()
                else b""
            )
            decoded_files = decode_uploaded_files(body.get("files") or [])
            record = submit_document_request(
                store=ctx.platform_store(),
                uploads_dir=ctx.platform_paths()["uploads_dir"],
                filename=str(body.get("filename", "")),
                mime_type=str(body.get("mime_type", "")),
                file_bytes=file_bytes,
                uploads=decoded_files,
                submitter_name=str(body.get("submitter_name", "")),
                submitter_ip=detect_submitter_ip(
                    dict(request.headers),
                    request.client.host if request.client else None,
                    trust_proxy_headers=ctx.trust_proxy_headers,
                    trusted_proxy_cidrs=ctx.trusted_proxy_cidrs,
                ),
                submitter_user_id=None,
                rate_limit_count=ctx.submission_rate_limit_count,
                rate_limit_window_seconds=ctx.submission_rate_limit_window_seconds,
                max_upload_bytes=ctx.max_upload_bytes,
                dedupe_window_seconds=ctx.submission_dedupe_window_seconds,
            )
        except PermissionError as exc:
            return json_response({"error": str(exc)}, status=429)
        except FileExistsError as exc:
            return json_response({"error": str(exc)}, status=409)
        except (ValueError, binascii.Error) as exc:
            return json_response({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            return json_response({"error": str(exc)}, status=400)
        return json_response(record, status=201)

    async def api_admin_session_status(request):
        return json_response(
            {
                "authenticated": ctx.is_admin_authorized(request),
                "auth_required": ctx.admin_auth_required(),
                "cookie_name": ctx.admin_session_cookie_name,
                "session_ttl_seconds": ctx.admin_session_ttl_seconds,
            }
        )

    async def api_admin_session_create(request):
        body = await request_json_or_empty(request)
        token = str(body.get("token", ""))
        if ctx.admin_auth_required() and not ctx.token_matches(token):
            return json_response({"error": "invalid admin token"}, status=401)
        response = json_response(
            {
                "authenticated": True,
                "auth_required": ctx.admin_auth_required(),
                "session_ttl_seconds": ctx.admin_session_ttl_seconds,
            }
        )
        if ctx.admin_auth_required():
            ctx.set_admin_session_cookie(response)
        ctx.platform_store().add_audit_log(
            actor_name="admin-session",
            actor_role="platform_admin",
            action="admin.session.create",
            target_type="session",
            target_id=request.client.host if request.client else "unknown",
            details={"auth_required": ctx.admin_auth_required()},
        )
        return response

    async def api_admin_session_delete(request):
        response = json_response(
            {"authenticated": False, "auth_required": ctx.admin_auth_required()}
        )
        ctx.clear_admin_session_cookie(response)
        ctx.platform_store().add_audit_log(
            actor_name="admin-session",
            actor_role="platform_admin",
            action="admin.session.delete",
            target_type="session",
            target_id=request.client.host if request.client else "unknown",
            details={"auth_required": ctx.admin_auth_required()},
        )
        return response

    async def api_admin_overview(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        return json_response(
            admin_overview_payload(
                store=ctx.platform_store(),
                kb_path=ctx.kb_path,
                stale_after_seconds=ctx.job_stale_after_seconds,
            )
        )

    async def api_admin_health_summary(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        return json_response(get_health_payload(ctx.kb_path))

    async def api_admin_health_issues(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        return json_response({"issues": build_health_issue_queue(ctx.kb_path)})

    async def api_admin_submissions(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        return json_response({"submissions": ctx.platform_store().list_submissions(limit=200)})

    async def api_admin_submission_detail(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        store = ctx.platform_store()
        submission = store.get_submission(request.path_params["submission_id"])
        if submission is None:
            return json_response({"error": "submission not found"}, status=404)
        jobs = [
            job
            for job in store.list_jobs(limit=200)
            if job.get("source_submission_id") == submission["id"]
        ]
        return json_response({"submission": submission, "jobs": jobs})

    async def api_admin_submission_triage(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        store = ctx.platform_store()
        submission_id = request.path_params["submission_id"]
        body = await request.json()
        status = str(body.get("status", "triaged"))
        submission = store.update_submission(submission_id, status=status, notes=body.get("notes"))
        if submission is None:
            return json_response({"error": "submission not found"}, status=404)
        store.add_audit_log(
            actor_name=str(body.get("actor_name", "admin")),
            actor_role="committer",
            action="submission.triage",
            target_type="submission",
            target_id=submission_id,
            details={"status": status, "notes": body.get("notes")},
        )
        return json_response(submission)

    async def api_admin_run_ingest(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        store = ctx.platform_store()
        body = await request_json_or_empty(request)
        submission_id = request.path_params["submission_id"]
        try:
            job = enqueue_ingest_job(
                store=store,
                submission_id=submission_id,
                actor_name=str(body.get("actor_name", "admin")),
                max_attempts=ctx.job_max_attempts,
            )
        except FileNotFoundError:
            return json_response({"error": "submission not found"}, status=404)
        if ctx.run_jobs_in_process:
            ctx.agent_runner().submit(job["id"])
        return json_response(job, status=202)

    async def api_admin_jobs(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        return json_response({"jobs": ctx.platform_store().list_jobs(limit=200)})

    async def api_admin_job_detail(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        job = ctx.platform_store().get_job(request.path_params["job_id"])
        if job is None:
            return json_response({"error": "job not found"}, status=404)
        return json_response(job)

    async def api_admin_job_retry(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        store = ctx.platform_store()
        body = await request_json_or_empty(request)
        try:
            job = store.retry_job(request.path_params["job_id"])
        except ValueError as exc:
            return json_response({"error": str(exc)}, status=400)
        if job is None:
            return json_response({"error": "job not found"}, status=404)
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
        if ctx.run_jobs_in_process:
            ctx.agent_runner().submit(job["id"])
        return json_response(job, status=202)

    async def api_admin_job_cancel(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        store = ctx.platform_store()
        body = await request_json_or_empty(request)
        reason = str(body.get("reason", "job cancelled by admin"))
        try:
            job = store.cancel_job(request.path_params["job_id"], reason=reason)
        except ValueError as exc:
            return json_response({"error": str(exc)}, status=400)
        if job is None:
            return json_response({"error": "job not found"}, status=404)
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
        return json_response(job)

    async def api_admin_tidy(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        body = await request.json()
        issue = body.get("issue") or {}
        job = enqueue_tidy_job(
            store=ctx.platform_store(),
            kb_path=ctx.kb_path,
            issue=issue,
            actor_name=str(body.get("actor_name", "admin")),
            max_attempts=ctx.job_max_attempts,
        )
        if ctx.run_jobs_in_process:
            ctx.agent_runner().submit(job["id"])
        return json_response(job, status=202)

    async def api_admin_reviews(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        decision = request.query_params.get("decision")
        return json_response(
            {"reviews": list_reviews_with_jobs(store=ctx.platform_store(), decision=decision)}
        )

    async def api_admin_review_detail(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        try:
            payload = review_detail_payload(ctx.platform_store(), request.path_params["review_id"])
        except FileNotFoundError:
            return json_response({"error": "review not found"}, status=404)
        return json_response(payload)

    async def api_admin_review_approve(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        body = await request.json()
        try:
            payload = apply_review_decision(
                store=ctx.platform_store(),
                kb_path=ctx.kb_path,
                review_id=request.path_params["review_id"],
                decision=str(body.get("decision", "approve")),
                reviewer_name=str(body.get("reviewer_name", "admin")),
                comment=str(body.get("comment", "")),
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            return json_response({"error": str(exc)}, status=400)
        return json_response(payload)

    async def api_admin_review_reject(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        body = await request.json()
        try:
            payload = apply_review_decision(
                store=ctx.platform_store(),
                kb_path=ctx.kb_path,
                review_id=request.path_params["review_id"],
                decision="reject",
                reviewer_name=str(body.get("reviewer_name", "admin")),
                comment=str(body.get("comment", "")),
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            return json_response({"error": str(exc)}, status=400)
        return json_response(payload)

    async def api_admin_system_status(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        return json_response(system_status_payload_for_store(ctx.platform_store()))

    async def api_admin_audit_logs(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        try:
            limit = int(request.query_params.get("limit", "50"))
        except ValueError:
            limit = 50
        return json_response({"logs": ctx.platform_store().list_audit_logs(limit=limit)})

    async def api_admin_entry_detail(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        try:
            payload = get_entry_detail(ctx.kb_path, request.path_params["name"])
        except FileNotFoundError:
            return json_response({"error": "entry not found"}, status=404)
        return json_response(payload)

    async def api_admin_entry_save(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        body = await request.json()
        try:
            payload = save_entry(
                ctx.kb_path,
                name=request.path_params["name"],
                content=str(body.get("content", "")),
                expected_hash=body.get("expected_hash"),
                actor_name=str(body.get("actor_name", "admin")),
                store=ctx.platform_store(),
            )
        except FileNotFoundError:
            return json_response({"error": "entry not found"}, status=404)
        except (RuntimeError, ValueError) as exc:
            return json_response({"error": str(exc)}, status=400)
        return json_response(payload)

    async def api_admin_explore(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        body = await request_json_or_empty(request)
        question = str(body.get("question", "")).strip()
        if not question:
            return json_response({"error": "question must not be empty"}, status=400)
        return json_response(ctx.answer_question(question, ctx.kb_path, ctx.project_root))

    async def api_admin_quartz_status(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        return json_response(
            ctx.quartz_status(runtime_dir=ctx.quartz_runtime_dir, site_dir=ctx.quartz_site_dir)
        )

    async def api_admin_quartz_build(request):
        guard = await admin_guard(request)
        if guard:
            return guard
        body = await request_json_or_empty(request)
        try:
            payload = ctx.build_quartz_site(
                kb_path=ctx.kb_path,
                runtime_dir=ctx.quartz_runtime_dir,
                site_dir=ctx.quartz_site_dir,
                knowledge_name=ctx.knowledge_name,
                locale=ctx.request_locale(request),
            )
        except RuntimeError as exc:
            return json_response({"error": str(exc)}, status=400)
        ctx.platform_store().add_audit_log(
            actor_name=str(body.get("actor_name", "admin")),
            actor_role="committer",
            action="quartz.build",
            target_type="quartz_site",
            target_id=str(ctx.quartz_site_dir),
            details={"runtime_path": str(ctx.quartz_runtime_dir)},
        )
        return json_response(payload, status=202)

    routes = [
        Route("/", root_page),
        Route("/healthz", healthz),
        Route("/portal", portal_page),
        Route("/portal/graph-view", portal_graph_page),
        Route("/admin", admin_overview_page),
        Route("/admin/kb", admin_kb_page),
        Route("/admin/reviews", admin_reviews_page),
        Route("/api/admin/session", api_admin_session_status, methods=["GET"]),
        Route("/api/admin/session", api_admin_session_create, methods=["POST"]),
        Route("/api/admin/session", api_admin_session_delete, methods=["DELETE"]),
        Route("/api/portal/home", api_portal_home),
        Route("/api/portal/search", api_portal_search),
        Route("/api/portal/entries/{name:str}", api_portal_entry),
        Route("/api/portal/graph", api_portal_graph),
        Route("/api/portal/submissions/text", api_portal_submit_text, methods=["POST"]),
        Route("/api/portal/submissions/document", api_portal_submit_document, methods=["POST"]),
        Route("/api/admin/overview", api_admin_overview),
        Route("/api/admin/system/status", api_admin_system_status),
        Route("/api/admin/audit", api_admin_audit_logs),
        Route("/api/admin/health/summary", api_admin_health_summary),
        Route("/api/admin/health/issues", api_admin_health_issues),
        Route("/api/admin/submissions", api_admin_submissions),
        Route("/api/admin/submissions/{submission_id:str}", api_admin_submission_detail),
        Route(
            "/api/admin/submissions/{submission_id:str}/triage",
            api_admin_submission_triage,
            methods=["POST"],
        ),
        Route(
            "/api/admin/submissions/{submission_id:str}/run-ingest",
            api_admin_run_ingest,
            methods=["POST"],
        ),
        Route("/api/admin/jobs", api_admin_jobs),
        Route("/api/admin/jobs/{job_id:str}", api_admin_job_detail),
        Route("/api/admin/jobs/{job_id:str}/retry", api_admin_job_retry, methods=["POST"]),
        Route("/api/admin/jobs/{job_id:str}/cancel", api_admin_job_cancel, methods=["POST"]),
        Route("/api/admin/tidy", api_admin_tidy, methods=["POST"]),
        Route("/api/admin/reviews", api_admin_reviews),
        Route("/api/admin/reviews/{review_id:str}", api_admin_review_detail),
        Route(
            "/api/admin/reviews/{review_id:str}/approve",
            api_admin_review_approve,
            methods=["POST"],
        ),
        Route(
            "/api/admin/reviews/{review_id:str}/reject",
            api_admin_review_reject,
            methods=["POST"],
        ),
        Route("/api/admin/entries/{name:str}", api_admin_entry_detail, methods=["GET"]),
        Route("/api/admin/entries/{name:str}", api_admin_entry_save, methods=["PUT"]),
        Route("/api/admin/explore", api_admin_explore, methods=["POST"]),
        Route("/api/admin/quartz/status", api_admin_quartz_status, methods=["GET"]),
        Route("/api/admin/quartz/build", api_admin_quartz_build, methods=["POST"]),
        Mount(ctx.sse_endpoint, app=mcp_app, routes=False),
    ]
    ctx.quartz_site_dir.mkdir(parents=True, exist_ok=True)
    routes.append(
        Mount(
            "/quartz",
            app=StaticFiles(directory=str(ctx.quartz_site_dir), html=True, check_dir=False),
        )
    )
    return Starlette(
        middleware=[Middleware(SecurityHeadersMiddleware)],
        routes=routes,
    )


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
