from __future__ import annotations

import asyncio
import importlib
import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

from sediment import cli
from sediment.instances import register_instance
from sediment.platform_store import PlatformStore
from sediment.settings import current_config_path
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


def test_main_without_args_prints_overview_help(capsys) -> None:
    rc = cli.main([])

    assert rc == 0
    output = capsys.readouterr().out
    assert "Sediment help" in output
    assert "Core workflow:" in output
    assert "sediment instance list" in output


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
    import sediment.server as server_module

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
    assert payload["mode"] == "quick"
    probe = next(item for item in payload["checks"] if item["name"] == "agent.simple_probe")
    assert probe["ok"] is True
    assert any(item["name"] == "paths.registry" for item in payload["checks"])
    assert any(item["name"] == "server.port" for item in payload["checks"])
    assert payload["notes"]


def test_doctor_command_reports_progress_for_humans(tmp_path: Path, capsys) -> None:
    _configure_cli_config(tmp_path)

    rc = cli.main(["doctor"])

    assert rc == 0
    output = capsys.readouterr().out
    assert "[sediment] Running doctor for instance" in output
    assert "[sediment] Checking registry path." in output
    assert "[sediment] Checking knowledge base path." in output
    assert "[sediment] Running simple claude-code generation probe (timeout:" in output


def test_doctor_command_hides_raw_help_output_and_surfaces_summary(tmp_path: Path, capsys) -> None:
    _configure_cli_config(tmp_path)

    rc = cli.main(["doctor"])

    assert rc == 0
    output = capsys.readouterr().out
    assert "mock workflow cli help" not in output
    assert "Help command responded successfully." in output
    assert "mode: quick" in output
    assert "Checks" in output
    assert "agent.help (" in output
    assert "doctor --full" in output


def test_doctor_retries_transient_non_json_probe(monkeypatch, tmp_path: Path) -> None:
    _configure_cli_config(tmp_path)
    progress_messages: list[str] = []
    calls = {"probe": 0}

    def fake_run(command, **kwargs):
        if "--help" in command:
            return SimpleNamespace(returncode=0, stdout="mock help", stderr="")
        calls["probe"] += 1
        if calls["probe"] == 1:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout="OK",
            stderr="",
        )

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    payload = cli.build_doctor_payload(progress=progress_messages.append)

    probe = next(item for item in payload["checks"] if item["name"] == "agent.simple_probe")
    assert payload["status"] == "ok"
    assert probe["ok"] is True
    assert any(
        "Probe returned an empty response; retrying once." in item
        for item in progress_messages
    )


def test_doctor_full_mode_warns_when_structured_probe_is_unstable(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    _configure_cli_config(tmp_path)

    def fake_run(command, **kwargs):
        if "--help" in command:
            return SimpleNamespace(returncode=0, stdout="mock help", stderr="")
        if "--json-schema" in command:
            return SimpleNamespace(returncode=0, stdout="thinking...", stderr="")
        return SimpleNamespace(returncode=0, stdout="OK", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    rc = cli.main(["doctor", "--full", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "warn"
    assert payload["mode"] == "full"
    structured = next(
        item for item in payload["checks"] if item["name"] == "agent.structured_probe"
    )
    assert structured["ok"] is False
    assert structured["severity"] == "warning"


def test_init_registers_multiple_instances(monkeypatch, tmp_path: Path, capsys) -> None:
    registry = tmp_path / "registry" / "instances.yaml"

    first = tmp_path / "first"
    first.mkdir()
    monkeypatch.chdir(first)
    rc = cli.main(
        [
            "--registry",
            str(registry),
            "init",
            "--instance-name",
            "ops-a",
            "--knowledge-name",
            "Ops A",
            "--backend",
            "codex",
            "--json",
        ]
    )
    assert rc == 0
    first_payload = json.loads(capsys.readouterr().out)
    assert Path(first_payload["config_path"]).exists()

    second = tmp_path / "second"
    second.mkdir()
    monkeypatch.chdir(second)
    rc = cli.main(
        [
            "--registry",
            str(registry),
            "init",
            "--instance-name",
            "ops-b",
            "--knowledge-name",
            "Ops B",
            "--backend",
            "codex",
            "--json",
        ]
    )
    assert rc == 0
    capsys.readouterr()

    rc = cli.main(["--registry", str(registry), "instance", "list", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["instance_name"] for item in payload["instances"]] == ["ops-a", "ops-b"]


def test_init_interactive_wizard_collects_defaults_and_overrides(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    registry = tmp_path / "registry" / "instances.yaml"
    workspace = tmp_path / "interactive"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    answers = iter(
        [
            "wizard-test",
            "向导知识库",
            "codex",
            "0.0.0.0",
            "8123",
            "n",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    rc = cli.main(
        [
            "--registry",
            str(registry),
            "init",
            "--interactive",
        ]
    )

    assert rc == 0
    output = capsys.readouterr().out
    assert "Sediment init wizard" in output
    assert "- instance: wizard-test" in output
    assert "- knowledge: 向导知识库" in output
    assert "- backend: codex" in output
    assert "- host: 0.0.0.0" in output
    assert "- port: 8123" in output
    assert "host: 0.0.0.0" in (workspace / "config" / "sediment" / "config.yaml").read_text()
    assert not (workspace / "knowledge-base").exists()


def test_init_command_reports_progress(monkeypatch, tmp_path: Path, capsys) -> None:
    registry = tmp_path / "registry" / "instances.yaml"

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    rc = cli.main(
        [
            "--registry",
            str(registry),
            "init",
            "--instance-name",
            "ops-progress",
            "--knowledge-name",
            "Ops Progress",
            "--backend",
            "codex",
            "--host",
            "0.0.0.0",
            "--no-interactive",
        ]
    )

    assert rc == 0
    output = capsys.readouterr().out
    assert "[sediment] Initializing Sediment instance in" in output
    assert "[sediment] Writing instance scaffold to" in output
    assert "[sediment] Registering instance in the local registry." in output
    assert "- host: 0.0.0.0" in output
    assert "doctor: skipped during init" in output
    assert "run `sediment doctor`" in output


def test_review_commands_and_instance_switching(tmp_path: Path, monkeypatch, capsys) -> None:
    _configure_cli_config(tmp_path)
    config = current_config_path()
    register_instance(
        instance_name="test-instance",
        config_path=config,
        knowledge_name="Test Knowledge Base",
    )
    monkeypatch.chdir(tmp_path)

    rc = cli.main(
        [
            "--instance",
            "test-instance",
            "kb",
            "tidy",
            "薄弱条目",
            "--process-once",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    review_job = payload["job"]
    store = PlatformStore(Path(tmp_path / "state" / "platform.db"))
    store.init()
    review = store.list_reviews(decision="pending")[0]

    rc = cli.main(["--instance", "test-instance", "review", "list", "--json"])
    assert rc == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert list_payload["reviews"][0]["id"] == review["id"]

    rc = cli.main(["--instance", "test-instance", "review", "show", review["id"]])
    assert rc == 0
    shown = capsys.readouterr().out
    assert review["id"] in shown
    assert "diff:" in shown

    rc = cli.main(
        [
            "--instance",
            "test-instance",
            "review",
            "approve",
            review["id"],
            "--reviewer-name",
            "alice",
        ]
    )
    assert rc == 0
    capsys.readouterr()

    assert store.get_job(review_job["id"])["status"] == "succeeded"
    assert store.get_review(review["id"])["decision"] == "approve"


def test_logs_and_help_commands(tmp_path: Path, capsys) -> None:
    _configure_cli_config(tmp_path)
    log_path = cli.daemon_paths()["log"]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                "[server] server ready",
                "[worker] worker boot",
                "[worker] worker idle",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rc = cli.main(["logs", "show", "--component", "worker", "--lines", "2"])
    assert rc == 0
    output = capsys.readouterr().out
    assert "[worker] worker boot" in output
    assert "[server]" not in output

    rc = cli.main(["help", "review"])
    assert rc == 0
    help_output = capsys.readouterr().out
    assert "sediment review" in help_output
    assert "sediment review approve" in help_output


def test_scoped_command_omits_instance_inside_kb_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    kb_path = _configure_cli_config(tmp_path)
    monkeypatch.chdir(kb_path)

    assert cli.scoped_command("doctor") == "sediment doctor"


def test_submit_text_command_and_status_urls(tmp_path: Path, capsys) -> None:
    _configure_cli_config(tmp_path, port=8124)

    rc = cli.main(
        [
            "submit",
            "text",
            "--title",
            "CLI 提案",
            "--content",
            "这是一条来自 CLI 的概念提案。",
            "--type",
            "concept",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["title"] == "CLI 提案"
    assert payload["status"] == "pending"

    rc = cli.main(["status"])
    assert rc == 0
    output = capsys.readouterr().out
    assert "portal:" in output
    assert "admin:" in output
    assert "mcp:" in output

    rc = cli.main(["help", "submit"])
    assert rc == 0
    help_output = capsys.readouterr().out
    assert "sediment submit" in help_output
    assert "submit file" in help_output


def test_submit_file_command_uses_shared_submission_backend(tmp_path: Path, capsys) -> None:
    _configure_cli_config(tmp_path, port=8125)
    note = tmp_path / "submission.md"
    note.write_text("# 故障笔记\n\n这是一个文档提交。\n", encoding="utf-8")

    rc = cli.main(
        [
            "submit",
            "file",
            str(note),
            "--name",
            "alice",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["submission_type"] == "document"
    assert payload["submitter_name"] == "alice"
