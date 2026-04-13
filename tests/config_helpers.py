from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mcp_server.settings import set_active_config_path


def write_test_config(
    root: Path,
    *,
    kb_path: Path,
    state_dir: Path,
    agent_backend: str = "claude-code",
    agent_command: str | list[str] | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    locale: str = "en",
    max_attempts: int = 2,
    stale_after_seconds: int = 1,
) -> Path:
    config_path = root / "config" / "sediment" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": 1,
        "locale": locale,
        "paths": {
            "workspace_root": str(root),
            "knowledge_base": str(kb_path),
            "state_dir": str(state_dir),
        },
        "server": {
            "host": host,
            "port": port,
            "sse_path": "/sediment/",
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
    }
    config_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    set_active_config_path(config_path)
    return config_path
