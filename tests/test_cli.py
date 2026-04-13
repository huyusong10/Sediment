from __future__ import annotations

import asyncio
import importlib
import json
import socket
import sys
from pathlib import Path

from mcp_server import cli
from mcp_server.platform_store import PlatformStore
from tests.config_helpers import write_test_config


def _configure_cli_config(tmp_path: Path, *, port: int | None = None) -> Path:
    sys.path.append(str(Path(__file__).parent.resolve()))
    from test_platform_workflow import _build_platform_project

    project_root, kb_path = _build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    cli_path = Path(__file__).parent / "fixtures" / "mock_workflow_cli.py"
    write_test_config(
        project_root,
        kb_path=kb_path,
        state_dir=state_dir,
        agent_backend="claude-code",
        agent_command=[sys.executable, str(cli_path)],
        port=port or 8000,
        host="127.0.0.1",
    )
    return kb_path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_status_command_json_reports_platform_state(monkeypatch, tmp_path: Path, capsys) -> None:
    kb_path = _configure_cli_config(tmp_path)

    rc = cli.main(["status", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["paths"]["kb_path"] == str(kb_path.resolve())
    assert payload["daemon"]["running"] is False
    assert payload["queue"]["queued_jobs"] == 0


def test_status_queue_subcommand_json_reports_queue_state(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    _configure_cli_config(tmp_path)

    rc = cli.main(["status", "queue", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["queued_jobs"] == 0
    assert payload["pending_reviews"] == 0


def test_kb_explore_command_json_uses_existing_runtime(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    _configure_cli_config(tmp_path)

    rc = cli.main(["kb", "explore", "热备份是什么", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "热备份" in payload["answer"]
    assert payload["sources"]


def test_kb_tidy_process_once_creates_review(monkeypatch, tmp_path: Path, capsys) -> None:
    _configure_cli_config(tmp_path)

    rc = cli.main(["kb", "tidy", "薄弱条目", "--process-once", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    job = payload["job"]
    assert job["job_type"] == "tidy"
    assert job["status"] == "awaiting_review"

    store = PlatformStore(Path(tmp_path / "state" / "platform.db"))
    store.init()
    reviews = store.list_reviews(decision="pending")
    assert reviews


def test_mcp_status_and_tidy_tools_share_runtime(monkeypatch, tmp_path: Path) -> None:
    kb_path = _configure_cli_config(tmp_path)
    import mcp_server.server as server_module

    server_module = importlib.reload(server_module)

    status_payload = json.loads(
        asyncio.run(server_module._dispatch_tool("knowledge_platform_status", {}))
    )
    assert status_payload["paths"]["kb_path"] == str(kb_path.resolve())
    assert status_payload["queue"]["queued_jobs"] == 0

    tidy_payload = json.loads(
        asyncio.run(
            server_module._dispatch_tool(
                "knowledge_tidy_request",
                {"target": "薄弱条目", "actor_name": "tester"},
            )
        )
    )
    assert tidy_payload["job"]["job_type"] == "tidy"
    assert tidy_payload["issue"]["target"] == "薄弱条目"


def test_server_daemon_lifecycle(monkeypatch, tmp_path: Path, capsys) -> None:
    _configure_cli_config(tmp_path, port=_free_port())

    try:
        start_rc = cli.main(
            [
                "server",
                "start",
                "--startup-timeout",
                "15",
                "--shutdown-timeout",
                "5",
            ]
        )
        assert start_rc == 0
        capsys.readouterr()

        status_rc = cli.main(["server", "status", "--json"])
        assert status_rc == 0
        running_payload = json.loads(capsys.readouterr().out)
        assert running_payload["running"] is True
        assert running_payload["health"]["status"] == "ok"
        assert Path(running_payload["log_path"]).exists()

        stop_rc = cli.main(["server", "stop", "--shutdown-timeout", "10"])
        assert stop_rc == 0
        capsys.readouterr()

        status_after_stop = cli.main(["server", "status", "--json"])
        assert status_after_stop == 0
        stopped_payload = json.loads(capsys.readouterr().out)
        assert stopped_payload["running"] is False
    finally:
        cli.main(["server", "stop", "--shutdown-timeout", "2", "--force-kill"])
        capsys.readouterr()


def test_doctor_command_reports_healthy_backend(tmp_path: Path, capsys) -> None:
    _configure_cli_config(tmp_path)

    rc = cli.main(["doctor", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    probe = next(item for item in payload["checks"] if item["name"] == "agent.probe")
    assert probe["ok"] is True
