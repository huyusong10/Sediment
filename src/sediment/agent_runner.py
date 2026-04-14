# ruff: noqa: E501
from __future__ import annotations

import json
import re
import socket
import subprocess
import shutil
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from sediment.kb import inventory
from sediment.llm_cli import build_cli_command, collect_output
from sediment.package_data import read_skill_text
from sediment.platform_services import (
    build_diff,
    content_hash,
    determine_target_path,
    stage_workspace_copy,
    validate_target_content,
)
from sediment.platform_store import PlatformStore, utc_now
from sediment.settings import load_settings

INGEST_SCHEMA = json.dumps(
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "drafts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "entry_type": {
                            "type": "string",
                            "enum": ["concept", "lesson", "placeholder"],
                        },
                        "relative_path": {"type": "string"},
                        "rationale": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["name", "entry_type", "content", "rationale"],
                },
            },
        },
        "required": ["summary", "warnings", "drafts"],
    },
    ensure_ascii=False,
)

TIDY_SCHEMA = json.dumps(
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "relative_path": {"type": "string"},
                        "change_type": {
                            "type": "string",
                            "enum": ["create", "update", "delete"],
                        },
                        "rationale": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["change_type", "rationale"],
                },
            },
        },
        "required": ["summary", "warnings", "changes"],
    },
    ensure_ascii=False,
)


class AgentRunner:
    def __init__(
        self,
        *,
        project_root: str | Path,
        kb_path: str | Path,
        workspaces_dir: str | Path,
        store: PlatformStore,
        max_workers: int = 2,
    ):
        self.project_root = Path(project_root).resolve()
        self.kb_path = Path(kb_path).resolve()
        self.workspaces_dir = Path(workspaces_dir).resolve()
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sediment")
        self.futures: dict[str, Future[Any]] = {}

    def submit(self, job_id: str) -> None:
        future = self.executor.submit(self.run_job_now, job_id)
        self.futures[job_id] = future

    def run_job_now(self, job_id: str) -> None:
        job = self.store.get_job(job_id)
        if not job:
            return
        if job["job_type"] == "ingest":
            self._run_ingest(job)
            return
        if job["job_type"] == "tidy":
            self._run_tidy(job)
            return
        self.store.update_job(
            job_id,
            status="failed",
            finished_at=utc_now(),
            error_message=f"unsupported job type: {job['job_type']}",
        )

    def _run_ingest(self, job: dict[str, Any]) -> None:
        submission = self.store.get_submission(job["source_submission_id"])
        if submission is None:
            self.store.update_job(
                job["id"],
                status="failed",
                finished_at=utc_now(),
                error_message="submission not found",
            )
            return
        workspace = stage_workspace_copy(self.kb_path, self.workspaces_dir, job["id"])
        try:
            self.store.update_job(
                job["id"],
                status="running",
                started_at=utc_now(),
                runner_host=socket.gethostname(),
                workspace_path=str(workspace),
            )
            try:
                payload = self._run_ingest_agent(job, submission, workspace)
            except Exception as exc:  # noqa: BLE001
                latest = self.store.get_job(job["id"])
                if latest and latest["status"] == "cancel_requested":
                    self.store.update_job(
                        job["id"],
                        status="cancelled",
                        finished_at=utc_now(),
                        error_message="job cancelled by admin",
                        workspace_path=None,
                    )
                    self.store.update_submission(submission["id"], status="triaged")
                    return
                self.store.update_job(
                    job["id"],
                    status="failed",
                    finished_at=utc_now(),
                    error_message=str(exc),
                    workspace_path=None,
                )
                self.store.update_submission(submission["id"], status="triaged")
                return

            latest = self.store.get_job(job["id"])
            if latest and latest["status"] == "cancel_requested":
                self.store.update_job(
                    job["id"],
                    status="cancelled",
                    finished_at=utc_now(),
                    error_message="job cancelled by admin",
                    result_payload=payload,
                    workspace_path=None,
                )
                self.store.update_submission(submission["id"], status="triaged")
                return

            self.store.update_job(
                job["id"],
                status="awaiting_review",
                finished_at=utc_now(),
                result_payload=payload,
                workspace_path=None,
            )
            self.store.update_submission(submission["id"], status="draft_ready")
            if self.store.find_review_by_job(job["id"]) is None:
                self.store.create_review(
                    job_id=job["id"],
                    submission_id=submission["id"],
                    review_type="ingest",
                )
        finally:
            self._cleanup_workspace(workspace)

    def _run_tidy(self, job: dict[str, Any]) -> None:
        workspace = stage_workspace_copy(self.kb_path, self.workspaces_dir, job["id"])
        try:
            self.store.update_job(
                job["id"],
                status="running",
                started_at=utc_now(),
                runner_host=socket.gethostname(),
                workspace_path=str(workspace),
            )
            try:
                payload = self._run_tidy_agent(job, workspace)
            except Exception as exc:  # noqa: BLE001
                latest = self.store.get_job(job["id"])
                if latest and latest["status"] == "cancel_requested":
                    self.store.update_job(
                        job["id"],
                        status="cancelled",
                        finished_at=utc_now(),
                        error_message="job cancelled by admin",
                        workspace_path=None,
                    )
                    return
                self.store.update_job(
                    job["id"],
                    status="failed",
                    finished_at=utc_now(),
                    error_message=str(exc),
                    workspace_path=None,
                )
                return

            latest = self.store.get_job(job["id"])
            if latest and latest["status"] == "cancel_requested":
                self.store.update_job(
                    job["id"],
                    status="cancelled",
                    finished_at=utc_now(),
                    error_message="job cancelled by admin",
                    result_payload=payload,
                    workspace_path=None,
                )
                return

            self.store.update_job(
                job["id"],
                status="awaiting_review",
                finished_at=utc_now(),
                result_payload=payload,
                workspace_path=None,
            )
            if self.store.find_review_by_job(job["id"]) is None:
                self.store.create_review(
                    job_id=job["id"],
                    submission_id=job.get("source_submission_id"),
                    review_type="tidy",
                )
        finally:
            self._cleanup_workspace(workspace)

    def _run_ingest_agent(
        self,
        job: dict[str, Any],
        submission: dict[str, Any],
        workspace: Path,
    ) -> dict[str, Any]:
        workspace_kb_path = workspace / "knowledge-base"
        kb_inventory = inventory(workspace_kb_path)
        existing_names = sorted(set(kb_inventory["entries"]) | set(kb_inventory["placeholders"]))[:120]
        prompt = "\n\n".join(
            [
                "You are the Sediment ingest runner.",
                "You are running on the knowledge-base host and may inspect local files if your CLI supports it.",
                "Return JSON only. Do not write files directly. Produce conservative drafts that are easy to review.",
                "If the evidence is weak, prefer placeholder drafts over speculative fact entries.",
                self._load_skill_body("ingest"),
                "## Submission",
                json.dumps(
                    {
                        "title": submission["title"],
                        "submission_type": submission["submission_type"],
                        "submitter_name": submission["submitter_name"],
                        "mime_type": submission["mime_type"],
                        "text": submission["extracted_text"],
                        "existing_names": existing_names,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )
        parsed = self._run_cli_json(
            prompt=prompt,
            schema=INGEST_SCHEMA,
            job_id=job["id"],
            cwd=workspace,
        )
        drafts = parsed.get("drafts", [])
        operations = []
        for draft in drafts:
            name = draft["name"].strip()
            target = determine_target_path(
                workspace_kb_path,
                name=name,
                content=draft["content"],
                relative_path=draft.get("relative_path"),
            )
            old_content = target.read_text(encoding="utf-8") if target.exists() else ""
            validation = validate_target_content(target, draft["content"])
            if validation and validation.get("hard_failures"):
                raise RuntimeError(
                    f"invalid ingest draft for {name}: {'; '.join(validation['hard_failures'])}"
                )
            rel_path = str(target.relative_to(workspace_kb_path))
            operations.append(
                {
                    "name": name,
                    "entry_type": draft["entry_type"],
                    "relative_path": rel_path,
                    "change_type": "update" if old_content else "create",
                    "rationale": draft["rationale"],
                    "content": draft["content"].strip() + "\n",
                    "base_hash": content_hash(old_content) if old_content else None,
                    "diff": build_diff(rel_path, old_content, draft["content"].strip() + "\n"),
                }
            )
        return {
            "summary": parsed.get("summary", ""),
            "warnings": parsed.get("warnings", []),
            "operations": operations,
        }

    def _run_tidy_agent(self, job: dict[str, Any], workspace: Path) -> dict[str, Any]:
        workspace_kb_path = workspace / "knowledge-base"
        request_payload = job.get("request_payload") or {}
        prompt = "\n\n".join(
            [
                "You are the Sediment tidy runner.",
                "You are running on the knowledge-base host and may inspect local files if your CLI supports it.",
                "Return JSON only. Do not write files directly. Touch only files needed to address the requested issue.",
                "Keep changes conservative and human-reviewable.",
                self._load_skill_body("tidy"),
                "## Requested Tidy Task",
                json.dumps(
                    {
                        "target_entry_name": job.get("target_entry_name"),
                        "request_payload": request_payload,
                        "health_report": request_payload.get("health_report"),
                        "issue": request_payload.get("issue"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )
        parsed = self._run_cli_json(
            prompt=prompt,
            schema=TIDY_SCHEMA,
            job_id=job["id"],
            cwd=workspace,
        )
        operations = []
        for change in parsed.get("changes", []):
            if change["change_type"] == "delete":
                relative_path = change.get("relative_path")
                if not relative_path:
                    raise RuntimeError("delete changes must include relative_path")
                target = (workspace_kb_path / relative_path).resolve()
                old_content = target.read_text(encoding="utf-8") if target.exists() else ""
                operations.append(
                    {
                        "name": change.get("name") or Path(relative_path).stem,
                        "relative_path": relative_path,
                        "change_type": "delete",
                        "rationale": change["rationale"],
                        "base_hash": content_hash(old_content) if old_content else None,
                        "diff": build_diff(relative_path, old_content, ""),
                    }
                )
                continue

            content = (change.get("content") or "").strip()
            if not content:
                raise RuntimeError("non-delete tidy changes must include content")
            name = change.get("name") or Path(change.get("relative_path", "")).stem
            if not name:
                raise RuntimeError("tide change must include name or relative_path")
            target = determine_target_path(
                workspace_kb_path,
                name=name,
                content=content,
                relative_path=change.get("relative_path"),
            )
            old_content = target.read_text(encoding="utf-8") if target.exists() else ""
            validation = validate_target_content(target, content)
            if validation and validation.get("hard_failures"):
                raise RuntimeError(
                    f"invalid tidy draft for {name}: {'; '.join(validation['hard_failures'])}"
                )
            rel_path = str(target.relative_to(workspace_kb_path))
            operations.append(
                {
                    "name": name,
                    "relative_path": rel_path,
                    "change_type": change["change_type"],
                    "rationale": change["rationale"],
                    "content": content + "\n",
                    "base_hash": content_hash(old_content) if old_content else None,
                    "diff": build_diff(rel_path, old_content, content + "\n"),
                }
            )
        return {
            "summary": parsed.get("summary", ""),
            "warnings": parsed.get("warnings", []),
            "operations": operations,
        }

    def _load_skill_body(self, skill_name: str) -> str:
        local_skill = self.project_root / "skills" / skill_name / "SKILL.md"
        if local_skill.exists():
            return local_skill.read_text(encoding="utf-8")
        return read_skill_text(skill_name)

    def _run_cli_json(
        self,
        *,
        prompt: str,
        schema: str,
        job_id: str,
        cwd: Path,
    ) -> dict[str, Any]:
        settings = load_settings()
        timeout_seconds = int(settings["agent"]["exec_timeout_seconds"])
        with tempfile.TemporaryDirectory(prefix="sediment-agent-") as temp_dir:
            temp_root = Path(temp_dir)
            prompt_file = temp_root / "prompt.txt"
            payload_file = temp_root / "payload.json"
            skill_file = temp_root / "skill.md"
            prompt_file.write_text(prompt, encoding="utf-8")
            payload_file.write_text("{}", encoding="utf-8")
            skill_file.write_text("", encoding="utf-8")
            invocation = build_cli_command(
                settings,
                prompt,
                prompt_file=prompt_file,
                payload_file=payload_file,
                skill_file=skill_file,
                cwd=cwd,
                extra_args=["--json-schema", schema],
            )
            try:
                process = subprocess.Popen(
                    invocation.command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(cwd),
                )
                if process.stdin is not None:
                    process.stdin.write(invocation.stdin_data or "")
                    process.stdin.close()
                    process.stdin = None
            except FileNotFoundError as exc:  # pragma: no cover - environment dependent
                raise RuntimeError(
                    f"agent CLI unavailable: {exc.filename or invocation.command[0]}"
                ) from exc

            started = time.monotonic()
            while True:
                self.store.heartbeat_job(job_id)
                latest = self.store.get_job(job_id)
                if latest and latest["status"] == "cancel_requested":
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise RuntimeError("job cancelled by admin")
                if process.poll() is not None:
                    break
                if time.monotonic() - started > timeout_seconds:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise RuntimeError("agent CLI timed out")
                time.sleep(1)

            stdout, stderr = process.communicate()
            if process.returncode != 0:
                detail = stderr.strip() or stdout.strip() or f"exit code {process.returncode}"
                raise RuntimeError(f"agent CLI failed: {detail}")
            raw_output = collect_output(invocation, stdout=stdout, stderr=stderr)
            if not raw_output:
                raise RuntimeError("agent CLI returned no output")
            return self._parse_cli_json(raw_output)

    @staticmethod
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
        raise RuntimeError("agent CLI did not return a valid JSON object")

    def _cleanup_workspace(self, workspace: Path) -> None:
        shutil.rmtree(workspace, ignore_errors=True)


_RUNNERS: dict[tuple[str, str, str], AgentRunner] = {}


def get_agent_runner(
    *,
    project_root: str | Path,
    kb_path: str | Path,
    workspaces_dir: str | Path,
    store: PlatformStore,
) -> AgentRunner:
    key = (str(project_root), str(kb_path), str(workspaces_dir))
    runner = _RUNNERS.get(key)
    if runner is None:
        runner = AgentRunner(
            project_root=project_root,
            kb_path=kb_path,
            workspaces_dir=workspaces_dir,
            store=store,
        )
        _RUNNERS[key] = runner
    return runner
