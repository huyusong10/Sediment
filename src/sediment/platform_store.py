from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JSON_FIELDS = {"request_payload", "result_payload", "details", "analysis"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_seconds_ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).replace(
        microsecond=0
    ).isoformat()


class PlatformStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY,
                    submission_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    extracted_text TEXT NOT NULL,
                    stored_file_path TEXT,
                    mime_type TEXT,
                    submitter_name TEXT NOT NULL,
                    submitter_ip TEXT NOT NULL,
                    submitter_user_id TEXT,
                    status TEXT NOT NULL,
                    dedupe_hash TEXT NOT NULL,
                    analysis TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_submissions_status
                ON submissions(status, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_submissions_ip_created
                ON submissions(submitter_ip, created_at DESC);

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    source_submission_id TEXT,
                    target_entry_name TEXT,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    runner_host TEXT,
                    workspace_path TEXT,
                    request_payload TEXT,
                    result_payload TEXT,
                    error_message TEXT,
                    last_heartbeat_at TEXT,
                    cancel_requested_at TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status_created
                ON jobs(status, created_at DESC);

                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY,
                    submission_id TEXT,
                    job_id TEXT NOT NULL,
                    review_type TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reviewer_id TEXT,
                    reviewer_name TEXT,
                    comment TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_reviews_job
                ON reviews(job_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    actor_name TEXT NOT NULL,
                    actor_id TEXT,
                    actor_role TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_audit_logs_created
                ON audit_logs(created_at DESC);
                """
            )
            self._ensure_column(
                conn,
                table="submissions",
                column="analysis",
                definition="TEXT",
            )
            self._ensure_column(
                conn,
                table="jobs",
                column="attempt_count",
                definition="INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                conn,
                table="jobs",
                column="max_attempts",
                definition="INTEGER NOT NULL DEFAULT 3",
            )
            self._ensure_column(
                conn,
                table="jobs",
                column="last_heartbeat_at",
                definition="TEXT",
            )
            self._ensure_column(
                conn,
                table="jobs",
                column="cancel_requested_at",
                definition="TEXT",
            )

    def submission_count_for_ip(self, submitter_ip: str, *, within_seconds: int) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM submissions
                WHERE submitter_ip = ?
                  AND created_at >= ?
                """,
                (submitter_ip, utc_seconds_ago(within_seconds)),
            ).fetchone()
        return int(row["count"])

    def create_submission(
        self,
        *,
        submission_type: str,
        title: str,
        raw_text: str,
        extracted_text: str,
        stored_file_path: str | None,
        mime_type: str | None,
        submitter_name: str,
        submitter_ip: str,
        submitter_user_id: str | None,
        dedupe_hash: str,
        status: str = "pending",
        analysis: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        submission_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO submissions (
                    id,
                    submission_type,
                    title,
                    raw_text,
                    extracted_text,
                    stored_file_path,
                    mime_type,
                    submitter_name,
                    submitter_ip,
                    submitter_user_id,
                    status,
                    dedupe_hash,
                    analysis,
                    notes,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    submission_type,
                    title,
                    raw_text,
                    extracted_text,
                    stored_file_path,
                    mime_type,
                    submitter_name,
                    submitter_ip,
                    submitter_user_id,
                    status,
                    dedupe_hash,
                    self._encode_json(analysis),
                    notes,
                    now,
                    now,
                ),
            )
        return self.get_submission(submission_id)

    def find_recent_submission_by_hash(
        self,
        dedupe_hash: str,
        *,
        within_seconds: int,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM submissions
                WHERE dedupe_hash = ?
                  AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (dedupe_hash, utc_seconds_ago(within_seconds)),
            ).fetchone()
        return self._decode_row(row)

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM submissions WHERE id = ?",
                (submission_id,),
            ).fetchone()
        return self._decode_row(row)

    def list_submissions(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 200))
        query = "SELECT * FROM submissions"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode_row(row) for row in rows]

    def submission_status_counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM submissions
                GROUP BY status
                """
            ).fetchall()
        return {row["status"]: int(row["count"]) for row in rows}

    def update_submission(self, submission_id: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get_submission(submission_id)
        fields["updated_at"] = utc_now()
        self._update_row("submissions", submission_id, fields)
        return self.get_submission(submission_id)

    def create_job(
        self,
        *,
        job_type: str,
        source_submission_id: str | None = None,
        target_entry_name: str | None = None,
        status: str = "queued",
        attempt_count: int = 0,
        max_attempts: int = 3,
        runner_host: str | None = None,
        workspace_path: str | None = None,
        request_payload: dict[str, Any] | None = None,
        result_payload: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id,
                    job_type,
                    source_submission_id,
                    target_entry_name,
                    status,
                    attempt_count,
                    max_attempts,
                    runner_host,
                    workspace_path,
                    request_payload,
                    result_payload,
                    error_message,
                    last_heartbeat_at,
                    cancel_requested_at,
                    created_at,
                    started_at,
                    finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    job_type,
                    source_submission_id,
                    target_entry_name,
                    status,
                    max(0, int(attempt_count)),
                    max(1, int(max_attempts)),
                    runner_host,
                    workspace_path,
                    self._encode_json(request_payload),
                    self._encode_json(result_payload),
                    error_message,
                    None,
                    None,
                    now,
                    None,
                    None,
                ),
            )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return self._decode_row(row)

    def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 200))
        query = "SELECT * FROM jobs"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode_row(row) for row in rows]

    def claim_next_job(
        self,
        *,
        runner_host: str,
        stale_after_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            if stale_after_seconds and stale_after_seconds > 0:
                self._recover_stale_jobs_in_txn(conn, stale_after_seconds=stale_after_seconds)
            row = conn.execute(
                """
                SELECT id
                FROM jobs
                WHERE status = 'queued'
                  AND attempt_count < max_attempts
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            now = utc_now()
            updated = conn.execute(
                """
                UPDATE jobs
                SET status = 'running',
                    attempt_count = attempt_count + 1,
                    runner_host = ?,
                    started_at = ?,
                    error_message = NULL,
                    last_heartbeat_at = ?,
                    cancel_requested_at = NULL
                WHERE id = ?
                  AND status = 'queued'
                """,
                (runner_host, now, now, row["id"]),
            )
            if updated.rowcount != 1:
                conn.execute("ROLLBACK")
                return None
            conn.execute("COMMIT")
        return self.get_job(row["id"])

    def update_job(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get_job(job_id)
        self._update_row("jobs", job_id, fields)
        return self.get_job(job_id)

    def heartbeat_job(self, job_id: str) -> dict[str, Any] | None:
        return self.update_job(job_id, last_heartbeat_at=utc_now())

    def list_stale_jobs(
        self,
        *,
        stale_after_seconds: int,
        statuses: tuple[str, ...] = ("running", "cancel_requested"),
    ) -> list[dict[str, Any]]:
        if stale_after_seconds <= 0:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        params: list[Any] = [utc_seconds_ago(stale_after_seconds), *statuses]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM jobs
                WHERE COALESCE(last_heartbeat_at, started_at, created_at) < ?
                  AND status IN ({placeholders})
                ORDER BY created_at ASC
                """,
                tuple(params),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def recover_stale_jobs(self, *, stale_after_seconds: int) -> list[dict[str, Any]]:
        if stale_after_seconds <= 0:
            return []
        with self._connect() as conn:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            recovered_ids = self._recover_stale_jobs_in_txn(
                conn,
                stale_after_seconds=stale_after_seconds,
            )
            conn.execute("COMMIT")
        return [job for job_id in recovered_ids if (job := self.get_job(job_id)) is not None]

    def retry_job(self, job_id: str) -> dict[str, Any] | None:
        job = self.get_job(job_id)
        if job is None:
            return None
        if job["status"] not in {"failed", "cancelled"}:
            raise ValueError("only failed or cancelled jobs can be retried")
        return self.update_job(
            job_id,
            status="queued",
            attempt_count=0,
            runner_host=None,
            workspace_path=None,
            result_payload=None,
            error_message=None,
            last_heartbeat_at=None,
            cancel_requested_at=None,
            started_at=None,
            finished_at=None,
        )

    def cancel_job(self, job_id: str, *, reason: str | None = None) -> dict[str, Any] | None:
        job = self.get_job(job_id)
        if job is None:
            return None
        now = utc_now()
        detail = reason or "job cancelled by admin"
        if job["status"] == "queued":
            return self.update_job(
                job_id,
                status="cancelled",
                error_message=detail,
                cancel_requested_at=now,
                last_heartbeat_at=now,
                finished_at=now,
            )
        if job["status"] == "running":
            return self.update_job(
                job_id,
                status="cancel_requested",
                error_message=detail,
                cancel_requested_at=now,
                last_heartbeat_at=now,
            )
        if job["status"] == "awaiting_review":
            return self.update_job(
                job_id,
                status="cancelled",
                error_message=detail,
                cancel_requested_at=now,
                finished_at=now,
            )
        raise ValueError("job is already finished and cannot be cancelled")

    def create_review(
        self,
        *,
        job_id: str,
        submission_id: str | None,
        review_type: str,
        decision: str = "pending",
        reviewer_id: str | None = None,
        reviewer_name: str | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        review_id = uuid.uuid4().hex
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reviews (
                    id,
                    submission_id,
                    job_id,
                    review_type,
                    decision,
                    reviewer_id,
                    reviewer_name,
                    comment,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    submission_id,
                    job_id,
                    review_type,
                    decision,
                    reviewer_id,
                    reviewer_name,
                    comment,
                    now,
                    now,
                ),
            )
        return self.get_review(review_id)

    def find_review_by_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM reviews
                WHERE job_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        return self._decode_row(row)

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reviews WHERE id = ?",
                (review_id,),
            ).fetchone()
        return self._decode_row(row)

    def list_reviews(
        self,
        *,
        decision: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 200))
        query = "SELECT * FROM reviews"
        params: list[Any] = []
        if decision:
            query += " WHERE decision = ?"
            params.append(decision)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode_row(row) for row in rows]

    def update_review(self, review_id: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get_review(review_id)
        fields["updated_at"] = utc_now()
        self._update_row("reviews", review_id, fields)
        return self.get_review(review_id)

    def add_audit_log(
        self,
        *,
        actor_name: str,
        actor_role: str,
        action: str,
        target_type: str,
        target_id: str,
        actor_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        log_id = uuid.uuid4().hex
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (
                    id,
                    actor_name,
                    actor_id,
                    actor_role,
                    action,
                    target_type,
                    target_id,
                    details,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    actor_name,
                    actor_id,
                    actor_role,
                    action,
                    target_type,
                    target_id,
                    self._encode_json(details),
                    now,
                ),
            )
        return self.get_audit_log(log_id)

    def get_audit_log(self, log_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM audit_logs WHERE id = ?",
                (log_id,),
            ).fetchone()
        return self._decode_row(row)

    def list_audit_logs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 200))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def _update_row(self, table: str, row_id: str, fields: dict[str, Any]) -> None:
        assignments: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            if key in JSON_FIELDS and value is not None:
                values.append(self._encode_json(value))
            else:
                values.append(value)
        values.append(row_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE {table} SET {', '.join(assignments)} WHERE id = ?",
                tuple(values),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        *,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column in columns:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _recover_stale_jobs_in_txn(
        self,
        conn: sqlite3.Connection,
        *,
        stale_after_seconds: int,
    ) -> list[str]:
        cutoff = utc_seconds_ago(stale_after_seconds)
        rows = conn.execute(
            """
            SELECT id, status, attempt_count, max_attempts
            FROM jobs
            WHERE COALESCE(last_heartbeat_at, started_at, created_at) < ?
              AND status IN ('running', 'cancel_requested')
            ORDER BY created_at ASC
            """,
            (cutoff,),
        ).fetchall()
        recovered_ids: list[str] = []
        now = utc_now()
        for row in rows:
            if row["status"] == "cancel_requested":
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'cancelled',
                        finished_at = ?,
                        last_heartbeat_at = ?,
                        error_message = COALESCE(
                            error_message,
                            'job cancelled while worker was offline'
                        )
                    WHERE id = ?
                    """,
                    (now, now, row["id"]),
                )
                recovered_ids.append(row["id"])
                continue
            if int(row["attempt_count"]) < int(row["max_attempts"]):
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'queued',
                        runner_host = NULL,
                        workspace_path = NULL,
                        result_payload = NULL,
                        error_message = 'recovered stale running job after heartbeat timeout',
                        last_heartbeat_at = NULL,
                        cancel_requested_at = NULL,
                        started_at = NULL,
                        finished_at = NULL
                    WHERE id = ?
                    """,
                    (row["id"],),
                )
            else:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed',
                        finished_at = ?,
                        last_heartbeat_at = ?,
                        error_message = 'job exceeded max attempts after stale recovery'
                    WHERE id = ?
                    """,
                    (now, now, row["id"]),
                )
            recovered_ids.append(row["id"])
        return recovered_ids

    def _decode_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        payload = dict(row)
        for field in JSON_FIELDS:
            value = payload.get(field)
            if not value:
                payload[field] = None
                continue
            try:
                payload[field] = json.loads(value)
            except json.JSONDecodeError:
                payload[field] = value
        return payload

    @staticmethod
    def _encode_json(value: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)
