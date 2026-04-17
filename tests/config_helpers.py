from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sediment.instances import set_active_registry_path
from sediment.settings import set_active_config_path


def write_test_config(
    root: Path,
    *,
    kb_path: Path,
    state_dir: Path,
    agent_backend: str = "claude-code",
    agent_command: str | list[str] | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    public_base_url: str | None = None,
    locale: str = "en",
    max_attempts: int = 2,
    stale_after_seconds: int = 1,
    instance_label: str = "test-instance",
    knowledge_label: str = "Test Knowledge Base",
    registry_path: Path | None = None,
    auth_users: list[dict[str, Any]] | None = None,
    session_secret: str = "test-session-secret",
) -> Path:
    config_path = root / "config" / "sediment" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": 1,
        "locale": locale,
        "instance": {
            "name": instance_label,
        },
        "paths": {
            "workspace_root": str(root),
            "knowledge_base": str(kb_path),
            "state_dir": str(state_dir),
        },
        "server": {
            "host": host,
            "port": port,
            "sse_path": "/sediment/",
            "public_base_url": public_base_url or "",
            "run_jobs_in_process": False,
        },
        "jobs": {
            "max_attempts": max_attempts,
            "stale_after_seconds": stale_after_seconds,
        },
        "agent": {
            "backend": agent_backend,
            "command": agent_command,
            "doctor_timeout_seconds": 10,
            "exec_timeout_seconds": 20,
        },
        "knowledge": {
            "name": knowledge_label,
        },
        "git": {
            "enabled": True,
            "repo_root": str(root),
            "tracked_paths": ["knowledge-base"],
            "remote_name": "origin",
            "system_author_name": "Sediment System",
            "system_author_email": "sediment-system@local",
        },
    }
    if auth_users is not None:
        payload["auth"] = {
            "users": auth_users,
            "session_secret": session_secret,
            "admin_session_cookie_name": "sediment_admin_session",
            "admin_session_ttl_seconds": 43_200,
            "secure_cookies": False,
        }
    config_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    set_active_registry_path(registry_path or root / ".registry" / "instances.yaml")
    set_active_config_path(config_path)
    return config_path
