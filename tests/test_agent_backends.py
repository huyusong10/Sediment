from __future__ import annotations

import asyncio
import importlib
import json
import sys
import textwrap
from pathlib import Path

from sediment import cli, server
from tests.config_helpers import write_test_config


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _build_project(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    kb_path = project_root / "knowledge-base"

    _write(
        project_root / "skills" / "explore" / "SKILL.md",
        """
        ---
        name: test-explore
        ---

        Return JSON only.
        """,
    )
    _write(
        kb_path / "entries" / "热备份.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - backup_design.md
        ---
        # 热备份

        热备份是在故障切换前准备好的可接管能力。

        ## Scope
        适用于需要连续服务的系统。

        ## Related
        - [[回音壁]] - 观测链路
        """,
    )
    _write(
        kb_path / "entries" / "回音壁.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - observability.md
        ---
        # 回音壁

        回音壁负责提供统一观测基线。

        ## Scope
        适用于监控与复盘。

        ## Related
        - [[热备份]] - 观测相关
        """,
    )
    _write(
        kb_path / "index.root.md",
        """
        ---
        kind: index
        segment: root
        last_tidied_at: 2026-04-13
        entry_count: 2
        estimated_tokens: 50
        ---
        # 索引入口

        - [[热备份]]
        """,
    )
    return project_root, kb_path


def _configure_backend(tmp_path: Path, backend: str, fixture_name: str) -> tuple[Path, Path]:
    project_root, kb_path = _build_project(tmp_path)
    command = [sys.executable, str(Path(__file__).parent / "fixtures" / fixture_name)]
    write_test_config(
        project_root,
        kb_path=kb_path,
        state_dir=project_root / ".sediment_state",
        agent_backend=backend,
        agent_command=command,
    )
    return project_root, kb_path


def test_explore_runtime_supports_codex_backend(tmp_path: Path) -> None:
    project_root, kb_path = _configure_backend(tmp_path, "codex", "mock_explore_cli.py")

    server_module = importlib.reload(server)
    server_module._PROJECT_ROOT = project_root
    server_module.KB_PATH = kb_path
    payload = json.loads(asyncio.run(server_module._knowledge_ask("什么是热备份？")))

    assert payload["sources"] == ["热备份"]
    assert payload["confidence"] == "high"


def test_explore_runtime_supports_opencode_backend(tmp_path: Path) -> None:
    project_root, kb_path = _configure_backend(tmp_path, "opencode", "mock_explore_cli.py")

    server_module = importlib.reload(server)
    server_module._PROJECT_ROOT = project_root
    server_module.KB_PATH = kb_path
    payload = json.loads(asyncio.run(server_module._knowledge_ask("什么是热备份？")))

    assert payload["sources"] == ["热备份"]
    assert payload["confidence"] == "high"


def test_doctor_supports_all_configured_backends(tmp_path: Path, capsys) -> None:
    for backend in ("claude-code", "codex", "opencode"):
        _configure_backend(tmp_path / backend, backend, "mock_workflow_cli.py")
        rc = cli.main(["doctor", "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "ok"
        assert payload["backend"] == backend
