from __future__ import annotations

import io
import sys
import threading
from pathlib import Path

from mcp_server import launcher
from tests.config_helpers import write_test_config


def test_validate_environment_reports_missing_inputs(tmp_path: Path, monkeypatch) -> None:
    missing_kb = tmp_path / "missing-kb"
    write_test_config(
        tmp_path,
        kb_path=missing_kb,
        state_dir=tmp_path / "state",
        agent_backend="claude-code",
        agent_command=["definitely-not-a-real-cli"],
    )

    errors = launcher.validate_environment(require_cli=True)

    assert len(errors) == 2
    assert "Configured knowledge_base path does not exist" in errors[0]
    assert "Configured agent backend executable was not found" in errors[1]


def test_build_process_specs_uses_current_python() -> None:
    specs = launcher.build_process_specs(worker_poll_interval=1.5)

    assert specs[0].name == "server"
    assert specs[0].command[:3] == [sys.executable, "-m", "mcp_server.server"]
    assert "--config" in specs[0].command
    assert specs[1].name == "worker"
    assert specs[1].command[:3] == [sys.executable, "-m", "mcp_server.worker"]
    assert specs[1].command[-2:] == ["--poll-interval", "1.5"]


def test_run_managed_processes_starts_and_stops_children(monkeypatch) -> None:
    fixture = Path(__file__).parent / "fixtures" / "mock_managed_service.py"
    stop_event = threading.Event()
    sink = io.StringIO()
    timer = threading.Timer(0.8, stop_event.set)
    timer.start()
    monkeypatch.setenv("MOCK_SERVICE_RUN_SECONDS", "10")

    try:
        rc = launcher.run_managed_processes(
            [
                launcher.ProcessSpec(
                    name="server",
                    command=[sys.executable, str(fixture), "server"],
                ),
                launcher.ProcessSpec(
                    name="worker",
                    command=[sys.executable, str(fixture), "worker"],
                ),
            ],
            sink=sink,
            stop_event=stop_event,
            ready_probe=lambda: True,
        )
    finally:
        timer.cancel()

    output = sink.getvalue()
    assert rc == 0
    assert "[up] Starting server:" in output
    assert "[server] server ready" in output
    assert "[worker] worker ready" in output
    assert "[up] Stopping server..." in output


def test_run_managed_processes_returns_nonzero_when_child_exits_early(monkeypatch) -> None:
    fixture = Path(__file__).parent / "fixtures" / "mock_managed_service.py"
    sink = io.StringIO()
    monkeypatch.setenv("MOCK_SERVER_FAIL_FAST", "1")
    monkeypatch.setenv("MOCK_SERVICE_RUN_SECONDS", "10")

    rc = launcher.run_managed_processes(
        [
            launcher.ProcessSpec(
                name="server",
                command=[sys.executable, str(fixture), "server"],
            ),
            launcher.ProcessSpec(
                name="worker",
                command=[sys.executable, str(fixture), "worker"],
            ),
        ],
        sink=sink,
        ready_probe=lambda: True,
    )

    output = sink.getvalue()
    assert rc == 3
    assert "server exited" in output
    monkeypatch.delenv("MOCK_SERVER_FAIL_FAST", raising=False)
    monkeypatch.delenv("MOCK_SERVICE_RUN_SECONDS", raising=False)
