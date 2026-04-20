from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

from tests.support.platform_harness import build_platform_project, configure_server

pytestmark = pytest.mark.integration


def _extract_page_data(page_html: str) -> dict[str, object]:
    match = re.search(
        r'<script id="sediment-page-data" type="application/json">(.*?)</script>',
        page_html,
        re.S,
    )
    assert match, "Missing sediment-page-data payload."
    return json.loads(match.group(1))


def _extract_ui_keys(asset_text: str) -> set[str]:
    return set(re.findall(r"UI\.([A-Za-z0-9_]+)", asset_text))


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
    assert 'href="/admin' not in page.text
    assert 'data-testid="portal-message"' in page.text
    assert 'data-testid="portal-page-title"' in page.text
    assert 'class="page-title sr-only"' in page.text
    assert 'class="brand-lockup"' in page.text
    assert 'data-shell-header-actions' in page.text
    assert 'data-shell-utility' in page.text
    assert 'data-shell-nav-link="true"' in page.text
    assert 'aria-current="page"' in page.text
    assert 'class="button nav-link primary"' in page.text
    assert 'class="button utility-action"' not in page.text
    assert 'class="stats stats-inline"' in page.text
    assert 'class="subtle search-status-line"' in page.text
    assert 'data-testid="portal-home-graph-layout"' in page.text
    assert 'data-testid="portal-home-graph"' in page.text
    assert 'data-testid="portal-universe-strip"' in page.text
    assert 'data-testid="portal-recent-updates"' not in page.text
    assert page.text.count('href="/submit?lang=en"') == 1
    assert 'href="/portal/graph-view?lang=en"' in page.text
    assert "Open universe" in page.text
    assert 'class="search-suggestions-popover"' in page.text
    assert 'src="/ui-assets/web-shell.js"' in page.text
    assert 'src="/ui-assets/portal.js"' in page.text
    assert 'src="/ui-assets/graph.bundle.js"' in page.text
    assert 'href="/ui-assets/graph.bundle.css"' in page.text
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
    assert 'data-testid="portal-submit-name"' in submit_page.text
    assert 'data-testid="portal-submit-title"' in submit_page.text
    assert 'data-testid="portal-submit-content"' in submit_page.text
    assert 'data-testid="portal-upload-file-selection"' in submit_page.text
    assert "Choose files" in submit_page.text
    assert "Choose folder" in submit_page.text
    assert "No files selected" in submit_page.text
    assert "No folder selected" in submit_page.text
    assert "未选择文件" not in submit_page.text

    submit_page_zh = client.get("/submit", headers={"accept-language": "zh-CN"})
    assert submit_page_zh.status_code == 200
    assert "文本意见" in submit_page_zh.text
    assert "Text submission" not in submit_page_zh.text

    search_page = client.get("/search?q=%E7%83%AD%E5%A4%87%E4%BB%BD", headers={"accept-language": "en-US"})
    assert search_page.status_code == 200
    assert 'data-testid="portal-page-title"' in search_page.text
    assert 'data-testid="portal-search-results"' in search_page.text
    assert 'class="list section-gap-md"' in search_page.text
    assert 'style="margin-top:18px;"' not in search_page.text
    assert 'aria-haspopup="listbox"' in search_page.text
    assert "<title>Full-text search | Test Knowledge Base</title>" in search_page.text

    shell_asset = client.get("/ui-assets/web-shell.js")
    assert shell_asset.status_code == 200
    assert "window.SedimentShell" in shell_asset.text
    assert "navigateWithShellMotion" not in shell_asset.text
    assert "nav-active-indicator" not in shell_asset.text
    assert "readSessionState" in shell_asset.text
    assert "writeSessionState" in shell_asset.text
    assert "shellLabel" in shell_asset.text
    assert 'new Error("Failed to read file")' not in shell_asset.text
    assert '|| "Selected"' not in shell_asset.text
    assert '|| "Switch language"' not in shell_asset.text

    portal_asset = client.get("/ui-assets/portal.js")
    assert portal_asset.status_code == 200
    assert "PORTAL_PAGE_SESSION_KEY" in portal_asset.text
    assert "loadHome" in portal_asset.text
    assert 'shellLabel("unknownError"' in portal_asset.text
    assert "isZh" not in portal_asset.text
    assert '|| "Unknown error"' not in portal_asset.text
    assert "Knowledge base ready." not in portal_asset.text

    admin_asset = client.get("/ui-assets/admin.js")
    assert admin_asset.status_code == 200
    assert "ADMIN_PAGE_SESSION_KEY" in admin_asset.text
    assert 'shellLabel("jobTypeLabel"' in admin_asset.text
    assert 'shellLabel("selectedPrefix"' in admin_asset.text
    assert 'class="action-row"' in admin_asset.text
    assert "UI.action_run_tidy" in admin_asset.text
    assert "UI.explore_question_required" in admin_asset.text
    assert "UI.admin_ready" in admin_asset.text
    assert "UI.graph_event_ask_reinforced" in admin_asset.text
    assert "UI.graph_renderer_unavailable" in admin_asset.text
    assert "UI.insight_job_created" in admin_asset.text
    assert "UI.insight_summary_pending" in admin_asset.text
    assert "UI.insight_hypothesis_title" in admin_asset.text
    assert "UI.health_cluster_coverage" in admin_asset.text
    assert "UI.live_ready" in admin_asset.text
    assert "UI.review_summary" in admin_asset.text
    assert "UI.version_repo_root" in admin_asset.text
    assert "UI.token_show" in admin_asset.text
    assert "UI.current_session" in admin_asset.text
    assert "UI.inbox_select_ready_required" in admin_asset.text
    assert "UI.file_index_direct_docs" in admin_asset.text
    assert "UI.doc_path_label" in admin_asset.text
    assert "UI.doc_kind_label" in admin_asset.text
    assert "UI.doc_status_label" in admin_asset.text
    assert "UI.doc_issues_label" in admin_asset.text
    assert "UI.doc_indexes_label" in admin_asset.text
    assert "UI.doc_aliases_label" in admin_asset.text
    assert "UI.doc_links_label" in admin_asset.text
    assert "UI.doc_updated_label" in admin_asset.text
    assert "UI.emerging_metric_demand" in admin_asset.text
    assert "UI.system_auth_label" in admin_asset.text
    assert "UI.users_empty" in admin_asset.text
    assert '|| "Changed files"' not in admin_asset.text
    assert '|| "Unknown error"' not in admin_asset.text
    assert '|| "Path"' not in admin_asset.text
    assert '|| "Kind"' not in admin_asset.text
    assert '|| "Status"' not in admin_asset.text
    assert '|| "Issues"' not in admin_asset.text
    assert '|| "Indexes"' not in admin_asset.text
    assert '|| "Aliases"' not in admin_asset.text
    assert '|| "Links"' not in admin_asset.text
    assert '|| "Updated"' not in admin_asset.text
    assert 'row actions' not in admin_asset.text
    assert 'style="margin-top:10px;"' not in admin_asset.text
    assert "isZh" not in admin_asset.text
    assert "isZh ?" not in admin_asset.text
    assert 'isZh ? "鉴权" : "Auth"' not in admin_asset.text
    assert 'isZh ? "暂无用户。" : "No users."' not in admin_asset.text
    assert "KB-level tidy" not in admin_asset.text
    assert "Question must not be empty." not in admin_asset.text
    assert "Admin ready." not in admin_asset.text
    assert "Cluster coverage " not in admin_asset.text
    assert "Pending " not in admin_asset.text
    assert "Hypothesis" not in admin_asset.text
    assert "Proposed Answer" not in admin_asset.text
    assert "LIVE READY" not in admin_asset.text
    assert "Patch summary" not in admin_asset.text
    assert "Repo root" not in admin_asset.text
    assert "Current session" not in admin_asset.text
    assert "Hide token" not in admin_asset.text
    assert "Select a review first." not in admin_asset.text
    assert "Select at least one ready document." not in admin_asset.text
    assert "Direct documents" not in admin_asset.text
    assert "Child indexes" not in admin_asset.text
    assert "Documents outside all indexes" not in admin_asset.text
    assert "Explore completed." not in admin_asset.text
    assert "Timed out while waiting for the job result." not in admin_asset.text
    assert "Agent command started with internal prompt details redacted." not in admin_asset.text
    assert "Recent questions are reinforcing this route." not in admin_asset.text
    assert 'Graph renderer is not ready.' not in admin_asset.text
    assert 'Managed job created.' not in admin_asset.text
    assert 'No obvious emerging knowledge clusters right now.' not in admin_asset.text

    graph_js = client.get("/ui-assets/graph.bundle.js")
    assert graph_js.status_code == 200
    assert "SedimentGraph" in graph_js.text

    graph_css = client.get("/ui-assets/graph.bundle.css")
    assert graph_css.status_code == 200
    assert ".portal-graph-frame" in graph_css.text

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
    assert created.json()["status"] == "open"
    assert created.json()["item"]["item_type"] == "text_feedback"

    inbox = client.get("/api/admin/inbox").json()
    assert any(item["title"] == "网页提案" for item in inbox["items"]["open_feedback"])

    quartz_page = client.get("/portal/graph-view", headers={"accept-language": "en-US"})
    assert quartz_page.status_code == 200
    assert 'data-testid="portal-insights-graph"' in quartz_page.text
    assert 'data-testid="portal-graph-focus"' in quartz_page.text
    assert 'data-testid="portal-graph-info-card"' in quartz_page.text
    assert 'data-testid="portal-graph-status"' in quartz_page.text
    assert 'data-testid="portal-graph-layout"' not in quartz_page.text
    assert 'src="/ui-assets/graph.bundle.js"' in quartz_page.text
    assert 'href="/ui-assets/graph.bundle.css"' in quartz_page.text
    assert "Knowledge universe" in quartz_page.text
    assert 'data-testid="portal-graph-quartz-link"' not in quartz_page.text

    focused_graph_page = client.get(
        "/portal/graph-view?lang=en&focus=entry::热备份",
        headers={"accept-language": "en-US"},
    )
    assert focused_graph_page.status_code == 200
    page_data = _extract_page_data(focused_graph_page.text)
    assert page_data["pageKind"] == "graph"
    assert page_data["graphScene"] == "universe_focus"
    assert page_data["initialFocus"] == "entry::热备份"
    graph_api = str(page_data["graphApi"])
    graph_query = parse_qs(urlparse(graph_api).query)
    assert graph_query["scene"] == ["universe_focus"]
    assert graph_query["budget"] == ["medium"]
    assert graph_query["focus"] == ["entry::热备份"]


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


def test_page_data_covers_frontend_ui_keys_for_portal_and_admin(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    state_dir = tmp_path / "state"
    client, server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        state_dir,
        admin_token="top-secret",
    )

    portal_page = client.get("/submit", headers={"accept-language": "en-US"})
    assert portal_page.status_code == 200
    portal_ui = _extract_page_data(portal_page.text)["ui"]
    assert isinstance(portal_ui, dict)
    portal_asset = client.get("/ui-assets/portal.js")
    assert portal_asset.status_code == 200
    missing_portal_keys = sorted(_extract_ui_keys(portal_asset.text) - set(portal_ui))
    assert missing_portal_keys == []

    login = client.post("/api/admin/session", json={"token": "top-secret"})
    assert login.status_code == 200
    assert client.cookies.get(server_module.ADMIN_SESSION_COOKIE_NAME)
    admin_page = client.get("/admin/kb", headers={"accept-language": "en-US"})
    assert admin_page.status_code == 200
    admin_ui = _extract_page_data(admin_page.text)["ui"]
    assert isinstance(admin_ui, dict)
    admin_asset = client.get("/ui-assets/admin.js")
    assert admin_asset.status_code == 200
    missing_admin_keys = sorted(_extract_ui_keys(admin_asset.text) - set(admin_ui))
    assert missing_admin_keys == []


def test_portal_graph_page_stays_self_contained_when_quartz_site_exists(
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
    assert "Knowledge universe" in page.text
    assert "Quartz Ready" not in page.text
    assert str(page.url).endswith("/portal/graph-view")
    assert 'data-testid="portal-graph-quartz-link"' not in page.text
    assert "<iframe" not in page.text


def test_portal_graph_page_exposes_universe_hud_and_minimap_shell(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    page = client.get("/portal/graph-view?lang=zh")

    assert page.status_code == 200
    assert 'data-testid="portal-graph-hud"' in page.text
    assert 'data-testid="portal-graph-search-input"' in page.text
    assert 'data-testid="portal-graph-hotspot"' in page.text
    assert 'data-testid="portal-graph-trail-run"' in page.text
    assert 'data-testid="portal-graph-minimap"' in page.text
    assert 'data-testid="portal-graph-minimap-frustum"' in page.text


def test_portal_graph_universe_api_exposes_navigation_metadata(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    payload = client.get("/api/portal/graph?scene=universe&budget=medium").json()

    assert payload["scene_mode"] == "portal-universe"
    assert payload["budget"] == "medium"
    assert payload["stats"]["total_node_count"] >= payload["stats"]["visible_node_count"]
    assert payload["hotspots"]
    assert all("hotspot_score" in node for node in payload["nodes"])
    assert all("maturity_estimate" in node for node in payload["nodes"])
    assert all("last_event_at" in node for node in payload["nodes"])


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
    assert 'class="panel panel-narrow section-gap-lg"' in login_page.text
    assert 'style="margin-top:20px; max-width:560px;"' not in login_page.text
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
    assert 'data-testid="admin-overview-primary-column"' in admin_page.text
    assert 'data-testid="admin-overview-secondary-column"' in admin_page.text
    assert 'data-testid="admin-overview-queue-panel"' in admin_page.text
    assert 'data-testid="admin-overview-health-panel"' in admin_page.text
    assert 'data-testid="admin-overview-issue-panel"' in admin_page.text
    assert 'data-testid="admin-overview-activity-panel"' in admin_page.text
    assert 'data-testid="admin-overview-emerging-panel"' in admin_page.text
    assert 'data-testid="admin-overview-stress-panel"' in admin_page.text
    assert '"admin_ready": "Admin ready."' in admin_page.text
    assert '"action_run_tidy": "KB-level tidy"' in admin_page.text
    assert '"health_cluster_coverage": "Cluster coverage"' in admin_page.text
    assert '"emerging_metric_demand": "Demand"' in admin_page.text
    assert '"emerging_metric_maturity": "Maturity"' in admin_page.text
    assert '"stress_empty": "No clear canonical stress points right now."' in admin_page.text
    assert '--overview-order: 1;' in admin_page.text
    assert '--overview-order: 6;' in admin_page.text
    assert 'src="/ui-assets/admin.js"' in admin_page.text
    assert "<title>Overview | Test Knowledge Base</title>" in admin_page.text

    kb_page = client.get("/admin/kb", headers={"accept-language": "en-US"})
    assert kb_page.status_code == 200
    assert 'data-testid="admin-ingest-button"' in kb_page.text
    assert 'data-testid="admin-kb-ingest-panel"' in kb_page.text
    assert 'data-testid="admin-kb-tidy-panel"' in kb_page.text
    assert 'data-testid="admin-kb-explore-panel"' in kb_page.text
    assert 'data-testid="admin-kb-pane-tabs"' in kb_page.text
    assert 'data-testid="admin-kb-insights-pane"' in kb_page.text
    assert 'data-testid="admin-kb-graph-pane"' in kb_page.text
    assert 'data-testid="admin-insights-list"' in kb_page.text
    assert 'data-testid="admin-insights-graph"' in kb_page.text
    assert 'data-testid="admin-runtime-console"' in kb_page.text
    assert 'data-testid="admin-kb-result"' in kb_page.text
    assert 'data-testid="admin-kb-live-log"' in kb_page.text
    assert '"insight_empty": "No insight proposals yet."' in kb_page.text
    assert '"insight_detail_empty": "Select a proposal to inspect its details."' in kb_page.text
    assert '"graph_detail_empty": "Select a graph node to inspect evidence and suggested actions."' in kb_page.text
    assert '"insight_select_prompt": "Select an insight proposal first."' in kb_page.text
    assert '"insight_job_created": "Managed job created."' in kb_page.text
    assert '"insight_summary_pending": "Pending"' in kb_page.text
    assert '"insight_summary_proposed": "Proposed"' in kb_page.text
    assert '"insight_summary_observing": "Observing"' in kb_page.text
    assert '"insight_kind_concept": "Concept"' in kb_page.text
    assert '"insight_sources_suffix": "sources"' in kb_page.text
    assert '"insight_hypothesis_title": "Hypothesis"' in kb_page.text
    assert '"insight_proposed_answer_title": "Proposed answer"' in kb_page.text
    assert '"explore_question_required": "Question must not be empty."' in kb_page.text
    assert '"graph_event_ask_reinforced": "Recent questions are reinforcing this route."' in kb_page.text
    assert '"graph_metric_energy": "Energy"' in kb_page.text
    assert '"graph_open_entry": "Open entry"' in kb_page.text
    assert '"graph_renderer_unavailable": "Graph renderer is not ready."' in kb_page.text
    assert '"editor_reload_target": "Reload current document"' in kb_page.text
    assert 'class="action-row"' in kb_page.text
    assert 'row actions' not in kb_page.text
    assert 'src="/ui-assets/graph.bundle.js"' in kb_page.text
    assert 'href="/ui-assets/graph.bundle.css"' in kb_page.text
    assert 'data-testid="admin-doc-browser"' not in kb_page.text
    assert 'data-testid="admin-editor-content"' not in kb_page.text
    assert "Choose files" in kb_page.text
    assert "Choose folder" in kb_page.text
    assert "No files selected" in kb_page.text
    assert "No folder selected" in kb_page.text

    kb_page_zh = client.get("/admin/kb", headers={"accept-language": "zh-CN"})
    assert kb_page_zh.status_code == 200
    assert '"insight_empty": "暂时还没有 insight proposal。"' in kb_page_zh.text
    assert '"insight_detail_empty": "选择一条 proposal 以查看细节。"' in kb_page_zh.text
    assert '"graph_detail_empty": "点击图中的节点，查看证据和建议动作。"' in kb_page_zh.text
    assert '"insight_select_prompt": "请先选择一条 proposal。"' in kb_page_zh.text
    assert '"insight_job_created": "已创建受管 job。"' in kb_page_zh.text
    assert '"insight_summary_pending": "待审"' in kb_page_zh.text
    assert '"insight_summary_proposed": "提案中"' in kb_page_zh.text
    assert '"insight_summary_observing": "观察中"' in kb_page_zh.text
    assert '"insight_kind_concept": "概念"' in kb_page_zh.text
    assert '"insight_sources_suffix": "条来源"' in kb_page_zh.text
    assert '"insight_hypothesis_title": "假设"' in kb_page_zh.text
    assert '"insight_proposed_answer_title": "建议答案"' in kb_page_zh.text
    assert '"explore_question_required": "问题不能为空。"' in kb_page_zh.text
    assert '"graph_event_ask_reinforced": "近期提问正在强化这条路径。"' in kb_page_zh.text
    assert '"graph_metric_energy": "能量"' in kb_page_zh.text
    assert '"graph_open_entry": "打开条目"' in kb_page_zh.text
    assert '"graph_renderer_unavailable": "图渲染器尚未就绪。"' in kb_page_zh.text
    assert '"editor_reload_target": "重新载入当前文档"' in kb_page_zh.text

    inbox_page = client.get("/admin/inbox", headers={"accept-language": "en-US"})
    assert inbox_page.status_code == 200
    assert 'data-testid="admin-inbox-layout"' in inbox_page.text
    assert 'data-testid="admin-inbox-open-feedback-list"' in inbox_page.text
    assert 'data-testid="admin-inbox-ready-documents-list"' in inbox_page.text
    assert 'class="action-row"' in inbox_page.text
    assert 'row actions' not in inbox_page.text

    version_page = client.get("/admin/version-control", headers={"accept-language": "en-US"})
    assert version_page.status_code == 200
    assert 'data-testid="admin-version-control-layout"' in version_page.text
    assert 'data-testid="admin-version-commit-reason"' in version_page.text
    assert 'data-testid="admin-version-commits-list"' in version_page.text
    assert 'class="action-row"' in version_page.text
    assert 'row actions' not in version_page.text

    files_page = client.get("/admin/files", headers={"accept-language": "en-US"})
    assert files_page.status_code == 200
    assert 'data-testid="admin-files-layout"' in files_page.text
    assert 'data-testid="admin-file-source-pane"' in files_page.text
    assert 'data-testid="admin-file-editor-pane"' in files_page.text
    assert 'data-testid="admin-file-editor-console"' in files_page.text
    assert 'data-testid="admin-file-entry-tabs"' in files_page.text
    assert 'data-testid="admin-file-console-tabs"' in files_page.text
    assert 'data-testid="admin-file-console-panel"' in files_page.text
    assert 'data-testid="admin-file-preview-button"' in files_page.text
    assert 'data-testid="admin-reset-entry-button"' in files_page.text
    assert 'data-testid="admin-reload-entry-button"' in files_page.text
    assert 'data-testid="admin-file-preview-modal"' in files_page.text
    assert 'data-testid="admin-file-console-issues"' in files_page.text
    assert 'data-testid="admin-file-console-meta"' in files_page.text
    assert 'data-testid="admin-file-index-tree"' in files_page.text
    assert 'data-testid="admin-file-search"' in files_page.text
    assert 'data-testid="admin-editor-content"' in files_page.text
    assert 'data-testid="admin-file-inspector-tabs"' not in files_page.text
    assert 'data-testid="admin-file-preview-panel"' not in files_page.text
    assert 'data-testid="admin-file-issues-panel"' not in files_page.text
    assert 'data-testid="admin-file-meta-panel"' not in files_page.text
    assert "<title>File management | Test Knowledge Base</title>" in files_page.text

    review_page = client.get("/admin/reviews", headers={"accept-language": "en-US"}, follow_redirects=False)
    assert review_page.status_code == 307
    assert review_page.headers["location"].endswith("/admin/inbox?lang=en")

    users_page = client.get("/admin/users", headers={"accept-language": "en-US"})
    assert users_page.status_code == 200
    assert 'data-testid="admin-user-list"' in users_page.text
    assert 'data-testid="admin-user-token-view"' not in users_page.text
    assert 'id="user-role"' not in users_page.text
    assert '"users_empty": "No users."' in users_page.text

    system_page = client.get("/admin/system", headers={"accept-language": "en-US"})
    assert system_page.status_code == 200
    assert 'data-testid="admin-system-status"' in system_page.text
    assert 'data-testid="admin-settings-raw-text"' in system_page.text
    assert 'data-testid="admin-settings-restart-button"' in system_page.text
    assert '"system_auth_label": "Auth"' in system_page.text
    assert '"system_state_enabled": "enabled"' in system_page.text
    assert "<title>Settings | Test Knowledge Base</title>" in system_page.text

    overview_page_zh = client.get("/admin/overview", headers={"accept-language": "zh-CN"})
    assert overview_page_zh.status_code == 200
    assert '"admin_ready": "管理台已就绪。"' in overview_page_zh.text
    assert '"action_run_tidy": "KB 级 tidy"' in overview_page_zh.text
    assert '"emerging_metric_demand": "需求"' in overview_page_zh.text
    assert '"emerging_metric_maturity": "成熟度"' in overview_page_zh.text
    assert '"stress_empty": "暂时没有明显的 canonical 压力点。"' in overview_page_zh.text

    kb_page_zh = client.get("/admin/kb", headers={"accept-language": "zh-CN"})
    assert kb_page_zh.status_code == 200
    assert "<title>知识库管理 | Test Knowledge Base</title>" in kb_page_zh.text
    assert "KB Management 知识库管理" not in kb_page_zh.text
    assert "Ingest 导入" not in kb_page_zh.text
    assert "Tidy 整理" not in kb_page_zh.text
    assert "Explore 探索" not in kb_page_zh.text
    assert ">操作<" in kb_page_zh.text
    assert ">Insights<" in kb_page_zh.text
    assert ">图谱<" in kb_page_zh.text
    assert ">Live<" in kb_page_zh.text
    assert ">导入<" in kb_page_zh.text
    assert ">整理<" in kb_page_zh.text
    assert ">探索<" in kb_page_zh.text

    files_page_zh = client.get("/admin/files", headers={"accept-language": "zh-CN"})
    assert files_page_zh.status_code == 200
    assert "<title>文件管理 | Test Knowledge Base</title>" in files_page_zh.text
    assert "Files 文件管理" not in files_page_zh.text
    assert "Files 文件入口" not in files_page_zh.text
    assert "Index 索引导航" not in files_page_zh.text
    assert ">文件入口<" in files_page_zh.text
    assert ">索引导航<" in files_page_zh.text
    assert ">健康队列<" in files_page_zh.text
    assert ">编辑控制台<" in files_page_zh.text
    assert ">预览<" in files_page_zh.text
    assert ">恢复<" in files_page_zh.text
    assert ">重新载入<" in files_page_zh.text
    assert ">关联问题<" in files_page_zh.text
    assert ">元数据<" in files_page_zh.text

    users_page_zh = client.get("/admin/users", headers={"accept-language": "zh-CN"})
    assert users_page_zh.status_code == 200
    assert '"users_empty": "暂无用户。"' in users_page_zh.text

    system_page_zh = client.get("/admin/system", headers={"accept-language": "zh-CN"})
    assert system_page_zh.status_code == 200
    assert '"system_auth_label": "鉴权"' in system_page_zh.text
    assert '"system_state_enabled": "启用"' in system_page_zh.text

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

    uploaded = client.post(
        "/api/portal/submissions/document",
        json={
            "filename": "admin-bundle.md",
            "mime_type": "text/markdown",
            "content_base64": base64.b64encode("# Admin Bundle\n\n这是一份管理台导入文档。\n".encode("utf-8")).decode("ascii"),
            "submitter_name": "Alice",
        },
    ).json()["item"]
    ready = client.post(
        f"/api/admin/inbox/document/{uploaded['id']}/mark-ready",
        json={"version": uploaded["version"]},
    )
    assert ready.status_code == 200
    ready_item = ready.json()["item"]
    batch = client.post(
        "/api/admin/inbox/ingest-batches",
        json={"items": [{"id": ready_item["id"], "version": ready_item["version"]}]},
    ).json()["batch"]

    enqueued = client.post("/api/admin/ingest/document", json={"ingest_batch_id": batch["id"]})
    assert enqueued.status_code == 202
    job_id = enqueued.json()["job"]["id"]

    assert worker_module.process_queue_until_idle(max_jobs=1) == 1

    for _ in range(10):
        job = client.get(f"/api/admin/jobs/{job_id}").json()
        if job["status"] == "succeeded":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("job did not succeed")
    assert job["commit_sha"]

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

    version_status_before_commit = client.get("/api/admin/version/status").json()
    assert any(item["path"].endswith("knowledge-base/entries/薄弱条目.md") or item["path"] == "knowledge-base/entries/薄弱条目.md" for item in version_status_before_commit["tracked_changes"])

    committed = client.post(
        "/api/admin/version/commit",
        json={"reason": "edit: capture web E2E update\n\nSave the Scope section added from the file manager."},
    )
    assert committed.status_code == 201
    assert committed.json()["commit_sha"]

    version_status_after_commit = client.get("/api/admin/version/status").json()
    assert version_status_after_commit["tracked_changes"] == []

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


def test_admin_explore_live_recovers_structured_output_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOCK_EXPLORE_STRUCTURED_SUMMARY", "1")
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
    assert explore.status_code == 200
    payload = explore.json()
    assert payload["sources"] == ["热备份", "回音壁"]
    assert payload["confidence"] == "high"
    assert payload["exploration_summary"]["mode"] == "structured-output-summary"

    with client.stream("POST", "/api/admin/explore/live", json={"question": "什么是热备份？"}) as explore_live:
        assert explore_live.status_code == 200
        events = [json.loads(line) for line in explore_live.iter_lines() if line]

    command_event = next(event for event in events if event["type"] == "command")
    assert command_event["backend"]
    assert "Launching agent CLI" in command_event["message"]
    assert "claude -p" not in command_event["message"]
    assert "--json-schema" not in command_event["message"]
    assert "internal Sediment explore runtime" not in command_event["message"]
    assert any(
        event["type"] == "status" and "structured-output summary" in event["message"]
        for event in events
    )
    assert any(event["type"] == "result" for event in events)
    done_event = next(event for event in events if event["type"] == "done")
    assert done_event["ok"] is True


def test_admin_explore_live_rejects_leaked_runtime_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOCK_EXPLORE_LEAKED_ANSWER", "1")
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

    with client.stream("POST", "/api/admin/explore/live", json={"question": "什么是热备份？"}) as explore_live:
        assert explore_live.status_code == 200
        events = [json.loads(line) for line in explore_live.iter_lines() if line]

    assert not any(event["type"] == "result" for event in events)
    assert any(event["type"] == "retry" and "prompt/schema leakage" in event.get("reason", "") for event in events)
    assert any(
        "You are the internal Sediment explore runtime"
        in (
            event.get("raw_excerpt", {}).get("excerpt", "")
            if isinstance(event.get("raw_excerpt"), dict)
            else str(event.get("raw_excerpt", ""))
        )
        for event in events
        if event["type"] == "retry"
    )
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
