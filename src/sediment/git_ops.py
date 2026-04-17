from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

MANAGED_GITIGNORE_START = "# >>> Sediment managed"
MANAGED_GITIGNORE_END = "# <<< Sediment managed"
MANAGED_GITIGNORE_LINES = (
    ".sediment_state/",
    "config/sediment/config.yaml",
)


class GitOperationError(RuntimeError):
    """Raised when a Git operation cannot be completed safely."""


def git_settings_payload(settings: dict[str, Any]) -> dict[str, Any]:
    payload = settings.get("git") or {}
    return {
        "enabled": bool(payload.get("enabled", True)),
        "repo_root": Path(payload.get("repo_root") or settings.get("workspace_root")).resolve(),
        "tracked_paths": [str(item) for item in payload.get("tracked_paths", ["knowledge-base"])],
        "remote_name": str(payload.get("remote_name", "origin")).strip() or "origin",
        "system_author_name": (
            str(payload.get("system_author_name", "Sediment System")).strip()
            or "Sediment System"
        ),
        "system_author_email": (
            str(payload.get("system_author_email", "sediment-system@local")).strip()
            or "sediment-system@local"
        ),
    }


def write_managed_gitignore(repo_root: str | Path) -> Path:
    root = Path(repo_root).resolve()
    target = root / ".gitignore"
    block_lines = [MANAGED_GITIGNORE_START, *MANAGED_GITIGNORE_LINES, MANAGED_GITIGNORE_END]
    block = "\n".join(block_lines) + "\n"
    if not target.exists():
        target.write_text(block, encoding="utf-8")
        return target

    content = target.read_text(encoding="utf-8")
    start_index = content.find(MANAGED_GITIGNORE_START)
    end_index = content.find(MANAGED_GITIGNORE_END)
    if start_index != -1 and end_index != -1 and end_index > start_index:
        end_index = content.index("\n", end_index) + 1 if "\n" in content[end_index:] else len(content)
        updated = content[:start_index] + block + content[end_index:]
    else:
        separator = "\n" if content and not content.endswith("\n") else ""
        updated = content + separator + block
    target.write_text(updated, encoding="utf-8")
    return target


def git_status(*, settings: dict[str, Any], recent_limit: int = 12) -> dict[str, Any]:
    git = git_settings_payload(settings)
    repo_root = git["repo_root"]
    payload: dict[str, Any] = {
        "enabled": git["enabled"],
        "repo_root": str(repo_root),
        "tracked_paths": list(git["tracked_paths"]),
        "is_repo": False,
        "current_branch": "",
        "has_upstream": False,
        "ahead": 0,
        "behind": 0,
        "tracked_changes": [],
        "recent_commits": [],
    }
    if not git["enabled"]:
        payload["error"] = "git integration is disabled"
        return payload
    if not _is_git_repo(repo_root):
        payload["error"] = "git repository not found"
        return payload

    payload["is_repo"] = True
    status_lines = _run_git(repo_root, "status", "--branch", "--porcelain=v1").stdout.splitlines()
    branch_line = status_lines[0] if status_lines else ""
    branch = ""
    ahead = 0
    behind = 0
    has_upstream = False
    if branch_line.startswith("## "):
        header = branch_line[3:]
        branch = header.split("...", 1)[0].strip()
        has_upstream = "..." in header
        if "[" in header and "]" in header:
            summary = header[header.index("[") + 1 : header.index("]")]
            for chunk in summary.split(","):
                token = chunk.strip()
                if token.startswith("ahead "):
                    ahead = int(token.split(" ", 1)[1])
                elif token.startswith("behind "):
                    behind = int(token.split(" ", 1)[1])
    payload["current_branch"] = branch
    payload["has_upstream"] = has_upstream
    payload["ahead"] = ahead
    payload["behind"] = behind
    payload["tracked_changes"] = tracked_changes(
        repo_root=repo_root,
        tracked_paths=git["tracked_paths"],
    )
    payload["recent_commits"] = recent_commits(repo_root=repo_root, limit=recent_limit)
    return payload


def tracked_changes(*, repo_root: str | Path, tracked_paths: list[str]) -> list[dict[str, str]]:
    root = Path(repo_root).resolve()
    raw = _run_git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--",
        *tracked_paths,
    ).stdout
    changes: list[dict[str, str]] = []
    for chunk in raw.split("\0"):
        if len(chunk) < 4:
            continue
        path = chunk[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        changes.append(
            {
                "index_status": chunk[0],
                "worktree_status": chunk[1],
                "path": path,
            }
        )
    return changes


def ensure_tracked_paths_clean(*, repo_root: str | Path, tracked_paths: list[str]) -> None:
    changes = tracked_changes(repo_root=repo_root, tracked_paths=tracked_paths)
    if changes:
        paths = ", ".join(sorted({item["path"] for item in changes}))
        raise GitOperationError(
            f"tracked knowledge files have uncommitted changes: {paths}"
        )


def restore_tracked_paths(*, repo_root: str | Path, tracked_paths: list[str]) -> None:
    root = Path(repo_root).resolve()
    _run_git(root, "restore", "--staged", "--worktree", "--", *tracked_paths)


def recent_commits(*, repo_root: str | Path, limit: int = 12) -> list[dict[str, Any]]:
    root = Path(repo_root).resolve()
    raw = _run_git(
        root,
        "log",
        f"-n{max(1, int(limit))}",
        "--date=iso-strict",
        "--pretty=format:%H%x1f%an%x1f%ae%x1f%ad%x1f%s%x1f%b%x1e",
    ).stdout
    commits: list[dict[str, Any]] = []
    for chunk in raw.split("\x1e"):
        if not chunk.strip():
            continue
        parts = chunk.rstrip("\n").split("\x1f")
        if len(parts) < 6:
            continue
        sha = parts[0].strip()
        if not sha:
            continue
        body = parts[5]
        trailers = _parse_trailers(body)
        operation = trailers.get("Sediment-Operation", "")
        commits.append(
            {
                "sha": sha,
                "author_name": parts[1],
                "author_email": parts[2],
                "authored_at": parts[3],
                "subject": parts[4],
                "body": body,
                "trailers": trailers,
                "sediment_operation": operation,
                "is_sediment_managed": bool(operation),
                "revertible": operation in {"ingest", "tidy"},
            }
        )
    return commits


def commit_tracked_changes(
    *,
    settings: dict[str, Any],
    actor_name: str,
    actor_id: str | None,
    operation: str,
    reason: str,
    extra_trailers: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    git = git_settings_payload(settings)
    repo_root = git["repo_root"]
    _ensure_ready_repo(repo_root)
    tracked = git["tracked_paths"]
    changes = tracked_changes(repo_root=repo_root, tracked_paths=tracked)
    if not changes:
        raise GitOperationError("no tracked changes to commit")
    subject, body = _split_commit_reason(reason)
    trailers = {
        "Sediment-Operation": operation,
        "Sediment-Actor-Id": actor_id or "",
        "Sediment-Actor-Name": actor_name,
    }
    for key, value in (extra_trailers or {}).items():
        if value is not None:
            trailers[key] = value
    message = _compose_commit_message(subject=subject, body=body, trailers=trailers)
    _run_git(repo_root, "add", "--", *tracked)
    _run_git(
        repo_root,
        "commit",
        "-m",
        message,
        "--",
        *tracked,
        env=_author_env(
            actor_name=actor_name,
            actor_id=actor_id,
            git=git,
            system=False,
        ),
    )
    sha = _run_git(repo_root, "rev-parse", "HEAD").stdout.strip()
    return {
        "commit_sha": sha,
        "tracked_changes": changes,
        "recent_commit": recent_commits(repo_root=repo_root, limit=1)[0] if sha else None,
    }


def push_current_branch(*, settings: dict[str, Any]) -> dict[str, Any]:
    git = git_settings_payload(settings)
    repo_root = git["repo_root"]
    _ensure_ready_repo(repo_root)
    branch = _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    upstream = _git_current_upstream(repo_root)
    if not upstream:
        raise GitOperationError("current branch does not have an upstream configured")
    _run_git(repo_root, "push", git["remote_name"], branch)
    return {
        "branch": branch,
        "upstream": upstream,
        "remote_name": git["remote_name"],
    }


def revert_commit(
    *,
    settings: dict[str, Any],
    commit_sha: str,
    actor_name: str,
    actor_id: str | None,
) -> dict[str, Any]:
    git = git_settings_payload(settings)
    repo_root = git["repo_root"]
    _ensure_ready_repo(repo_root)
    try:
        _run_git(
            repo_root,
            "revert",
            "--no-edit",
            commit_sha,
            env=_author_env(
                actor_name=actor_name,
                actor_id=actor_id,
                git=git,
                system=False,
            ),
        )
    except GitOperationError as exc:
        try:
            _run_git(repo_root, "revert", "--abort")
        except GitOperationError:
            pass
        raise GitOperationError(f"git revert failed: {exc}") from exc
    revert_sha = _run_git(repo_root, "rev-parse", "HEAD").stdout.strip()
    return {
        "revert_commit_sha": revert_sha,
        "reverted_commit_sha": commit_sha,
        "recent_commit": recent_commits(repo_root=repo_root, limit=1)[0] if revert_sha else None,
    }


def _split_commit_reason(reason: str) -> tuple[str, str]:
    cleaned = "\n".join(str(reason or "").splitlines()).strip()
    if not cleaned:
        raise GitOperationError("commit reason must not be empty")
    lines = cleaned.splitlines()
    subject = lines[0].strip()
    if not subject:
        raise GitOperationError("commit reason must start with a summary line")
    body = "\n".join(line.rstrip() for line in lines[1:]).strip()
    return subject, body


def _compose_commit_message(
    *,
    subject: str,
    body: str,
    trailers: dict[str, str],
) -> str:
    segments = [subject.strip()]
    if body:
        segments.extend(["", body])
    if trailers:
        segments.append("")
        segments.extend(f"{key}: {value}" for key, value in trailers.items())
    return "\n".join(segments).strip() + "\n"


def _author_env(
    *,
    actor_name: str,
    actor_id: str | None,
    git: dict[str, Any],
    system: bool,
) -> dict[str, str]:
    if system:
        name = git["system_author_name"]
        email = git["system_author_email"]
    else:
        normalized_name = str(actor_name or "").strip() or git["system_author_name"]
        normalized_id = str(actor_id or "").strip()
        name = normalized_name
        email = f"sediment+{normalized_id}@local" if normalized_id else git["system_author_email"]
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = name
    env["GIT_AUTHOR_EMAIL"] = email
    env["GIT_COMMITTER_NAME"] = name
    env["GIT_COMMITTER_EMAIL"] = email
    return env


def _parse_trailers(body: str) -> dict[str, str]:
    trailers: dict[str, str] = {}
    for line in str(body or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            continue
        trailers[key] = value
    return trailers


def _git_current_upstream(repo_root: Path) -> str:
    try:
        return _run_git(repo_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip()
    except GitOperationError:
        return ""


def _ensure_ready_repo(repo_root: Path) -> None:
    if not _is_git_repo(repo_root):
        raise GitOperationError("git repository not found")


def _is_git_repo(repo_root: Path) -> bool:
    try:
        _run_git(repo_root, "rev-parse", "--show-toplevel")
    except GitOperationError:
        return False
    return True


def _run_git(
    repo_root: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed"
        raise GitOperationError(stderr)
    return result
