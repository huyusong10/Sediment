from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

from sediment import cli
from sediment.instances import unregister_instance
from tests.config_helpers import write_test_config
from tests.test_platform_workflow import _build_platform_project


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _configure_cli(tmp_path: Path, *, port: int | None = None) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    cli_path = Path(__file__).parent / "fixtures" / "mock_workflow_cli.py"
    write_test_config(
        project_root,
        kb_path=kb_path,
        state_dir=state_dir,
        agent_backend="claude-code",
        agent_command=[sys.executable, str(cli_path)],
        host="127.0.0.1",
        port=port or _free_port(),
    )


def test_cli_disorder_stop_before_start_is_idempotent(tmp_path: Path, capsys) -> None:
    _configure_cli(tmp_path)

    rc = cli.main(["server", "stop", "--shutdown-timeout", "1"])

    assert rc == 0
    assert "not running" in capsys.readouterr().out.lower()


def test_cli_disorder_double_start_requires_force(tmp_path: Path, capsys) -> None:
    _configure_cli(tmp_path)

    try:
        first = cli.main(["server", "start", "--no-health-check", "--startup-timeout", "3"])
        assert first == 0
        capsys.readouterr()

        second = cli.main(["server", "start", "--no-health-check", "--startup-timeout", "3"])
        assert second == 1
        err = capsys.readouterr().err.lower()
        assert "already running" in err
    finally:
        cli.main(["server", "stop", "--force-kill", "--shutdown-timeout", "3"])
        capsys.readouterr()


def test_cli_disorder_unlock_all_deleted_without_candidates(tmp_path: Path, capsys) -> None:
    rc = cli.main(
        [
            "instance",
            "unlock",
            "--all-deleted",
            "--search-root",
            str(tmp_path),
            "--force-kill",
        ]
    )

    assert rc == 0
    assert "No unregistered instances" in capsys.readouterr().out


def test_cli_disorder_init_from_existing_kb_root_reuses_current_root(tmp_path: Path, capsys, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    monkeypatch.chdir(kb_path)

    rc = cli.main(["init", "--force", "--json", "--no-interactive"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert Path(payload["instance_root"]).resolve() == project_root.resolve()
    assert Path(payload["knowledge_base_path"]).resolve() == kb_path.resolve()


def test_cli_disorder_quartz_status_build_if_missing_is_safe(tmp_path: Path, capsys) -> None:
    _configure_cli(tmp_path)

    rc = cli.main(["quartz", "status", "--build-if-missing", "--timeout-seconds", "30", "--json"])

    assert rc in {0, 1}
    payload = json.loads(capsys.readouterr().out)
    assert "runtime_available" in payload
    assert "site_available" in payload


def test_cli_disorder_unlock_without_target_returns_hint(capsys) -> None:
    rc = cli.main(["instance", "unlock"])

    assert rc == 1
    assert "Provide `--path" in capsys.readouterr().err


def test_cli_disorder_unlock_by_path_for_unregistered_instance(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    _configure_cli(tmp_path)
    config_path = tmp_path / "project" / "config" / "sediment" / "config.yaml"
    unregister_instance("project")

    monkeypatch.setattr(cli, "_stop_instance_daemon_for_entry", lambda *args, **kwargs: True)

    rc = cli.main(["instance", "unlock", "--path", str(config_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unlocked"] is True
    assert payload["config_path"].endswith("config/sediment/config.yaml")


def test_cli_disorder_quartz_status_build_if_missing_surfaces_build_error(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    _configure_cli(tmp_path)
    monkeypatch.setattr(
        cli,
        "quartz_status",
        lambda **kwargs: {
            "runtime_available": True,
            "runtime_path": str(kwargs["runtime_dir"]),
            "site_available": False,
            "site_path": str(kwargs["site_dir"]),
            "site_index_path": str(Path(kwargs["site_dir"]) / "index.html"),
            "site_last_built_at": None,
        },
    )
    monkeypatch.setattr(
        cli,
        "build_quartz_site",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("build failed for test")),
    )

    rc = cli.main(["quartz", "status", "--build-if-missing"])

    assert rc == 1
    assert "Build error: build failed for test" in capsys.readouterr().err


def test_cli_disorder_unlock_all_includes_registered_instance(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    _configure_cli(tmp_path)
    calls: list[str] = []

    def fake_stop(entry, **kwargs):
        calls.append(str(entry.get("config_path", "")))
        return True

    monkeypatch.setattr(cli, "_stop_instance_daemon_for_entry", fake_stop)

    rc = cli.main(
        [
            "instance",
            "unlock",
            "--all",
            "--search-root",
            str(tmp_path),
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] >= 1
    assert calls


def test_cli_disorder_server_stop_force_kill_when_not_running_is_stable(tmp_path: Path, capsys) -> None:
    _configure_cli(tmp_path)

    rc = cli.main(["server", "stop", "--force-kill", "--shutdown-timeout", "1"])

    assert rc == 0
    assert "not running" in capsys.readouterr().out.lower()
