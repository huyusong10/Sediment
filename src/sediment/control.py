from __future__ import annotations

from pathlib import Path
from typing import Any

from sediment.diagnostics import DiagnosticLogger
from sediment.platform_services import (
    apply_operations,
    build_health_issue_queue,
    get_health_payload,
    infer_mime_type,
    list_reviews_with_jobs,
    submit_feedback_item,
    submit_uploaded_document_item,
)
from sediment.platform_store import PlatformStore

LOGGER = DiagnosticLogger("control")

TIDY_SCOPES = {"full", "graph", "indexes", "health_blocking"}


def normalize_tidy_scope(value: str | None) -> str:
    scope = str(value or "health_blocking").strip().lower()
    aliases = {
        "health-blocking": "health_blocking",
        "health": "health_blocking",
        "blocking": "health_blocking",
        "index": "indexes",
    }
    normalized = aliases.get(scope, scope)
    return normalized if normalized in TIDY_SCOPES else "health_blocking"


def scope_from_issue(issue: dict[str, Any] | None) -> str:
    issue_type = str((issue or {}).get("type", "")).strip().lower()
    if issue_type in {
        "dangling_link",
        "orphan_entry",
        "canonical_gap",
        "promotable_placeholder",
    }:
        return "graph"
    if issue_type in {"invalid_index", "overloaded_index", "unknown_index_link"}:
        return "indexes"
    return "health_blocking"


def build_tidy_request(
    *,
    kb_path: str | Path,
    scope: str,
    reason: str,
    issue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_scope = normalize_tidy_scope(scope)
    issues = build_health_issue_queue(kb_path)
    if issue:
        selected_issues = [dict(issue)]
    elif normalized_scope == "full":
        selected_issues = issues[:20]
    elif normalized_scope == "graph":
        selected_issues = [
            item
            for item in issues
            if scope_from_issue(item) == "graph"
        ][:20]
    elif normalized_scope == "indexes":
        selected_issues = [
            item
            for item in issues
            if scope_from_issue(item) == "indexes"
        ][:20]
    else:
        selected_issues = [
            item
            for item in issues
            if item.get("severity") == "blocking"
        ][:20]

    return {
        "scope": normalized_scope,
        "reason": str(reason or "").strip(),
        "issue": dict(issue or {}),
        "issues": selected_issues,
        "health_report": get_health_payload(kb_path)["summary"],
    }


def submit_text_request(
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
    return submit_feedback_item(
        store=store,
        title=title,
        content=content,
        submitter_name=submitter_name,
        submitter_ip=submitter_ip,
        submitter_user_id=submitter_user_id,
        notes=notes,
        rate_limit_count=rate_limit_count,
        rate_limit_window_seconds=rate_limit_window_seconds,
        max_text_chars=max_text_chars,
        dedupe_window_seconds=dedupe_window_seconds,
    )


def submit_document_request(
    *,
    store: PlatformStore,
    uploads_dir: str | Path,
    filename: str,
    mime_type: str | None,
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
    resolved_mime = (mime_type or "").strip() or infer_mime_type(filename or "") or ""
    return submit_uploaded_document_item(
        store=store,
        uploads_dir=uploads_dir,
        filename=filename,
        mime_type=resolved_mime,
        file_bytes=file_bytes,
        uploads=uploads,
        submitter_name=submitter_name,
        submitter_ip=submitter_ip,
        submitter_user_id=submitter_user_id,
        notes=notes,
        rate_limit_count=rate_limit_count,
        rate_limit_window_seconds=rate_limit_window_seconds,
        max_upload_bytes=max_upload_bytes,
        dedupe_window_seconds=dedupe_window_seconds,
    )


def enqueue_ingest_job(
    *,
    store: PlatformStore,
    submission_id: str | None = None,
    ingest_batch_id: str | None = None,
    actor_name: str,
    actor_id: str | None = None,
    actor_role: str = "committer",
    max_attempts: int,
) -> dict[str, Any]:
    if submission_id:
        submission = store.get_submission(submission_id)
        if submission is None:
            raise FileNotFoundError("submission not found")
        job = store.create_ingest_job_for_submission(
            submission_id=submission_id,
            target_entry_name=submission["title"],
            max_attempts=max_attempts,
            request_payload={
                "submission_id": submission_id,
                "actor_name": actor_name,
                "actor_id": actor_id,
                "actor_role": actor_role,
            },
        )
        details = {"submission_id": submission_id}
    elif ingest_batch_id:
        batch = store.get_ingest_batch(ingest_batch_id)
        if batch is None:
            raise FileNotFoundError("ingest batch not found")
        job = store.create_ingest_job_for_batch(
            batch_id=ingest_batch_id,
            target_entry_name=batch["title"],
            max_attempts=max_attempts,
            request_payload={
                "ingest_batch_id": ingest_batch_id,
                "actor_name": actor_name,
                "actor_id": actor_id,
                "actor_role": actor_role,
            },
        )
        details = {"ingest_batch_id": ingest_batch_id}
    else:
        raise ValueError("submission_id or ingest_batch_id is required")
    store.add_audit_log(
        actor_name=actor_name,
        actor_id=actor_id,
        actor_role=actor_role,
        action="job.enqueue_ingest",
        target_type="job",
        target_id=job["id"],
        details=details,
    )
    LOGGER.info(
        "job.enqueue_ingest",
        "Enqueued ingest job.",
        job_id=job["id"],
        submission_id=submission_id,
        actor_id=actor_id,
        details={"actor_role": actor_role, **details},
    )
    return job


def enqueue_tidy_job(
    *,
    store: PlatformStore,
    kb_path: str | Path,
    scope: str,
    reason: str,
    actor_name: str,
    actor_id: str | None = None,
    actor_role: str = "committer",
    max_attempts: int,
    issue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_payload = build_tidy_request(
        kb_path=kb_path,
        scope=scope,
        reason=reason,
        issue=issue,
    )
    request_payload["actor_name"] = actor_name
    request_payload["actor_id"] = actor_id
    request_payload["actor_role"] = actor_role
    job = store.create_job(
        job_type="tidy",
        target_entry_name=None,
        status="queued",
        max_attempts=max_attempts,
        request_payload=request_payload,
    )
    store.add_audit_log(
        actor_name=actor_name,
        actor_id=actor_id,
        actor_role=actor_role,
        action="job.enqueue_tidy",
        target_type="job",
        target_id=job["id"],
        details={
            "scope": request_payload["scope"],
            "reason": request_payload["reason"],
            "issue": request_payload["issue"],
        },
    )
    LOGGER.info(
        "job.enqueue_tidy",
        "Enqueued tidy job.",
        job_id=job["id"],
        actor_id=actor_id,
        details={
            "actor_role": actor_role,
            "scope": request_payload["scope"],
        },
    )
    return job


def admin_overview_payload(
    *,
    store: PlatformStore,
    kb_path: str | Path,
    stale_after_seconds: int,
) -> dict[str, Any]:
    health = get_health_payload(kb_path)
    jobs = store.list_jobs(limit=200)
    inbox_counts = store.inbox_status_counts() if hasattr(store, "inbox_status_counts") else {}
    pending_inbox = (
        inbox_counts.get("open", 0)
        + inbox_counts.get("staged", 0)
        + inbox_counts.get("ready", 0)
        + inbox_counts.get("ingesting", 0)
    )
    return {
        "submission_counts": {
            **store.submission_status_counts(),
            "pending": pending_inbox,
        },
        "running_jobs": sum(1 for item in jobs if item["status"] == "running"),
        "queued_jobs": sum(1 for item in jobs if item["status"] == "queued"),
        "pending_reviews": 0,
        "open_feedback": inbox_counts.get("open", 0),
        "staged_documents": inbox_counts.get("staged", 0),
        "ready_documents": inbox_counts.get("ready", 0),
        "severity_counts": health["severity_counts"],
        "health_summary": health["summary"],
        "cancel_requested_jobs": sum(
            1 for item in jobs if item["status"] == "cancel_requested"
        ),
        "stale_jobs": len(store.list_stale_jobs(stale_after_seconds=stale_after_seconds)),
    }


def system_status_payload(
    *,
    store: PlatformStore,
    kb_path: str | Path,
    paths: dict[str, Path],
    instance_name: str,
    knowledge_name: str,
    instance_root: str | Path,
    config_path: str | Path,
    host: str,
    port: int,
    sse_endpoint: str,
    public_base_url: str,
    auth_required: bool,
    run_jobs_in_process: bool,
    submission_rate_limit_count: int,
    submission_rate_limit_window_seconds: int,
    submission_dedupe_window_seconds: int,
    max_text_submission_chars: int,
    max_upload_bytes: int,
    job_max_attempts: int,
    job_stale_after_seconds: int,
    trust_proxy_headers: bool,
    trusted_proxy_cidrs: list[str],
) -> dict[str, Any]:
    jobs = store.list_jobs(limit=200)
    stale_jobs = store.list_stale_jobs(stale_after_seconds=job_stale_after_seconds)
    inbox_counts = store.inbox_status_counts() if hasattr(store, "inbox_status_counts") else {}
    query_host = "127.0.0.1" if host in {"0.0.0.0", "::", "[::]"} else host
    base_url = str(public_base_url or "").strip().rstrip("/") or f"http://{query_host}:{port}"

    def public_url(path: str) -> str:
        return f"{base_url}/{str(path or '/').lstrip('/')}"

    return {
        "instance": {
            "name": instance_name,
            "knowledge_name": knowledge_name,
            "root": str(Path(instance_root).resolve()),
            "config_path": str(Path(config_path).resolve()),
        },
        "auth_required": auth_required,
        "urls": {
            "portal": public_url("/"),
            "admin": public_url("/admin/overview"),
            "search": public_url("/search"),
            "submit": public_url("/submit"),
            "quartz": public_url("/quartz/"),
            "health": public_url("/healthz"),
            "mcp_sse": public_url(sse_endpoint),
            "bind_host": host,
        },
        "worker_mode": "in_process" if run_jobs_in_process else "queue",
        "limits": {
            "submission_rate_limit_count": submission_rate_limit_count,
            "submission_rate_limit_window_seconds": submission_rate_limit_window_seconds,
            "submission_dedupe_window_seconds": submission_dedupe_window_seconds,
            "max_text_submission_chars": max_text_submission_chars,
            "max_upload_bytes": max_upload_bytes,
            "job_max_attempts": job_max_attempts,
            "job_stale_after_seconds": job_stale_after_seconds,
        },
        "proxy": {
            "trust_proxy_headers": trust_proxy_headers,
            "trusted_proxy_cidrs": trusted_proxy_cidrs,
        },
        "queue": {
            "queued_jobs": sum(1 for job in jobs if job["status"] == "queued"),
            "running_jobs": sum(1 for job in jobs if job["status"] == "running"),
            "cancel_requested_jobs": sum(
                1 for job in jobs if job["status"] == "cancel_requested"
            ),
            "stale_jobs": len(stale_jobs),
            "pending_reviews": 0,
            "pending_submissions": (
                inbox_counts.get("open", 0)
                + inbox_counts.get("staged", 0)
                + inbox_counts.get("ready", 0)
                + inbox_counts.get("ingesting", 0)
            ),
            "open_feedback": inbox_counts.get("open", 0),
            "staged_documents": inbox_counts.get("staged", 0),
            "ready_documents": inbox_counts.get("ready", 0),
        },
        "health": get_health_payload(kb_path)["summary"],
        "paths": {
            "kb_path": str(Path(kb_path).resolve()),
            "db_path": str(paths["db_path"]),
            "uploads_dir": str(paths["uploads_dir"]),
            "workspaces_dir": str(paths["workspaces_dir"]),
        },
    }


def resolve_tidy_issue(
    *,
    kb_path: str | Path,
    target: str,
    issue_type: str | None = None,
) -> dict[str, Any]:
    scope = normalize_tidy_scope(target)
    if scope != "health_blocking" or target.strip().lower() in TIDY_SCOPES:
        return build_tidy_request(kb_path=kb_path, scope=scope, reason="Manual tidy request")

    issues = build_health_issue_queue(kb_path)
    matches = [item for item in issues if item["target"] == target]
    if issue_type:
        typed = [item for item in matches if item["type"] == issue_type]
        if typed:
            return typed[0]
    if matches:
        return matches[0]
    return {
        "type": issue_type or "manual_tidy_request",
        "severity": "medium",
        "target": target,
        "summary": "Manual tidy request created from CLI",
        "suggested_action": "run_tidy",
        "evidence": {"target": target},
    }


def platform_status_payload(
    *,
    store: PlatformStore,
    kb_path: str | Path,
    paths: dict[str, Path],
    daemon: dict[str, Any],
    instance_name: str,
    knowledge_name: str,
    instance_root: str | Path,
    config_path: str | Path,
    host: str,
    port: int,
    sse_endpoint: str,
    public_base_url: str,
    auth_required: bool,
    run_jobs_in_process: bool,
    submission_rate_limit_count: int,
    submission_rate_limit_window_seconds: int,
    submission_dedupe_window_seconds: int,
    max_text_submission_chars: int,
    max_upload_bytes: int,
    job_max_attempts: int,
    job_stale_after_seconds: int,
    trust_proxy_headers: bool,
    trusted_proxy_cidrs: list[str],
) -> dict[str, Any]:
    payload = system_status_payload(
        store=store,
        kb_path=kb_path,
        paths=paths,
        instance_name=instance_name,
        knowledge_name=knowledge_name,
        instance_root=instance_root,
        config_path=config_path,
        host=host,
        port=port,
        sse_endpoint=sse_endpoint,
        public_base_url=public_base_url,
        auth_required=auth_required,
        run_jobs_in_process=run_jobs_in_process,
        submission_rate_limit_count=submission_rate_limit_count,
        submission_rate_limit_window_seconds=submission_rate_limit_window_seconds,
        submission_dedupe_window_seconds=submission_dedupe_window_seconds,
        max_text_submission_chars=max_text_submission_chars,
        max_upload_bytes=max_upload_bytes,
        job_max_attempts=job_max_attempts,
        job_stale_after_seconds=job_stale_after_seconds,
        trust_proxy_headers=trust_proxy_headers,
        trusted_proxy_cidrs=trusted_proxy_cidrs,
    )
    payload["daemon"] = daemon
    payload["overview"] = admin_overview_payload(
        store=store,
        kb_path=kb_path,
        stale_after_seconds=job_stale_after_seconds,
    )
    payload["recent_reviews"] = []
    return payload


def review_detail_payload(store: PlatformStore, review_id: str) -> dict[str, Any]:
    review = store.get_review(review_id)
    if review is None:
        raise FileNotFoundError("review not found")
    job = store.get_job(review["job_id"])
    submission = (
        store.get_submission(review["submission_id"])
        if review.get("submission_id")
        else None
    )
    return {"review": review, "job": job, "submission": submission}


def apply_review_decision(
    *,
    store: PlatformStore,
    kb_path: str | Path,
    review_id: str,
    decision: str,
    reviewer_name: str,
    reviewer_id: str | None = None,
    reviewer_role: str = "committer",
    comment: str,
) -> dict[str, Any]:
    if decision in {"approve", "approve_formal", "approve_placeholder"}:
        review, job = store.claim_review_resolution(review_id)
        operations = (job.get("result_payload") or {}).get("operations", [])
        try:
            result = apply_operations(
                kb_path,
                operations,
                actor_name=reviewer_name,
                actor_id=reviewer_id,
                actor_role=reviewer_role,
                store=store,
            )
        except Exception as exc:
            store.release_review_resolution(
                review_id,
                error_message=f"review apply failed: {exc}",
            )
            raise
        if review.get("submission_id"):
            resolved_review, resolved_job = store.finalize_review_resolution(
                review_id=review_id,
                decision=decision,
                reviewer_name=reviewer_name,
                comment=comment,
                job_status="succeeded",
                submission_status="accepted",
            )
        else:
            resolved_review, resolved_job = store.finalize_review_resolution(
                review_id=review_id,
                decision=decision,
                reviewer_name=reviewer_name,
                comment=comment,
                job_status="succeeded",
                submission_status=None,
            )
        store.add_audit_log(
            actor_name=reviewer_name,
            actor_id=reviewer_id,
            actor_role=reviewer_role,
            action="review.approve",
            target_type="review",
            target_id=review_id,
            details={"job_id": job["id"], "decision": decision, "comment": comment},
        )
        return {
            "review": resolved_review,
            "job": resolved_job,
            "apply_result": result,
        }

    if decision in {"reject", "request_changes", "cancel"}:
        review, job = store.claim_review_resolution(review_id)
        resolved_review, resolved_job = store.finalize_review_resolution(
            review_id=review_id,
            decision=decision,
            reviewer_name=reviewer_name,
            comment=comment,
            job_status="cancelled",
            submission_status=(
                "rejected" if decision == "reject" else "triaged"
            )
            if review.get("submission_id")
            else None,
        )
        store.add_audit_log(
            actor_name=reviewer_name,
            actor_id=reviewer_id,
            actor_role=reviewer_role,
            action="review.reject" if decision == "reject" else "review.request_changes",
            target_type="review",
            target_id=review_id,
            details={"job_id": job["id"], "decision": decision, "comment": comment},
        )
        return {"review": resolved_review, "job": resolved_job}

    raise ValueError(f"unsupported review decision: {decision}")
