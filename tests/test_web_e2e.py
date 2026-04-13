from __future__ import annotations

import time
from pathlib import Path

from tests.test_platform_workflow import _build_platform_project, _configure_server


def test_portal_page_e2e_surface_and_submission_flow(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    page = client.get("/portal")
    assert page.status_code == 200
    assert 'data-testid="portal-search-input"' in page.text
    assert 'data-testid="portal-submit-text-button"' in page.text
    assert 'data-testid="portal-graph"' in page.text
    assert 'data-testid="portal-message"' in page.text

    home = client.get("/api/portal/home").json()
    assert home["counts"]["formal_entries"] >= 2

    search = client.get("/api/portal/search?q=%E7%83%AD%E5%A4%87%E4%BB%BD").json()
    assert any(item["name"] == "热备份" for item in search)

    created = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "网页提案",
            "content": "这是一条来自门户的提案。",
            "submitter_name": "Alice",
            "submission_type": "concept",
        },
    )
    assert created.status_code == 201

    submissions = client.get("/api/admin/submissions").json()["submissions"]
    assert any(item["title"] == "网页提案" for item in submissions)


def test_admin_page_e2e_login_review_and_edit_flow(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, server_module, worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        state_dir,
        admin_token="top-secret",
    )

    login_page = client.get("/admin")
    assert login_page.status_code == 200
    assert 'data-testid="admin-login-token"' in login_page.text
    assert 'data-testid="admin-login-button"' in login_page.text

    login = client.post("/api/admin/session", json={"token": "top-secret"})
    assert login.status_code == 200
    assert client.cookies.get(server_module.ADMIN_SESSION_COOKIE_NAME)

    admin_page = client.get("/admin")
    assert admin_page.status_code == 200
    assert 'data-testid="admin-message"' in admin_page.text
    assert 'data-testid="admin-submission-list"' in admin_page.text
    assert 'data-testid="admin-editor-content"' in admin_page.text

    submission = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "管理台提案",
            "content": "需要进入 ingest 和 review 的网页流转。",
            "submitter_name": "Alice",
            "submission_type": "concept",
        },
    ).json()

    enqueued = client.post(f"/api/admin/submissions/{submission['id']}/run-ingest")
    assert enqueued.status_code == 202
    job_id = enqueued.json()["id"]

    assert worker_module.process_queue_until_idle(max_jobs=1) == 1

    for _ in range(10):
        job = client.get(f"/api/admin/jobs/{job_id}").json()
        if job["status"] == "awaiting_review":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("job did not reach awaiting_review")

    reviews = client.get("/api/admin/reviews?decision=pending").json()["reviews"]
    review_id = reviews[0]["id"]
    review_detail = client.get(f"/api/admin/reviews/{review_id}")
    assert review_detail.status_code == 200
    assert review_detail.json()["review"]["id"] == review_id

    approved = client.post(
        f"/api/admin/reviews/{review_id}/approve",
        json={"reviewer_name": "Committer"},
    )
    assert approved.status_code == 200

    entry = client.get("/api/admin/entries/%E8%96%84%E5%BC%B1%E6%9D%A1%E7%9B%AE").json()
    updated_content = entry["content"].replace(
        "## Related\n- [[暗流]] - 单一关系",
        "## Scope\n适用于网页 E2E 编辑。\n\n## Related\n- [[暗流]] - 单一关系",
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

    portal_entry = client.get("/api/portal/entries/%E8%96%84%E5%BC%B1%E6%9D%A1%E7%9B%AE").json()
    assert "适用于网页 E2E 编辑" in portal_entry["content"]
