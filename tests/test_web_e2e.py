from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.support.platform_harness import build_platform_project, configure_server

pytestmark = pytest.mark.integration


def test_portal_page_e2e_surface_and_submission_flow(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    page = client.get("/", headers={"accept-language": "en-US"})
    assert page.status_code == 200
    assert 'data-testid="portal-search-input"' in page.text
    assert 'data-testid="portal-submit-text-button"' not in page.text
    assert 'href="/quartz/?lang=en"' in page.text
    assert '/portal/graph-view' not in page.text
    assert 'data-testid="portal-message"' in page.text
    assert 'data-shell-header-actions' in page.text
    assert 'data-shell-utility' in page.text
    assert 'class="stats stats-inline"' in page.text
    assert page.text.index('data-testid="portal-stats"') < page.text.index('data-testid="portal-recent-updates"')
    assert page.text.count('href="/submit?lang=en"') == 1
    assert 'class="search-suggestions-popover"' in page.text
    assert 'src="/ui-assets/web-shell.js"' in page.text
    assert 'src="/ui-assets/portal.js"' in page.text
    assert "const UI =" not in page.text
    assert "Browsing stays public and anonymous." not in page.text

    submit_page = client.get("/submit", headers={"accept-language": "en-US"})
    assert submit_page.status_code == 200
    assert 'data-testid="portal-submit-text-button"' in submit_page.text

    submit_page_zh = client.get("/submit", headers={"accept-language": "zh-CN"})
    assert submit_page_zh.status_code == 200
    assert "文本提交" in submit_page_zh.text
    assert "Text Submission" not in submit_page_zh.text

    search_page = client.get("/search?q=%E7%83%AD%E5%A4%87%E4%BB%BD", headers={"accept-language": "en-US"})
    assert search_page.status_code == 200
    assert 'data-testid="portal-search-results"' in search_page.text
    assert 'aria-haspopup="listbox"' in search_page.text

    shell_asset = client.get("/ui-assets/web-shell.js")
    assert shell_asset.status_code == 200
    assert "window.SedimentShell" in shell_asset.text

    portal_asset = client.get("/ui-assets/portal.js")
    assert portal_asset.status_code == 200
    assert "loadHome" in portal_asset.text

    home = client.get("/api/portal/home").json()
    assert home["counts"]["formal_entries"] >= 2

    suggest = client.get("/api/portal/search/suggest?q=%E7%83%AD%E5%A4%87").json()
    assert any(item["name"] == "热备份" for item in suggest["suggestions"])

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
    assert created.json()["analysis"]["recommended_type"] == "concept"

    submissions = client.get("/api/admin/submissions").json()["submissions"]
    assert any(item["title"] == "网页提案" for item in submissions)

    quartz_page = client.get("/portal/graph-view", headers={"accept-language": "en-US"})
    assert quartz_page.status_code == 200
    assert "Open Quartz" in quartz_page.text
    assert 'href="/admin/system?lang=en"' in quartz_page.text


def test_portal_graph_page_uses_new_window_launcher_when_quartz_site_exists(
    tmp_path: Path, monkeypatch
) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )
    quartz_index = server_module.QUARTZ_SITE_DIR / "index.html"
    quartz_index.parent.mkdir(parents=True, exist_ok=True)
    quartz_index.write_text(
        "<!doctype html><html><head><title>Quartz Ready</title></head><body>Quartz Ready</body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(server_module, "_quartz_site_available", lambda: True)

    page = client.get("/portal/graph-view", headers={"accept-language": "en-US"})
    assert page.status_code == 200
    assert "Quartz Ready" in page.text
    assert "/quartz/" in str(page.url)
    assert "<iframe" not in page.text


def test_admin_page_e2e_login_review_and_edit_flow(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, server_module, worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        state_dir,
        admin_token="top-secret",
    )

    login_page = client.get("/admin", headers={"accept-language": "en-US"})
    assert login_page.status_code == 200
    assert 'data-testid="admin-login-token"' in login_page.text
    assert 'data-testid="admin-login-button"' in login_page.text
    assert 'src="/ui-assets/admin-login.js"' in login_page.text

    login = client.post("/api/admin/session", json={"token": "top-secret"})
    assert login.status_code == 200
    assert client.cookies.get(server_module.ADMIN_SESSION_COOKIE_NAME)

    admin_page = client.get("/admin/overview", headers={"accept-language": "en-US"})
    assert admin_page.status_code == 200
    assert 'data-testid="admin-message"' in admin_page.text
    assert 'data-testid="admin-stats"' in admin_page.text
    assert 'data-testid="admin-refresh-button"' not in admin_page.text
    assert 'src="/ui-assets/admin.js"' in admin_page.text

    kb_page = client.get("/admin/kb", headers={"accept-language": "en-US"})
    assert kb_page.status_code == 200
    assert 'data-testid="admin-submission-list"' in kb_page.text
    assert 'data-testid="admin-editor-content"' in kb_page.text

    review_page = client.get("/admin/reviews", headers={"accept-language": "en-US"})
    assert review_page.status_code == 200
    assert 'data-testid="admin-review-list"' in review_page.text
    assert 'data-testid="admin-review-detail-meta"' in review_page.text
    assert 'data-testid="admin-review-comment"' in review_page.text

    users_page = client.get("/admin/users", headers={"accept-language": "en-US"})
    assert users_page.status_code == 200
    assert 'data-testid="admin-user-list"' in users_page.text
    assert 'data-testid="admin-user-token-view"' not in users_page.text
    assert 'id="user-role"' not in users_page.text

    system_page = client.get("/admin/system", headers={"accept-language": "en-US"})
    assert system_page.status_code == 200
    assert 'data-testid="admin-system-status"' in system_page.text

    owner_create = client.post("/api/admin/users", json={"name": "Spare Owner", "role": "owner"})
    assert owner_create.status_code == 400

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
        },
    )
    assert saved.status_code == 200

    portal_entry = client.get("/api/portal/entries/%E8%96%84%E5%BC%B1%E6%9D%A1%E7%9B%AE").json()
    assert "适用于网页 E2E 编辑" in portal_entry["content"]
    assert any(section["name"] == "Scope" for section in portal_entry["structured"]["canonical_sections"])

    entry_page = client.get("/entries/%E8%96%84%E5%BC%B1%E6%9D%A1%E7%9B%AE", headers={"accept-language": "en-US"})
    assert entry_page.status_code == 200
    assert 'data-testid="portal-entry-sections-panel"' in entry_page.text
    assert 'data-testid="portal-entry-signals-panel"' in entry_page.text
