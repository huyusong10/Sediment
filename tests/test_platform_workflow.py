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


def _upload_document_to_inbox(
    client: TestClient,
    *,
    filename: str = "bundle.md",
    mime_type: str = "text/markdown",
    content: str = "# Bundle\n\n同一文档重复提交。\n",
    submitter_name: str = "Alice",
) -> dict[str, object]:
    response = client.post(
        "/api/portal/submissions/document",
        json={
            "filename": filename,
            "mime_type": mime_type,
            "content_base64": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "submitter_name": submitter_name,
        },
    )
    assert response.status_code == 201
    return response.json()["item"]


def _create_ready_ingest_batch(client: TestClient) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    staged_item = _upload_document_to_inbox(client)
    ready = client.post(
        f"/api/admin/inbox/document/{staged_item['id']}/mark-ready",
        json={"version": staged_item["version"]},
    )
    assert ready.status_code == 200
    ready_item = ready.json()["item"]
    batch_response = client.post(
        "/api/admin/inbox/ingest-batches",
        json={"items": [{"id": ready_item["id"], "version": ready_item["version"]}]},
    )
    assert batch_response.status_code == 201
    return staged_item, ready_item, batch_response.json()["batch"]


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
    assert payload["status"] == "open"
    assert payload["item"]["submitter_name"] == "Alice"
    assert payload["item"]["item_type"] == "text_feedback"
    assert payload["item"]["body_text"] == "这是一条新的概念提案。"

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


def test_portal_text_submission_rejects_malformed_json_body(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    response = client.post(
        "/api/portal/submissions/text",
        content="{",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "request body must be a valid UTF-8 JSON object"
    inbox = client.get("/api/admin/inbox").json()["items"]
    assert all(not items for items in inbox.values())


def test_ingest_batch_auto_commits_and_updates_inbox_history(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, _server_module, worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        state_dir,
    )

    staged_item, ready_item, batch = _create_ready_ingest_batch(client)
    run = client.post("/api/admin/ingest/document", json={"ingest_batch_id": batch["id"]})
    assert run.status_code == 202
    job_id = run.json()["job"]["id"]

    processed = worker_module.process_queue_until_idle(max_jobs=1)
    assert processed == 1

    for _ in range(10):
        job = client.get(f"/api/admin/jobs/{job_id}").json()
        if job["status"] == "succeeded":
            break
        time.sleep(0.05)
    else:
        raise AssertionError(f"ingest job did not succeed: {job}")

    assert job["commit_sha"]
    assert job["result_payload"]["commit_sha"] == job["commit_sha"]
    assert job["result_payload"]["apply_result"]["operations"][0]["change_type"] == "create"

    inbox = client.get("/api/admin/inbox").json()
    history_ids = {item["id"]: item for item in inbox["items"]["history_documents"]}
    assert staged_item["id"] in history_ids
    assert history_ids[staged_item["id"]]["status"] == "ingested"
    assert history_ids[staged_item["id"]]["commit_sha"] == job["commit_sha"]

    version_status = client.get("/api/admin/version/status").json()
    assert version_status["recent_commits"][0]["sha"] == job["commit_sha"]
    assert version_status["recent_commits"][0]["revertible"] is True

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
    assert payload["status"] == "staged"
    assert payload["item"]["mime_type"] == "application/zip"
    assert payload["item"]["title"] == "bundle"
    assert Path(payload["item"]["stored_file_path"]).exists()


def test_portal_document_submission_rejects_mixed_payload_without_creating_item(
    tmp_path: Path, monkeypatch
) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    response = client.post(
        "/api/portal/submissions/document",
        json={
            "filename": "bundle.txt",
            "mime_type": "text/plain",
            "content_base64": base64.b64encode("inline\n".encode("utf-8")).decode("ascii"),
            "files": [
                {
                    "filename": "nested.txt",
                    "content_base64": base64.b64encode("nested\n".encode("utf-8")).decode(
                        "ascii"
                    ),
                }
            ],
            "submitter_name": "Alice",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["error"]
        == "document payload must provide either content_base64 or files, not both"
    )
    inbox = client.get("/api/admin/inbox").json()["items"]
    assert all(not items for items in inbox.values())


def test_admin_direct_ingest_upload_enqueues_job_from_uploaded_files(
    tmp_path: Path, monkeypatch
) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, _server_module, worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        state_dir,
    )

    response = client.post(
        "/api/admin/ingest/document",
        json={
            "filename": "admin-upload-bundle.zip",
            "mime_type": "application/zip",
            "files": [
                {
                    "filename": "admin-upload.md",
                    "content_base64": base64.b64encode(
                        "# Admin Upload\n\n这是一份后台直接导入文档。\n".encode("utf-8")
                    ).decode("ascii"),
                }
            ],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["item"]["item_type"] == "uploaded_document"
    assert payload["item"]["status"] == "ingesting"
    assert payload["submission"]["id"] == payload["item"]["id"]
    assert payload["batch"]["id"] == payload["job"]["source_batch_id"]

    processed = worker_module.process_queue_until_idle(max_jobs=1)
    assert processed == 1

    job_id = payload["job"]["id"]
    for _ in range(10):
        job = client.get(f"/api/admin/jobs/{job_id}").json()
        if job["status"] == "succeeded":
            break
        time.sleep(0.05)
    else:
        raise AssertionError(f"admin direct upload job did not succeed: {job}")

    inbox = client.get("/api/admin/inbox").json()["items"]["history_documents"]
    history_item = next(item for item in inbox if item["id"] == payload["item"]["id"])
    assert history_item["status"] == "ingested"
    assert history_item["job_id"] == job_id


def test_admin_direct_ingest_upload_rejects_partially_invalid_bundle_without_side_effects(
    tmp_path: Path, monkeypatch
) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        state_dir,
    )

    response = client.post(
        "/api/admin/ingest/document",
        json={
            "files": [
                {
                    "filename": "valid.md",
                    "content_base64": base64.b64encode("# Valid\n\nok\n".encode("utf-8")).decode(
                        "ascii"
                    ),
                },
                {
                    "filename": "broken.md",
                    "content_base64": "   ",
                },
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"] == "files[2].content_base64 must not be empty"
    assert client.get("/api/admin/jobs").json()["jobs"] == []
    inbox = client.get("/api/admin/inbox").json()["items"]
    assert all(not items for items in inbox.values())


def test_ingest_batch_auto_commits_with_symlinked_kb_path(tmp_path: Path, monkeypatch) -> None:
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

    _staged_item, _ready_item, batch = _create_ready_ingest_batch(client)
    run = client.post("/api/admin/ingest/document", json={"ingest_batch_id": batch["id"]})
    assert run.status_code == 202
    job_id = run.json()["job"]["id"]

    processed = worker_module.process_queue_until_idle(max_jobs=1)
    assert processed == 1

    for _ in range(10):
        job = client.get(f"/api/admin/jobs/{job_id}").json()
        if job["status"] == "succeeded":
            break
        time.sleep(0.05)
    else:
        raise AssertionError(f"ingest job did not succeed: {job}")

    assert job["commit_sha"]
    assert (kb_path / "entries" / "热备份提交草案.md").exists()


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


def test_admin_file_management_payload_and_restart_api(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
        admin_token="top-secret",
    )

    login = client.post("/api/admin/session", json={"token": "top-secret"})
    assert login.status_code == 200

    files_payload = client.get("/api/admin/files")
    assert files_payload.status_code == 200
    payload = files_payload.json()
    assert payload["top_indexes"]
    assert payload["documents_by_name"]["热备份"]["group"] == "formal"
    assert payload["documents_by_name"]["index.root"]["group"] == "index"

    suggestions = client.get("/api/admin/files/suggest?q=%E7%83%AD%E5%A4%87")
    assert suggestions.status_code == 200
    assert any(item["name"] == "热备份" for item in suggestions.json()["suggestions"])

    monkeypatch.setattr(
        server_module,
        "_schedule_admin_restart",
        lambda: {"scheduled": True, "message": "restart scheduled"},
    )
    restart = client.post("/api/admin/settings/restart", json={})
    assert restart.status_code == 202
    assert restart.json()["scheduled"] is True


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
        static_dir = site_dir / "static"
        entry_dir = site_dir / "entries"
        site_dir.mkdir(parents=True, exist_ok=True)
        static_dir.mkdir(parents=True, exist_ok=True)
        entry_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "index.html").write_text(
            "<html><body>Built Quartz</body></html>",
            encoding="utf-8",
        )
        (site_dir / "postscript.js").write_text("console.log('graph-ready')", encoding="utf-8")
        (site_dir / "prescript.js").write_text("window.__quartz = true", encoding="utf-8")
        (static_dir / "contentIndex.json").write_text(
            '{"entries/test-entry":{"title":"Built Quartz"}}',
            encoding="utf-8",
        )
        (entry_dir / "test-entry.html").write_text(
            "<html><body>Test Entry</body></html>",
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
    assert "worker-src 'self' blob:" in quartz_page.headers["content-security-policy"]
    assert (
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https: blob:"
        in quartz_page.headers["content-security-policy"]
    )

    quartz_postscript = client.get("/quartz/postscript.js")
    assert quartz_postscript.status_code == 200
    assert "graph-ready" in quartz_postscript.text

    quartz_index = client.get("/quartz/static/contentIndex.json")
    assert quartz_index.status_code == 200
    assert quartz_index.json()["entries/test-entry"]["title"] == "Built Quartz"

    quartz_entry = client.get("/quartz/entries/test-entry")
    assert quartz_entry.status_code == 200
    assert "Test Entry" in quartz_entry.text

    graph_page = client.get("/portal/graph-view")
    assert graph_page.status_code == 200
    assert "Built Quartz" in graph_page.text
    assert "/quartz/" in str(graph_page.url)


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
    assert 'data-testid="admin-login-token"' in page.text
    assert 'data-testid="admin-login-button"' in page.text
    assert 'rel="icon"' in page.text
    assert 'class="brand-lockup"' in page.text
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
    assert 'data-testid="admin-message"' in authed_page.text
    assert 'data-testid="admin-refresh-button"' not in authed_page.text
    assert 'class="brand-lockup"' in authed_page.text


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

    enqueued = client.post(
        "/api/admin/tidy",
        json={"scope": "graph", "reason": "这条任务先被取消，再重试进入队列。"},
    )
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


def test_admin_tidy_rejects_empty_reason_and_unknown_scope_without_enqueuing(
    tmp_path: Path, monkeypatch
) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    empty_reason = client.post(
        "/api/admin/tidy",
        json={"scope": "graph", "reason": "   "},
    )
    assert empty_reason.status_code == 400
    assert empty_reason.json()["error"] == "reason must not be empty"

    invalid_scope = client.post(
        "/api/admin/tidy",
        json={"scope": "graph-only", "reason": "Repair graph issues."},
    )
    assert invalid_scope.status_code == 400
    assert invalid_scope.json()["error"] == "unsupported tidy scope: graph-only"
    assert client.get("/api/admin/jobs").json()["jobs"] == []


def test_admin_version_commit_rejects_empty_reason_before_claiming_repo_lock(
    tmp_path: Path, monkeypatch
) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    store = server_module._platform_store()

    def fail_claim_repo_lock(**_kwargs):
        raise AssertionError("repo lock should not be claimed for an empty reason")

    monkeypatch.setattr(store, "claim_repo_lock", fail_claim_repo_lock)

    response = client.post(
        "/api/admin/version/commit",
        json={"reason": "   "},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "reason must not be empty"


def test_admin_review_approve_rejects_non_approval_decision_without_mutating_review(
    tmp_path: Path, monkeypatch
) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        state_dir,
    )

    store = PlatformStore(state_dir / "platform.db")
    store.init()
    job = store.create_job(
        job_type="ingest",
        target_entry_name="待审条目",
        status="awaiting_review",
        max_attempts=2,
        request_payload={"operations": []},
    )
    review = store.create_review(
        job_id=job["id"],
        submission_id=None,
        review_type="formal_entry_patch",
    )

    response = client.post(
        f"/api/admin/reviews/{review['id']}/approve",
        json={"decision": "reject", "comment": "This should not pass through approve."},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "unsupported approval decision: reject"

    current_review = store.get_review(review["id"])
    current_job = store.get_job(job["id"])
    assert current_review is not None and current_review["decision"] == "pending"
    assert current_job is not None and current_job["status"] == "awaiting_review"


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
    stored_path = Path(first.json()["item"]["stored_file_path"])
    assert stored_path.exists()

    second = client.post("/api/portal/submissions/document", json=payload)
    assert second.status_code == 409
    assert stored_path.exists()
    assert stored_path.read_text(encoding="utf-8") == "# Bundle\n\n同一文档重复提交。\n"


def test_text_feedback_constraints_are_serialized(tmp_path: Path, monkeypatch) -> None:
    store = PlatformStore(tmp_path / "platform.db")
    store.init()
    kb_path = tmp_path / "knowledge-base"
    kb_path.mkdir()

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
    assert len(store.list_inbox_items(limit=10)) == 1


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


def test_inbox_document_state_conflict_returns_409(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    staged_item = _upload_document_to_inbox(client)
    first = client.post(
        f"/api/admin/inbox/document/{staged_item['id']}/mark-ready",
        json={"version": staged_item["version"]},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/admin/inbox/document/{staged_item['id']}/mark-ready",
        json={"version": staged_item["version"]},
    )
    assert second.status_code == 409


def test_inbox_document_mark_ready_rejects_malformed_json_without_mutating_state(
    tmp_path: Path, monkeypatch
) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    staged_item = _upload_document_to_inbox(client)
    invalid = client.post(
        f"/api/admin/inbox/document/{staged_item['id']}/mark-ready",
        content="{",
        headers={"content-type": "application/json"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"] == "request body must be a valid UTF-8 JSON object"

    ready = client.post(
        f"/api/admin/inbox/document/{staged_item['id']}/mark-ready",
        json={"version": staged_item["version"]},
    )
    assert ready.status_code == 200
    assert ready.json()["item"]["status"] == "ready"


def test_inbox_document_mark_ready_requires_valid_version(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    staged_item = _upload_document_to_inbox(client)

    missing = client.post(
        f"/api/admin/inbox/document/{staged_item['id']}/mark-ready",
        json={},
    )
    assert missing.status_code == 400
    assert missing.json()["error"] == "version is required"

    invalid = client.post(
        f"/api/admin/inbox/document/{staged_item['id']}/mark-ready",
        json={"version": "abc"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"] == "version must be an integer"

    too_small = client.post(
        f"/api/admin/inbox/document/{staged_item['id']}/mark-ready",
        json={"version": 0},
    )
    assert too_small.status_code == 400
    assert too_small.json()["error"] == "version must be >= 1"

    ready = client.post(
        f"/api/admin/inbox/document/{staged_item['id']}/mark-ready",
        json={"version": staged_item["version"]},
    )
    assert ready.status_code == 200


def test_feedback_resolve_requires_version_and_preserves_open_state(
    tmp_path: Path, monkeypatch
) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    feedback = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "需要人工处理",
            "content": "请先验证并发保护。",
            "submitter_name": "Alice",
        },
    ).json()["item"]

    response = client.post(
        f"/api/admin/inbox/text/{feedback['id']}/resolve",
        json={"version": "abc"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "version must be an integer"

    inbox = client.get("/api/admin/inbox").json()["items"]
    assert any(item["id"] == feedback["id"] for item in inbox["open_feedback"])
    assert all(item["id"] != feedback["id"] for item in inbox["resolved_feedback"])


def test_ingest_batch_creation_requires_item_versions(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    staged_item = _upload_document_to_inbox(client)
    ready = client.post(
        f"/api/admin/inbox/document/{staged_item['id']}/mark-ready",
        json={"version": staged_item["version"]},
    )
    assert ready.status_code == 200
    ready_item = ready.json()["item"]

    missing = client.post(
        "/api/admin/inbox/ingest-batches",
        json={"items": [{"id": ready_item["id"]}]},
    )
    assert missing.status_code == 400
    assert missing.json()["error"] == "version is required"

    invalid = client.post(
        "/api/admin/inbox/ingest-batches",
        json={"items": [{"id": ready_item["id"], "version": "abc"}]},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"] == "version must be an integer"

    created = client.post(
        "/api/admin/inbox/ingest-batches",
        json={"items": [{"id": ready_item["id"], "version": ready_item["version"]}]},
    )
    assert created.status_code == 201


def test_duplicate_ingest_batch_creation_returns_conflict(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    staged_item = _upload_document_to_inbox(client)
    ready = client.post(
        f"/api/admin/inbox/document/{staged_item['id']}/mark-ready",
        json={"version": staged_item["version"]},
    )
    assert ready.status_code == 200
    ready_item = ready.json()["item"]

    first = client.post(
        "/api/admin/inbox/ingest-batches",
        json={"items": [{"id": ready_item["id"], "version": ready_item["version"]}]},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/admin/inbox/ingest-batches",
        json={"items": [{"id": ready_item["id"], "version": ready_item["version"]}]},
    )
    assert second.status_code == 409


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


def test_admin_save_entry_rejects_non_object_json_body(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    entry = client.get("/api/admin/entries/%E7%83%AD%E5%A4%87%E4%BB%BD").json()
    response = client.put(
        "/api/admin/entries/%E7%83%AD%E5%A4%87%E4%BB%BD",
        content="[]",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "request body must be a JSON object"
    assert client.get("/api/admin/entries/%E7%83%AD%E5%A4%87%E4%BB%BD").json()["content"] == entry["content"]


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
    assert latest_job["status"] == "succeeded"
    assert latest_job["commit_sha"]
    assert latest_job["workspace_path"] is None
