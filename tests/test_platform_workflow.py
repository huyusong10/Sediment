from __future__ import annotations

import base64
import io
import sys
import textwrap
import threading
import time
import zipfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from sediment import agent_runner as agent_runner_module
from sediment import platform_services as platform_services_module
from sediment.control import submit_text_request
from sediment.platform_services import (
    apply_operations,
    build_health_issue_queue,
    detect_submitter_ip,
    inventory,
    parse_trusted_proxy_cidrs,
    resolve_kb_document_path,
)
from sediment.platform_store import PlatformStore
from tests.config_helpers import write_test_config
from tests.support.platform_harness import (
    build_platform_project,
    configure_server,
    write_fixture_text as _write,
)

pytestmark = pytest.mark.integration


def test_portal_text_submission_and_rate_limit(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
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
    assert payload["analysis"]["recommended_type"] == "concept"
    assert payload["analysis"]["related_entries"]

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
    project_root, kb_path = build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, _server_module, worker_module = configure_server(
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


def test_portal_document_archive_submission(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("notes/one.md", "# One\n\n来自 zip 的第一份文档。\n")
        archive.writestr("notes/two.txt", "第二份文本\n")

    response = client.post(
        "/api/portal/submissions/document",
        json={
            "filename": "bundle.zip",
            "mime_type": "application/zip",
            "content_base64": base64.b64encode(bundle.getvalue()).decode("ascii"),
            "submitter_name": "Alice",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["mime_type"] == "application/zip"
    assert payload["title"] == "bundle"
    assert "notes/one.md" in payload["extracted_text"]


def test_ingest_job_review_and_apply_with_symlinked_kb_path(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    linked_kb = tmp_path / "kb-link"
    linked_kb.symlink_to(kb_path, target_is_directory=True)
    state_dir = tmp_path / "state"
    client, _server_module, worker_module = configure_server(
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
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
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


def test_quartz_build_api_serves_site_without_server_restart(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        state_dir,
    )

    runtime_dir = server_module.QUARTZ_RUNTIME_DIR
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "package.json").write_text("{}", encoding="utf-8")
    (runtime_dir / "node_modules").mkdir(exist_ok=True)

    def _fake_quartz_build(**kwargs):
        site_dir = Path(kwargs["site_dir"])
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "index.html").write_text(
            "<html><body>Built Quartz</body></html>",
            encoding="utf-8",
        )
        return server_module.quartz_status(
            runtime_dir=kwargs["runtime_dir"],
            site_dir=kwargs["site_dir"],
        )

    monkeypatch.setattr(server_module, "build_quartz_site", _fake_quartz_build)

    status_before = client.get("/api/admin/quartz/status")
    assert status_before.status_code == 200
    assert status_before.json()["runtime_available"] is True
    assert status_before.json()["site_available"] is False

    build = client.post("/api/admin/quartz/build", json={"actor_name": "tester"})
    assert build.status_code == 202
    assert build.json()["site_available"] is True

    quartz_page = client.get("/quartz/")
    assert quartz_page.status_code == 200
    assert "Built Quartz" in quartz_page.text

    graph_page = client.get("/portal/graph-view")
    assert graph_page.status_code == 200
    assert 'data-testid="portal-open-quartz"' in graph_page.text
    assert 'href="/quartz/"' in graph_page.text
    assert "<iframe" not in graph_page.text


def test_admin_session_cookie_guards_admin_routes(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, server_module, _worker_module = configure_server(
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
    project_root, kb_path = build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, _server_module, _worker_module = configure_server(
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


def test_duplicate_document_submission_keeps_original_upload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )
    monkeypatch.setattr(server_module, "SUBMISSION_RATE_LIMIT_COUNT", 5)

    payload = {
        "filename": "bundle.md",
        "mime_type": "text/markdown",
        "content_base64": base64.b64encode("# Bundle\n\n同一文档重复提交。\n".encode("utf-8")).decode(
            "ascii"
        ),
        "submitter_name": "Alice",
    }

    first = client.post("/api/portal/submissions/document", json=payload)
    assert first.status_code == 201
    stored_path = Path(first.json()["stored_file_path"])
    assert stored_path.exists()

    second = client.post("/api/portal/submissions/document", json=payload)
    assert second.status_code == 409
    assert stored_path.exists()
    assert stored_path.read_text(encoding="utf-8") == "# Bundle\n\n同一文档重复提交。\n"


def test_text_submission_constraints_are_serialized(tmp_path: Path, monkeypatch) -> None:
    store = PlatformStore(tmp_path / "platform.db")
    store.init()
    kb_path = tmp_path / "knowledge-base"
    kb_path.mkdir()
    monkeypatch.setattr(
        platform_services_module,
        "analyze_text_submission",
        lambda **_: {
            "summary": "ok",
            "recommended_title": "并发提交",
            "recommended_type": "concept",
            "duplicate_risk": "medium",
            "committer_action": "manual_review",
            "committer_note": "test",
            "related_entries": [],
        },
    )

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def submit_once() -> None:
        barrier.wait()
        try:
            record = submit_text_request(
                store=store,
                kb_path=kb_path,
                title="并发提交",
                content="两条线程同时提交同一份内容。",
                submitter_name="Alice",
                submitter_ip="198.51.100.10",
                rate_limit_count=1,
                rate_limit_window_seconds=60,
                dedupe_window_seconds=86_400,
            )
        except Exception as exc:  # noqa: BLE001
            outcomes.append(type(exc).__name__)
        else:
            outcomes.append(record["id"])

    threads = [threading.Thread(target=submit_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(outcomes) == 2
    assert len([item for item in outcomes if len(item) == 32]) == 1
    assert outcomes.count("PermissionError") == 1
    assert len(store.list_submissions(limit=10)) == 1


def test_admin_logout_revokes_existing_cookie(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
        admin_token="top-secret",
    )
    app = server_module.create_starlette_app()

    login = client.post("/api/admin/session", json={"token": "top-secret"})
    assert login.status_code == 200
    cookie_name = server_module.ADMIN_SESSION_COOKIE_NAME
    session_cookie = client.cookies.get(cookie_name)
    assert session_cookie

    copied = TestClient(app)
    copied.cookies.set(cookie_name, session_cookie)
    assert copied.get("/api/admin/overview").status_code == 200

    logout = client.delete("/api/admin/session")
    assert logout.status_code == 200
    assert copied.get("/api/admin/overview").status_code == 401


def test_invalid_submission_triage_status_is_rejected(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    submission = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "待归类提案",
            "content": "这条提案只用于 triage 校验。",
            "submitter_name": "Alice",
            "submission_type": "concept",
        },
    ).json()

    response = client.post(
        f"/api/admin/submissions/{submission['id']}/triage",
        json={"status": "totally-invalid"},
    )
    assert response.status_code == 400
    assert client.get(f"/api/admin/submissions/{submission['id']}").json()["submission"][
        "status"
    ] == "pending"


def test_duplicate_ingest_enqueue_returns_conflict(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    submission = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "排队一次即可",
            "content": "重复点击 run-ingest 不应创建多个活动任务。",
            "submitter_name": "Alice",
            "submission_type": "concept",
        },
    ).json()

    first = client.post(f"/api/admin/submissions/{submission['id']}/run-ingest")
    assert first.status_code == 202

    second = client.post(f"/api/admin/submissions/{submission['id']}/run-ingest")
    assert second.status_code == 409

    jobs = client.get(f"/api/admin/submissions/{submission['id']}").json()["jobs"]
    assert len(jobs) == 1


def test_admin_save_missing_entry_returns_404(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    response = client.put(
        "/api/admin/entries/%E4%B8%8D%E5%AD%98%E5%9C%A8%E7%9A%84%E6%9D%A1%E7%9B%AE",
        json={
            "content": "# missing",
            "actor_name": "Committer",
        },
    )
    assert response.status_code == 404


def test_apply_operations_rolls_back_on_failure(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    store = PlatformStore(tmp_path / "platform.db")
    store.init()
    original = (kb_path / "entries" / "热备份.md").read_text(encoding="utf-8")
    real_write = platform_services_module._atomic_write_text

    def flaky_write(path: Path, content: str) -> None:
        if path.name == "新建失败条目.md":
            raise OSError("disk full")
        real_write(path, content)

    monkeypatch.setattr(platform_services_module, "_atomic_write_text", flaky_write)

    with pytest.raises(OSError):
        apply_operations(
            kb_path,
            [
                {
                    "name": "热备份",
                    "relative_path": "entries/热备份.md",
                    "change_type": "update",
                    "content": original.replace("适用于需要连续服务的系统。", "适用于需要连续服务与演练的系统。"),
                },
                {
                    "name": "新建失败条目",
                    "relative_path": "entries/新建失败条目.md",
                    "change_type": "create",
                    "content": textwrap.dedent(
                        """
                        ---
                        type: concept
                        status: fact
                        aliases: []
                        sources:
                          - rollback.md
                        ---
                        # 新建失败条目

                        这条内容会在写入阶段失败。

                        ## Scope
                        用于验证回滚。

                        ## Related
                        - [[热备份]] - 验证回滚
                        """
                    ).strip(),
                },
            ],
            actor_name="Committer",
            actor_role="committer",
            store=store,
        )

    assert (kb_path / "entries" / "热备份.md").read_text(encoding="utf-8") == original
    assert not (kb_path / "entries" / "新建失败条目.md").exists()


def test_duplicate_kb_names_raise_instead_of_overwriting(tmp_path: Path) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    _write(
        kb_path / "entries" / "重名条目.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - duplicate.md
        ---
        # 重名条目

        ## Scope
        正式条目版本。

        ## Related
        - [[热备份]] - 正式
        """,
    )
    _write(
        kb_path / "placeholders" / "重名条目.md",
        """
        ---
        type: placeholder
        aliases: []
        ---
        # 重名条目

        占位版本。
        """,
    )

    with pytest.raises(RuntimeError, match="duplicate knowledge base entry name detected"):
        inventory(kb_path)
    with pytest.raises(RuntimeError, match="multiple knowledge base documents share the same name"):
        resolve_kb_document_path(kb_path, "重名条目")


def test_build_health_issue_queue_handles_dangling_link_shape(tmp_path: Path) -> None:
    _, kb_path = build_platform_project(tmp_path)
    _write(
        kb_path / "entries" / "悬空条目.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - dangling.md
        ---
        # 悬空条目

        这个条目链接到了[[不存在的目标]]。

        ## Scope
        用于验证 health issue 队列。

        ## Related
        - [[热备份]] - 已存在目标
        """,
    )

    issues = build_health_issue_queue(kb_path)

    dangling_issue = next(item for item in issues if item["type"] == "dangling_link")
    assert dangling_issue["target"] == "entries/悬空条目.md"
    assert "不存在的目标" in dangling_issue["summary"]
    assert dangling_issue["evidence"]["link"] == "不存在的目标"


def test_detect_submitter_ip_requires_explicit_proxy_allowlist() -> None:
    headers = {"x-forwarded-for": "203.0.113.10", "x-real-ip": "203.0.113.11"}
    assert (
        detect_submitter_ip(
            headers,
            "10.2.3.4",
            trust_proxy_headers=True,
            trusted_proxy_cidrs=(),
        )
        == "10.2.3.4"
    )


def test_agent_runner_uses_workspace_snapshot_and_cleans_up(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    write_test_config(
        project_root,
        kb_path=kb_path,
        state_dir=state_dir,
        agent_backend="claude-code",
        agent_command=[sys.executable, str(Path(__file__).parent / "fixtures" / "mock_workflow_cli.py")],
    )
    store = PlatformStore(state_dir / "platform.db")
    store.init()
    submission = store.create_submission(
        submission_type="text",
        title="Workspace Draft",
        raw_text="draft body",
        extracted_text="draft body",
        stored_file_path=None,
        mime_type="text/plain",
        submitter_name="Alice",
        submitter_ip="127.0.0.1",
        submitter_user_id=None,
        dedupe_hash="workspace-draft",
    )
    job = store.create_job(
        job_type="ingest",
        source_submission_id=submission["id"],
        target_entry_name=submission["title"],
        status="queued",
        request_payload={"submission_id": submission["id"]},
    )
    runner = agent_runner_module.AgentRunner(
        project_root=project_root,
        kb_path=kb_path,
        workspaces_dir=state_dir / "workspaces",
        store=store,
    )
    real_inventory = agent_runner_module.inventory
    real_target_path = agent_runner_module.determine_target_path
    captured: dict[str, Path] = {}

    def wrapped_inventory(path):
        captured["inventory_path"] = Path(path)
        return real_inventory(path)

    def wrapped_target_path(root, **kwargs):
        captured["target_root"] = Path(root)
        return real_target_path(root, **kwargs)

    def fake_cli_json(*, prompt: str, schema: str, job_id: str, cwd: Path) -> dict[str, Any]:
        captured["cwd"] = Path(cwd)
        return {
            "summary": "ok",
            "warnings": [],
            "drafts": [
                {
                    "name": "Workspace Draft",
                    "entry_type": "concept",
                    "relative_path": "entries/Workspace Draft.md",
                    "rationale": "workspace-only",
                    "content": textwrap.dedent(
                        """
                        ---
                        type: concept
                        status: fact
                        aliases: []
                        sources:
                          - workspace.md
                        ---
                        # Workspace Draft

                        这条草案应该只基于 workspace 快照生成。

                        ## Scope
                        用于验证 runner 的工作目录。

                        ## Related
                        - [[热备份]] - workspace test
                        """
                    ).strip(),
                }
            ],
        }

    monkeypatch.setattr(agent_runner_module, "inventory", wrapped_inventory)
    monkeypatch.setattr(agent_runner_module, "determine_target_path", wrapped_target_path)
    monkeypatch.setattr(runner, "_run_cli_json", fake_cli_json)

    runner._run_ingest(job)

    workspace_root = captured["cwd"]
    assert captured["inventory_path"] == workspace_root / "knowledge-base"
    assert captured["target_root"] == workspace_root / "knowledge-base"
    assert not workspace_root.exists()
    latest_job = store.get_job(job["id"])
    assert latest_job is not None
    assert latest_job["status"] == "awaiting_review"
    assert latest_job["workspace_path"] is None
