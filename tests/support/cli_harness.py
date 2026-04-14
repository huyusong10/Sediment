from __future__ import annotations

import sys
from pathlib import Path

from tests.config_helpers import write_test_config
from tests.support.platform_harness import build_platform_project, free_port


def configure_cli_config(tmp_path: Path, *, port: int | None = None) -> Path:
    project_root, kb_path = build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    cli_path = Path(__file__).resolve().parent.parent / "fixtures" / "mock_workflow_cli.py"
    write_test_config(
        project_root,
        kb_path=kb_path,
        state_dir=state_dir,
        agent_backend="claude-code",
        agent_command=[sys.executable, str(cli_path)],
        port=port or free_port(),
        host="127.0.0.1",
        auth_users=[
            {
                "id": "owner",
                "name": "Owner",
                "role": "owner",
                "token": "owner-secret",
                "created_at": "2026-04-15T00:00:00+00:00",
                "disabled": False,
            }
        ],
    )
    return kb_path
