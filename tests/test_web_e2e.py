from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import yaml

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
    assert page.headers.get("x-request-id")
    assert 'data-testid="portal-search-input"' in page.text
    assert 'data-testid="portal-submit-text-button"' not in page.text
    assert 'href="/tutorial?lang=en"' in page.text
    assert 'href="/quartz/?lang=en" target="_blank" rel="noopener noreferrer"' in page.text
    assert '/portal/graph-view' not in page.text
    assert 'href="/admin' not in page.text
    assert 'data-testid="portal-message"' in page.text
    assert 'data-testid="portal-page-title"' in page.text
    assert 'class="page-title sr-only"' in page.text
    assert 'class="brand-lockup"' in page.text
    assert 'data-shell-header-actions' in page.text
    assert 'data-shell-utility' in page.text
    assert 'class="button nav-link primary"' in page.text
    assert 'class="button utility-action"' not in page.text
    assert 'class="stats stats-inline"' in page.text
    assert 'class="subtle search-status-line"' in page.text
    assert page.text.index('data-testid="portal-stats"') < page.text.index('data-testid="portal-recent-updates"')
    assert page.text.count('href="/submit?lang=en"') == 1
    assert 'class="search-suggestions-popover"' in page.text
    assert 'src="/ui-assets/web-shell.js"' in page.text
    assert 'src="/ui-assets/portal.js"' in page.text
    assert "const UI =" not in page.text
    assert "Browsing stays public and anonymous." not in page.text
    assert "<title>Knowledge base overview | Test Knowledge Base</title>" in page.text

    tutorial_page = client.get("/tutorial", headers={"accept-language": "en-US"})
    assert tutorial_page.status_code == 200
    assert 'data-testid="tutorial-skill-downloads"' in tutorial_page.text
    assert 'data-testid="tutorial-tool-cards"' in tutorial_page.text
    assert 'data-testid="tutorial-decision-cards"' in tutorial_page.text
    assert 'data-testid="tutorial-agent-guides"' in tutorial_page.text
    assert "Connect via MCP" in tutorial_page.text
    assert "http://testserver/sediment/" in tutorial_page.text
    assert "Download SKILL" in tutorial_page.text
    assert "knowledge_ask" in tutorial_page.text
    assert "knowledge_list" in tutorial_page.text
    assert "knowledge_read" in tutorial_page.text
    assert "sediment-mcp-explore-SKILL.md" in tutorial_page.text
    assert "Transport" not in tutorial_page.text
    assert "Public browsing stays anonymous by default" not in tutorial_page.text
    assert "Recommended workflow" not in tutorial_page.text
    assert "from agents import Agent" not in tutorial_page.text
    assert "tools/call knowledge_list {}" not in tutorial_page.text

    skill_download = client.get("/downloads/skills/mcp-explore", headers={"accept-language": "en-US"})
    assert skill_download.status_code == 200
    assert skill_download.headers["content-disposition"] == 'attachment; filename="sediment-mcp-explore-SKILL.md"'
    assert "Sediment MCP Explore Skill" in skill_download.text
    assert "If you only need a fast answer, call `knowledge_ask` directly." in skill_download.text

    submit_page = client.get("/submit", headers={"accept-language": "en-US"})
    assert submit_page.status_code == 200
    assert 'data-testid="portal-page-title"' in submit_page.text
    assert 'data-testid="portal-submit-text-button"' in submit_page.text

    submit_page_zh = client.get("/submit", headers={"accept-language": "zh-CN"})
    assert submit_page_zh.status_code == 200
    assert "文本提交" in submit_page_zh.text
    assert "Text Submission" not in submit_page_zh.text

    search_page = client.get("/search?q=%E7%83%AD%E5%A4%87%E4%BB%BD", headers={"accept-language": "en-US"})
    assert search_page.status_code == 200
    assert 'data-testid="portal-page-title"' in search_page.text
    assert 'data-testid="portal-search-results"' in search_page.text
    assert 'aria-haspopup="listbox"' in search_page.text
    assert "<title>Full-text search | Test Knowledge Base</title>" in search_page.text

    shell_asset = client.get("/ui-assets/web-shell.js")
    assert shell_asset.status_code == 200
    assert "window.SedimentShell" in shell_asset.text

    portal_asset = client.get("/ui-assets/portal.js")
    assert portal_asset.status_code == 200
    assert "loadHome" in portal_asset.text

    home_response = client.get("/api/portal/home")
    assert home_response.headers.get("x-request-id")
    home = home_response.json()
    assert home["counts"]["formal_entries"] >= 2

    suggest = client.get("/api/portal/search/suggest?q=%E7%83%AD%E5%A4%87").json()
    assert any(item["name"] == "热备份" for item in suggest["suggestions"])

    search = client.get("/api/portal/search?q=%E7%83%AD%E5%A4%87%E4%BB%BD").json()
    assert any(item["name"] == "热备份" for item in search)

    created = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "网页提案",
            "content": "这是一条来自知识库界面的提案。",
            "submitter_name": "Alice",
            "submission_type": "concept",
        },
    )
    assert created.status_code == 201
    assert created.headers.get("x-request-id")
    assert created.json()["analysis"]["recommended_type"] == "concept"

    submissions = client.get("/api/admin/submissions").json()["submissions"]
    assert any(item["title"] == "网页提案" for item in submissions)

    quartz_page = client.get("/portal/graph-view", headers={"accept-language": "en-US"})
    assert quartz_page.status_code == 200
    assert "Open Quartz" in quartz_page.text
    assert 'href="/admin/system?lang=en"' in quartz_page.text


def test_portal_default_language_prefers_english_without_zh_signal(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
        locale="zh",
    )

    default_page = client.get("/")
    assert default_page.status_code == 200
    assert '<html lang="en"' in default_page.text
    assert "Knowledge base overview" in default_page.text
    assert "知识库概览" not in default_page.text

    zh_page = client.get("/", headers={"accept-language": "zh-CN"})
    assert zh_page.status_code == 200
    assert '<html lang="zh-CN"' in zh_page.text
    assert "知识库概览" in zh_page.text


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
    assert 'data-testid="admin-page-title"' in login_page.text
    assert 'data-testid="admin-login-token"' in login_page.text
    assert 'data-testid="admin-login-button"' in login_page.text
    assert 'src="/ui-assets/admin-login.js"' in login_page.text
    assert "<title>Admin sign in | Test Knowledge Base</title>" in login_page.text

    login = client.post("/api/admin/session", json={"token": "top-secret"})
    assert login.status_code == 200
    assert client.cookies.get(server_module.ADMIN_SESSION_COOKIE_NAME)

    admin_page = client.get("/admin/overview", headers={"accept-language": "en-US"})
    assert admin_page.status_code == 200
    assert admin_page.headers.get("x-request-id")
    assert 'data-testid="admin-page-title"' in admin_page.text
    assert 'data-testid="admin-message"' in admin_page.text
    assert 'data-testid="admin-stats"' in admin_page.text
    assert 'data-testid="admin-refresh-button"' not in admin_page.text
    assert 'src="/ui-assets/admin.js"' in admin_page.text
    assert "<title>Overview | Test Knowledge Base</title>" in admin_page.text

    kb_page = client.get("/admin/kb", headers={"accept-language": "en-US"})
    assert kb_page.status_code == 200
    assert 'data-testid="admin-submission-list"' in kb_page.text
    assert 'data-testid="admin-ingest-button"' in kb_page.text
    assert 'data-testid="admin-kb-ingest-panel"' in kb_page.text
    assert 'data-testid="admin-kb-tidy-panel"' in kb_page.text
    assert 'data-testid="admin-kb-explore-panel"' in kb_page.text
    assert 'data-testid="admin-kb-live-log"' in kb_page.text
    assert 'data-testid="admin-doc-browser"' not in kb_page.text
    assert 'data-testid="admin-editor-content"' not in kb_page.text

    files_page = client.get("/admin/files", headers={"accept-language": "en-US"})
    assert files_page.status_code == 200
    assert 'data-testid="admin-file-index-tree"' in files_page.text
    assert 'data-testid="admin-file-search"' in files_page.text
    assert 'data-testid="admin-editor-content"' in files_page.text
    assert "<title>File management | Test Knowledge Base</title>" in files_page.text

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
    assert 'data-testid="admin-settings-raw-text"' in system_page.text
    assert 'data-testid="admin-settings-restart-button"' in system_page.text
    assert "<title>Settings | Test Knowledge Base</title>" in system_page.text

    kb_page_zh = client.get("/admin/kb", headers={"accept-language": "zh-CN"})
    assert kb_page_zh.status_code == 200
    assert "<title>知识库管理 | Test Knowledge Base</title>" in kb_page_zh.text
    assert "KB Management 知识库管理" not in kb_page_zh.text
    assert "Ingest 导入" not in kb_page_zh.text
    assert "Tidy 整理" not in kb_page_zh.text
    assert "Explore 探索" not in kb_page_zh.text
    assert ">导入<" in kb_page_zh.text
    assert ">整理<" in kb_page_zh.text
    assert ">探索<" in kb_page_zh.text

    files_page_zh = client.get("/admin/files", headers={"accept-language": "zh-CN"})
    assert files_page_zh.status_code == 200
    assert "<title>文件管理 | Test Knowledge Base</title>" in files_page_zh.text
    assert "Files 文件管理" not in files_page_zh.text
    assert "Files 文件结构" not in files_page_zh.text
    assert "Index 结构浏览" not in files_page_zh.text
    assert "Index 治理约定" not in files_page_zh.text
    assert ">文件结构<" in files_page_zh.text
    assert ">索引结构浏览<" in files_page_zh.text
    assert ">索引治理约定<" in files_page_zh.text

    with client.stream("POST", "/api/admin/explore/live", json={"question": "什么是热备份？"}) as explore_live:
        assert explore_live.status_code == 200
        events = [json.loads(line) for line in explore_live.iter_lines() if line]
    assert any(event["type"] == "command" for event in events)
    assert any(event["type"] == "cli-output" for event in events)
    result_event = next(event for event in events if event["type"] == "result")
    assert "热备份" in result_event["payload"]["answer"]

    kb_documents = client.get("/api/admin/kb/documents")
    assert kb_documents.status_code == 200
    assert kb_documents.json()["counts"]["formal"] >= 2

    files_payload = client.get("/api/admin/files")
    assert files_payload.status_code == 200
    files_data = files_payload.json()
    assert files_data["counts"]["index"] >= 1
    assert files_data["top_indexes"]
    assert "薄弱条目" in files_data["documents_by_name"]

    file_suggestions = client.get("/api/admin/files/suggest?q=%E8%96%84%E5%BC%B1")
    assert file_suggestions.status_code == 200
    assert any(item["name"] == "薄弱条目" for item in file_suggestions.json()["suggestions"])

    settings_payload = client.get("/api/admin/settings/config")
    assert settings_payload.status_code == 200
    settings_data = settings_payload.json()
    assert "raw_text" in settings_data
    config_doc = yaml.safe_load(settings_data["raw_text"])
    config_doc["server"]["public_base_url"] = "https://kb.example.com/app"
    updated_settings = client.put(
        "/api/admin/settings/config",
        json={"raw_text": yaml.safe_dump(config_doc, allow_unicode=True, sort_keys=False)},
    )
    assert updated_settings.status_code == 200
    monkeypatch.setattr(
        server_module,
        "_schedule_admin_restart",
        lambda: {"scheduled": True, "message": "restart scheduled"},
    )
    restart_response = client.post("/api/admin/settings/restart", json={})
    assert restart_response.status_code == 202
    assert restart_response.json()["scheduled"] is True
    tutorial_after_settings = client.get("/tutorial", headers={"accept-language": "en-US"})
    assert "https://kb.example.com/app/sediment/" in tutorial_after_settings.text

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
    assert 'data-testid="portal-entry-page-title"' in entry_page.text
    assert 'data-testid="portal-entry-sections-panel"' in entry_page.text
    assert 'data-testid="portal-entry-signals-panel"' in entry_page.text
    assert "<title>薄弱条目 | Test Knowledge Base</title>" in entry_page.text


def test_admin_explore_public_entrypoints_surface_runtime_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOCK_EXPLORE_INVALID_JSON", "1")
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
    assert client.cookies.get(server_module.ADMIN_SESSION_COOKIE_NAME)

    explore = client.post("/api/admin/explore", json={"question": "什么是热备份？"})
    assert explore.status_code == 502
    payload = explore.json()
    assert "error" in payload
    assert "invalid JSON" in payload["error"]
    assert "answer" not in payload

    with client.stream("POST", "/api/admin/explore/live", json={"question": "什么是热备份？"}) as explore_live:
        assert explore_live.status_code == 200
        events = [json.loads(line) for line in explore_live.iter_lines() if line]

    assert not any(event["type"] == "result" for event in events)
    assert any(event["type"] == "error" and "invalid JSON" in event["message"] for event in events)
    done_event = next(event for event in events if event["type"] == "done")
    assert done_event["ok"] is False


def test_tutorial_endpoint_prefers_proxy_headers_when_trusted(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )
    monkeypatch.setattr(server_module, "TRUST_PROXY_HEADERS", True)

    tutorial_page = client.get(
        "/tutorial",
        headers={
            "accept-language": "en-US",
            "x-forwarded-proto": "https",
            "x-forwarded-host": "kb.example.com",
            "x-forwarded-prefix": "/sediment-ui",
        },
    )
    assert tutorial_page.status_code == 200
    assert "https://kb.example.com/sediment-ui/sediment/" in tutorial_page.text
