from __future__ import annotations

from pathlib import Path
from typing import Any

from sediment.platform_services import (
    apply_operations,
    build_health_issue_queue,
    get_health_payload,
    infer_mime_type,
    list_reviews_with_jobs,
    submit_document,
    submit_text,
)
from sediment.platform_store import PlatformStore, utc_now


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
    return submit_text(
        store=store,
        kb_path=kb_path,
        title=title,
        content=content,
        submitter_name=submitter_name,
        submitter_ip=submitter_ip,
        submission_type=submission_type,
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
    return submit_document(
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
    submission_id: str,
    actor_name: str,
    max_attempts: int,
) -> dict[str, Any]:
    submission = store.get_submission(submission_id)
    if submission is None:
        raise FileNotFoundError("submission not found")
    job = store.create_job(
        job_type="ingest",
        source_submission_id=submission_id,
        target_entry_name=submission["title"],
        status="queued",
        max_attempts=max_attempts,
        request_payload={"submission_id": submission_id},
    )
    store.update_submission(submission_id, status="ingesting")
    store.add_audit_log(
        actor_name=actor_name,
        actor_role="committer",
        action="job.enqueue_ingest",
        target_type="job",
        target_id=job["id"],
        details={"submission_id": submission_id},
    )
    return job


def enqueue_tidy_job(
    *,
    store: PlatformStore,
    kb_path: str | Path,
    issue: dict[str, Any],
    actor_name: str,
    max_attempts: int,
) -> dict[str, Any]:
    target = str(issue.get("target", ""))
    job = store.create_job(
        job_type="tidy",
        target_entry_name=target or None,
        status="queued",
        max_attempts=max_attempts,
        request_payload={
            "issue": issue,
            "health_report": get_health_payload(kb_path)["summary"],
        },
    )
    store.add_audit_log(
        actor_name=actor_name,
        actor_role="committer",
        action="job.enqueue_tidy",
        target_type="job",
        target_id=job["id"],
        details={"target": target, "issue": issue},
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
    return {
        "submission_counts": store.submission_status_counts(),
        "running_jobs": sum(1 for item in jobs if item["status"] == "running"),
        "queued_jobs": sum(1 for item in jobs if item["status"] == "queued"),
        "pending_reviews": len(store.list_reviews(decision="pending", limit=200)),
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
    query_host = "127.0.0.1" if host in {"0.0.0.0", "::", "[::]"} else host
    return {
        "instance": {
            "name": instance_name,
            "knowledge_name": knowledge_name,
            "root": str(Path(instance_root).resolve()),
            "config_path": str(Path(config_path).resolve()),
        },
        "auth_required": auth_required,
        "urls": {
            "portal": f"http://{query_host}:{port}/portal",
            "admin": f"http://{query_host}:{port}/admin",
            "health": f"http://{query_host}:{port}/healthz",
            "mcp_sse": f"http://{query_host}:{port}{sse_endpoint}",
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
            "pending_reviews": len(store.list_reviews(decision="pending", limit=200)),
            "pending_submissions": store.submission_status_counts().get("pending", 0),
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
    payload["recent_reviews"] = list_reviews_with_jobs(store=store, decision="pending")[:5]
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
    comment: str,
) -> dict[str, Any]:
    review = store.get_review(review_id)
    if review is None:
        raise FileNotFoundError("review not found")
    job = store.get_job(review["job_id"])
    if job is None:
        raise FileNotFoundError("review job not found")
    if review["decision"] != "pending":
        raise RuntimeError("review has already been resolved")
    if job["status"] != "awaiting_review":
        raise RuntimeError(f"job is not awaiting review (current status: {job['status']})")

    if decision in {"approve", "approve_formal", "approve_placeholder"}:
        operations = (job.get("result_payload") or {}).get("operations", [])
        result = apply_operations(
            kb_path,
            operations,
            actor_name=reviewer_name,
            actor_role="committer",
            store=store,
        )
        store.update_review(
            review_id,
            decision=decision,
            reviewer_name=reviewer_name,
            comment=comment,
        )
        store.update_job(job["id"], status="succeeded", finished_at=utc_now())
        if review.get("submission_id"):
            store.update_submission(review["submission_id"], status="accepted")
        store.add_audit_log(
            actor_name=reviewer_name,
            actor_role="committer",
            action="review.approve",
            target_type="review",
            target_id=review_id,
            details={"job_id": job["id"], "decision": decision, "comment": comment},
        )
        return {
            "review": store.get_review(review_id),
            "job": store.get_job(job["id"]),
            "apply_result": result,
        }

    if decision in {"reject", "request_changes", "cancel"}:
        store.update_review(
            review_id,
            decision=decision,
            reviewer_name=reviewer_name,
            comment=comment,
        )
        store.update_job(job["id"], status="cancelled", finished_at=utc_now())
        if review.get("submission_id"):
            store.update_submission(
                review["submission_id"],
                status="rejected" if decision == "reject" else "triaged",
            )
        store.add_audit_log(
            actor_name=reviewer_name,
            actor_role="committer",
            action="review.reject" if decision == "reject" else "review.request_changes",
            target_type="review",
            target_id=review_id,
            details={"job_id": job["id"], "decision": decision, "comment": comment},
        )
        return {"review": store.get_review(review_id), "job": store.get_job(job["id"])}

    raise ValueError(f"unsupported review decision: {decision}")
