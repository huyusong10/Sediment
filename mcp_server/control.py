from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp_server.platform_services import (
    build_health_issue_queue,
    get_health_payload,
    list_reviews_with_jobs,
)
from mcp_server.platform_store import PlatformStore


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
    return {
        "auth_required": auth_required,
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
