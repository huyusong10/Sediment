from __future__ import annotations

import importlib
import subprocess
import sys
import textwrap
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import uvicorn
from starlette.testclient import TestClient

from sediment import server, worker
from sediment.git_ops import write_managed_gitignore
from tests.config_helpers import write_test_config


def write_fixture_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def build_platform_project(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    kb_path = project_root / "knowledge-base"

    write_fixture_text(
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
    write_fixture_text(
        kb_path / "entries" / "薄弱条目.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - weak_note.md
        ---
        # 薄弱条目

        这是一个过于简单的[[暗流]]描述。

        ## Related
        - [[暗流]] - 单一关系
        """,
    )
    write_fixture_text(
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
    write_fixture_text(
        kb_path / "placeholders" / "暗流.md",
        """
        ---
        type: placeholder
        aliases: []
        ---
        # 暗流

        这个概念在知识库中被引用了，但目前还没有足够清晰的定义可供提升。
        """,
    )
    write_fixture_text(
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
        - [[薄弱条目]]
        """,
    )
    write_managed_gitignore(project_root)
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Sediment Tests"], cwd=project_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "sediment-tests@local"], cwd=project_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "--", "knowledge-base", ".gitignore"], cwd=project_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "test fixture"], cwd=project_root, check=True, capture_output=True, text=True)
    return project_root, kb_path


def configure_server(
    monkeypatch,
    project_root: Path,
    kb_path: Path,
    state_dir: Path,
    *,
    admin_token: str = "",
    startup_admin_token: str = "",
    submission_rate_limit_count: int | None = None,
    locale: str = "en",
    public_base_url: str | None = None,
) -> tuple[TestClient, object, object]:
    cli_path = Path(__file__).resolve().parent.parent / "fixtures" / "mock_workflow_cli.py"
    auth_users = None
    if admin_token:
        auth_users = [
            {
                "id": "owner",
                "name": "Owner",
                "role": "owner",
                "token": admin_token,
                "created_at": "2026-04-15T00:00:00+00:00",
                "disabled": False,
            }
        ]
    write_test_config(
        project_root,
        kb_path=kb_path,
        state_dir=state_dir,
        locale=locale,
        public_base_url=public_base_url,
        agent_backend="claude-code",
        agent_command=[sys.executable, str(cli_path)],
        auth_users=auth_users,
        session_secret="test-session-secret",
    )
    server_module = importlib.reload(server)
    worker_module = importlib.reload(worker)
    monkeypatch.setattr(server_module, "SESSION_SECRET", "test-session-secret")
    monkeypatch.setattr(server_module, "RUN_JOBS_IN_PROCESS", False)
    monkeypatch.setattr(server_module, "TRUST_PROXY_HEADERS", False)
    monkeypatch.setattr(server_module, "TRUSTED_PROXY_CIDRS", ())
    monkeypatch.setattr(server_module, "JOB_STALE_AFTER_SECONDS", 1)
    monkeypatch.setattr(server_module, "JOB_MAX_ATTEMPTS", 2)
    if submission_rate_limit_count is not None:
        monkeypatch.setattr(
            server_module,
            "SUBMISSION_RATE_LIMIT_COUNT",
            submission_rate_limit_count,
        )
    app = server_module.create_starlette_app()
    return TestClient(app), server_module, worker_module


@contextmanager
def live_server(
    tmp_path: Path,
    monkeypatch,
    *,
    admin_token: str = "",
    locale: str = "en",
    public_base_url: str | None = None,
):
    project_root, kb_path = build_platform_project(tmp_path)
    port = free_port()
    state_dir = tmp_path / "state"
    cli_path = Path(__file__).resolve().parent.parent / "fixtures" / "mock_workflow_cli.py"
    auth_users = None
    if admin_token:
        auth_users = [
            {
                "id": "owner",
                "name": "Owner",
                "role": "owner",
                "token": admin_token,
                "created_at": "2026-04-15T00:00:00+00:00",
                "disabled": False,
            }
        ]
    write_test_config(
        project_root,
        kb_path=kb_path,
        state_dir=state_dir,
        locale=locale,
        agent_backend="claude-code",
        agent_command=[sys.executable, str(cli_path)],
        host="127.0.0.1",
        port=port,
        public_base_url=public_base_url,
        auth_users=auth_users,
        session_secret="browser-e2e-session",
    )

    server_module = importlib.reload(server)
    worker_module = importlib.reload(worker)
    monkeypatch.setattr(server_module, "SESSION_SECRET", "browser-e2e-session")
    monkeypatch.setattr(server_module, "RUN_JOBS_IN_PROCESS", False)
    monkeypatch.setattr(server_module, "TRUST_PROXY_HEADERS", False)
    monkeypatch.setattr(server_module, "TRUSTED_PROXY_CIDRS", ())
    monkeypatch.setattr(server_module, "JOB_STALE_AFTER_SECONDS", 1)
    monkeypatch.setattr(server_module, "JOB_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(server_module, "SUBMISSION_RATE_LIMIT_COUNT", 3)
    app = server_module.create_starlette_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    live_app = uvicorn.Server(config)
    live_app.install_signal_handlers = lambda: None
    thread = threading.Thread(target=live_app.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=0.5) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.1)
    else:
        live_app.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("Timed out waiting for live Sediment server")

    try:
        yield {
            "base_url": base_url,
            "server_module": server_module,
            "worker_module": worker_module,
        }
    finally:
        live_app.should_exit = True
        thread.join(timeout=5)


def free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
