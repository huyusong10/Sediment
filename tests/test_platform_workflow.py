from __future__ import annotations

import importlib
import sys
import textwrap
import time
from pathlib import Path

from starlette.testclient import TestClient

from mcp_server import server, worker
from mcp_server.platform_services import (
    apply_operations,
    detect_submitter_ip,
    parse_trusted_proxy_cidrs,
)
from mcp_server.platform_store import PlatformStore
from tests.config_helpers import write_test_config


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _build_platform_project(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    kb_path = project_root / "knowledge-base"

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
        - [[薄弱条目]]
        """,
    )
    return project_root, kb_path


def _configure_server(
    monkeypatch,
    project_root: Path,
    kb_path: Path,
    state_dir: Path,
    *,
    admin_token: str = "",
) -> tuple[TestClient, object, object]:
    cli_path = Path(__file__).parent / "fixtures" / "mock_workflow_cli.py"
    write_test_config(
        project_root,
        kb_path=kb_path,
        state_dir=state_dir,
        agent_backend="claude-code",
        agent_command=[sys.executable, str(cli_path)],
    )
    server_module = importlib.reload(server)
    worker_module = importlib.reload(worker)
    monkeypatch.setattr(server_module, "ADMIN_TOKEN", admin_token)
    monkeypatch.setattr(server_module, "SESSION_SECRET", "test-session-secret")
    monkeypatch.setattr(server_module, "RUN_JOBS_IN_PROCESS", False)
    monkeypatch.setattr(server_module, "TRUST_PROXY_HEADERS", False)
    monkeypatch.setattr(server_module, "TRUSTED_PROXY_CIDRS", ())
    monkeypatch.setattr(server_module, "JOB_STALE_AFTER_SECONDS", 1)
    monkeypatch.setattr(server_module, "JOB_MAX_ATTEMPTS", 2)
    app = server_module.create_starlette_app()
    return TestClient(app), server_module, worker_module


def test_portal_text_submission_and_rate_limit(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    response = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "门户提案",
            "content": "这是一条新的概念提案。",
            "submitter_name": "Alice",
            "submission_type": "concept",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["submitter_name"] == "Alice"

    limited = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "第二次提交",
            "content": "同一 IP 一分钟内不应重复提交。",
            "submitter_name": "Alice",
            "submission_type": "concept",
        },
    )
    assert limited.status_code == 429


def test_ingest_job_review_and_apply(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, _server_module, worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        state_dir,
    )

    submission = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "热备份提案",
            "content": "我们需要把热备份相关经验沉淀成概念。",
            "submitter_name": "Alice",
            "submission_type": "concept",
        },
    ).json()

    run = client.post(f"/api/admin/submissions/{submission['id']}/run-ingest")
    assert run.status_code == 202
    job_id = run.json()["id"]

    processed = worker_module.process_queue_until_idle(max_jobs=1)
    assert processed == 1

    for _ in range(10):
        job = client.get(f"/api/admin/jobs/{job_id}").json()
        if job["status"] == "awaiting_review":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("ingest job did not reach awaiting_review")

    reviews = client.get("/api/admin/reviews?decision=pending").json()["reviews"]
    assert reviews
    review_id = reviews[0]["id"]

    approve = client.post(
        f"/api/admin/reviews/{review_id}/approve",
        json={"reviewer_name": "Committer"},
    )
    assert approve.status_code == 200
    apply_result = approve.json()["apply_result"]
    assert apply_result["operations"][0]["change_type"] == "create"

    entry = client.get(
        "/api/portal/entries/"
        "%E7%83%AD%E5%A4%87%E4%BB%BD%E6%8F%90%E4%BA%A4%E8%8D%89%E6%A1%88"
    )
    assert entry.status_code == 200
    assert "热备份提交草案" in entry.json()["content"]


def test_ingest_job_review_and_apply_with_symlinked_kb_path(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    linked_kb = tmp_path / "kb-link"
    linked_kb.symlink_to(kb_path, target_is_directory=True)
    state_dir = tmp_path / "state"
    client, _server_module, worker_module = _configure_server(
        monkeypatch,
        project_root,
        linked_kb,
        state_dir,
    )

    submission = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "热备份提案",
            "content": "我们需要把热备份相关经验沉淀成概念。",
            "submitter_name": "Alice",
            "submission_type": "concept",
        },
    ).json()

    run = client.post(f"/api/admin/submissions/{submission['id']}/run-ingest")
    assert run.status_code == 202
    job_id = run.json()["id"]

    processed = worker_module.process_queue_until_idle(max_jobs=1)
    assert processed == 1

    for _ in range(10):
        job = client.get(f"/api/admin/jobs/{job_id}").json()
        if job["status"] == "awaiting_review":
            break
        time.sleep(0.05)
    else:
        raise AssertionError(f"ingest job did not reach awaiting_review: {job}")

    reviews = client.get("/api/admin/reviews?decision=pending").json()["reviews"]
    assert reviews


def test_admin_save_entry_and_health_issue_queue(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    health = client.get("/api/admin/health/issues")
    assert health.status_code == 200
    issues = health.json()["issues"]
    assert any(item["target"] == "薄弱条目" for item in issues)

    entry = client.get("/api/admin/entries/%E8%96%84%E5%BC%B1%E6%9D%A1%E7%9B%AE").json()
    updated_content = entry["content"].replace(
        "## Related\n- [[暗流]] - 单一关系",
        (
            "## Scope\n适用于结构修复测试。"
            "\n\n## Related\n- [[暗流]] - 单一关系\n- [[回音壁]] - 额外上下文"
        ),
    )
    saved = client.put(
        "/api/admin/entries/%E8%96%84%E5%BC%B1%E6%9D%A1%E7%9B%AE",
        json={
            "content": updated_content,
            "expected_hash": entry["content_hash"],
            "actor_name": "Committer",
        },
    )
    assert saved.status_code == 200

    refreshed = client.get("/api/admin/entries/%E8%96%84%E5%BC%B1%E6%9D%A1%E7%9B%AE").json()
    assert "适用于结构修复测试" in refreshed["content"]
    assert refreshed["validation"]["valid"] is True


def test_admin_session_cookie_guards_admin_routes(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
        admin_token="top-secret",
    )

    page = client.get("/admin")
    assert page.status_code == 200
    assert "Sediment Admin Sign-in" in page.text
    assert 'rel="icon"' in page.text
    assert 'class="brand-mark"' in page.text
    assert page.headers["cache-control"] == "no-store"

    unauthorized = client.get("/api/admin/overview")
    assert unauthorized.status_code == 401

    wrong = client.post("/api/admin/session", json={"token": "wrong"})
    assert wrong.status_code == 401

    login = client.post("/api/admin/session", json={"token": "top-secret"})
    assert login.status_code == 200
    assert client.cookies.get(server_module.ADMIN_SESSION_COOKIE_NAME)

    overview = client.get("/api/admin/overview")
    assert overview.status_code == 200
    assert overview.json()["queued_jobs"] == 0

    authed_page = client.get("/admin")
    assert "Sediment Control Room" in authed_page.text
    assert 'class="brand-mark"' in authed_page.text


def test_detect_submitter_ip_only_trusts_configured_proxy() -> None:
    headers = {"x-forwarded-for": "203.0.113.10", "x-real-ip": "203.0.113.11"}
    trusted = parse_trusted_proxy_cidrs("10.0.0.0/8")

    assert (
        detect_submitter_ip(
            headers,
            "10.2.3.4",
            trust_proxy_headers=True,
            trusted_proxy_cidrs=trusted,
        )
        == "203.0.113.10"
    )
    assert (
        detect_submitter_ip(
            headers,
            "198.51.100.8",
            trust_proxy_headers=True,
            trusted_proxy_cidrs=trusted,
        )
        == "198.51.100.8"
    )


def test_job_cancel_retry_and_stale_recovery(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        state_dir,
    )

    submission = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "需要重试的提案",
            "content": "这条提案先被取消，再重试进入队列。",
            "submitter_name": "Alice",
            "submission_type": "concept",
        },
    ).json()
    enqueued = client.post(f"/api/admin/submissions/{submission['id']}/run-ingest")
    assert enqueued.status_code == 202
    job_id = enqueued.json()["id"]

    cancelled = client.post(
        f"/api/admin/jobs/{job_id}/cancel",
        json={"actor_name": "Committer", "reason": "Queue cleanup"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    retried = client.post(
        f"/api/admin/jobs/{job_id}/retry",
        json={"actor_name": "Committer"},
    )
    assert retried.status_code == 202
    assert retried.json()["status"] == "queued"
    assert retried.json()["attempt_count"] == 0

    store = PlatformStore(state_dir / "platform.db")
    store.init()
    stale_job = store.create_job(
        job_type="tidy",
        target_entry_name="薄弱条目",
        status="running",
        attempt_count=1,
        max_attempts=2,
        request_payload={"issue": {"target": "薄弱条目"}},
    )
    store.update_job(
        stale_job["id"],
        started_at="2000-01-01T00:00:00+00:00",
        last_heartbeat_at="2000-01-01T00:00:00+00:00",
    )
    recovered = store.recover_stale_jobs(stale_after_seconds=1)
    recovered_job = next(item for item in recovered if item["id"] == stale_job["id"])
    assert recovered_job["status"] == "queued"


def test_apply_operations_handles_symlinked_kb_root(tmp_path: Path) -> None:
    real_root = tmp_path / "real-kb"
    real_root.mkdir()
    _write(
        real_root / "entries" / "现有条目.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - smoke.md
        ---
        # 现有条目

        ## Scope
        用于路径解析测试。

        ## Related
        - [[新条目]] - 目标条目
        """,
    )
    symlink_root = tmp_path / "linked-kb"
    symlink_root.symlink_to(real_root, target_is_directory=True)
    store = PlatformStore(tmp_path / "platform.db")
    store.init()

    result = apply_operations(
        symlink_root,
        [
            {
                "name": "新条目",
                "relative_path": "entries/新条目.md",
                "change_type": "create",
                "content": textwrap.dedent(
                    """
                    ---
                    type: concept
                    status: fact
                    aliases: []
                    sources:
                      - smoke.md
                    ---
                    # 新条目

                    新条目用于验证符号链接知识库根目录下的写回路径。

                    ## Scope
                    由符号链接根目录写入。

                    ## Related
                    - [[现有条目]] - 回链
                    """
                ).strip(),
            }
        ],
        actor_name="Committer",
        actor_role="committer",
        store=store,
    )

    assert result["operations"][0]["relative_path"] == "entries/新条目.md"
    assert (real_root / "entries" / "新条目.md").exists()
