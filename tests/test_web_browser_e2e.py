from __future__ import annotations

import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

from sediment.quartz_runtime import build_quartz_site
from tests.support.platform_harness import live_server

pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@contextmanager
def _browser_page():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"Chromium is unavailable for Playwright E2E: {exc}")
        context = browser.new_context(locale="zh-CN", accept_downloads=True)
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()


def _installed_quartz_runtime_dir() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Sediment" / "quartz-runtime" / "quartz"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "").strip()
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / "Sediment" / "quartz-runtime" / "quartz"
    xdg_state = os.environ.get("XDG_STATE_HOME", "").strip()
    base = Path(xdg_state) if xdg_state else home / ".local" / "state"
    return base / "sediment" / "quartz-runtime" / "quartz"


def _wait_for_shared_row_alignment(page, *testids: str, tolerance: float = 2.0) -> None:
    selector_list = ", ".join(f'[data-testid="{testid}"]' for testid in testids)
    page.wait_for_function(
        """
        ({ selectors, tolerance }) => {
          const nodes = selectors
            .split(",")
            .map((selector) => document.querySelector(selector.trim()))
            .filter(Boolean);
          if (nodes.length !== selectors.split(",").length) return false;
          const boxes = nodes.map((node) => node.getBoundingClientRect());
          const referenceTop = boxes[0].top;
          const referenceHeight = boxes[0].height;
          return boxes.every(
            (box) =>
              Math.abs(box.top - referenceTop) <= tolerance &&
              Math.abs(box.height - referenceHeight) <= tolerance
          );
        }
        """,
        arg={"selectors": selector_list, "tolerance": tolerance},
    )


def test_portal_browser_e2e_search_and_submit(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch) as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/", wait_until="domcontentloaded")

            expect(page.get_by_test_id("portal-search-input")).to_be_visible()
            expect(page.get_by_test_id("portal-page-title")).to_have_class(re.compile("sr-only"))
            expect(page.get_by_test_id("portal-message")).to_contain_text("知识库已就绪")
            expect(page.locator("[data-shell-nav] a.nav-link")).to_have_count(5)
            expect(page.locator("[data-shell-utility] .utility-icon-button")).to_have_count(2)
            expect(page.locator("[data-shell-nav] a[aria-current='page']")).to_have_count(1)
            expect(page.locator(".brand svg.brand-lockup")).to_be_visible()
            expect(page.locator('a[href^="/admin"]')).to_have_count(0)
            assert page.locator('a[href="/submit?lang=zh"]').count() == 1
            brand_box = page.locator(".brand").bounding_box()
            nav_row_box = page.locator("[data-shell-nav]").bounding_box()
            assert brand_box is not None and nav_row_box is not None
            assert nav_row_box["y"] > brand_box["y"]
            overview_box = page.locator("[data-shell-nav] a.nav-link").nth(0).bounding_box()
            tutorial_box = page.locator("[data-shell-nav] a.nav-link").nth(2).bounding_box()
            assert overview_box is not None and tutorial_box is not None
            assert abs(overview_box["width"] - tutorial_box["width"]) < 2

            page.goto(f"{live['base_url']}/?lang=en", wait_until="domcontentloaded")
            overview_box = page.locator("[data-shell-nav] a.nav-link").nth(0).bounding_box()
            tutorial_box = page.locator("[data-shell-nav] a.nav-link").nth(2).bounding_box()
            assert overview_box is not None and tutorial_box is not None
            assert abs(overview_box["height"] - tutorial_box["height"]) < 2

            page.goto(f"{live['base_url']}/", wait_until="domcontentloaded")

            search_button = page.get_by_test_id("portal-search-button")
            search_input = page.get_by_test_id("portal-search-input")
            page.get_by_test_id("portal-search-input").fill("热备")
            expect(page.get_by_test_id("portal-search-suggestions")).to_contain_text("热备份")
            button_box = search_button.bounding_box()
            input_box = search_input.bounding_box()
            assert button_box is not None and input_box is not None
            assert abs(button_box["y"] - input_box["y"]) < 4

            stat_cards = page.locator("#portal-stats .stat")
            expect(stat_cards).to_have_count(5)
            first_stat_box = stat_cards.nth(0).bounding_box()
            second_stat_box = stat_cards.nth(1).bounding_box()
            assert first_stat_box is not None and second_stat_box is not None
            assert abs(first_stat_box["y"] - second_stat_box["y"]) < 4
            expect(page.get_by_test_id("portal-home-graph-layout")).to_be_visible()
            page.wait_for_function(
                "() => document.querySelector('#portal-insights-graph')?.dataset.graphReady === 'true'"
            )
            assert page.locator("#portal-insights-graph canvas").count() >= 1
            assert page.get_by_test_id("portal-recent-updates").count() == 0
            graph_box = page.get_by_test_id("portal-home-graph").bounding_box()
            search_box = page.get_by_test_id("portal-search-input").bounding_box()
            assert graph_box is not None and search_box is not None
            assert graph_box["y"] < search_box["y"]
            node_ids = page.evaluate(
                """() => {
                  const api = document.querySelector('#portal-insights-graph')?.__sedimentGraphApi;
                  return typeof api?.nodeIds === 'function' ? api.nodeIds() : [];
                }"""
            )
            selectable = [item for item in node_ids if not str(item).startswith("anchor::")]
            assert selectable
            page.evaluate(
                """(nodeId) => {
                  const api = document.querySelector('#portal-insights-graph')?.__sedimentGraphApi;
                  if (typeof api?.selectNodeById === 'function') api.selectNodeById(nodeId);
                }""",
                selectable[0],
            )
            expect(page.get_by_test_id("portal-graph-focus")).to_be_visible()
            expect(page.get_by_test_id("portal-graph-focus")).not_to_contain_text("打开条目")
            page.get_by_test_id("portal-graph-focus").get_by_role("button").click()

            page.get_by_test_id("portal-search-input").fill("热备份")
            page.get_by_test_id("portal-search-button").click()
            expect(page.get_by_test_id("portal-search-results")).to_contain_text("热备份")
            page.locator("#search-results .card").filter(has_text="热备份").first.click()
            expect(page.get_by_test_id("portal-entry-page-title")).to_have_text("热备份")
            expect(page).to_have_title(re.compile("热备份"))
            expect(page.get_by_test_id("portal-entry-sections")).to_contain_text("适用于需要连续服务的系统")
            signal_cards = page.locator("#entry-signals .signal-card")
            expect(signal_cards).to_have_count(5)
            expect(page.get_by_test_id("portal-entry-signals")).not_to_contain_text("-")
            signals_panel_box = page.get_by_test_id("portal-entry-signals-panel").bounding_box()
            sections_panel_box = page.get_by_test_id("portal-entry-sections-panel").bounding_box()
            assert signals_panel_box is not None and sections_panel_box is not None
            assert signals_panel_box["width"] < sections_panel_box["width"]
            page.goto(f"{live['base_url']}/submit", wait_until="domcontentloaded")
            expect(page.locator("body")).to_contain_text("文本意见")
            expect(page.locator("body")).not_to_contain_text("Text submission")

            page.locator("#submit-name").fill("Alice")
            page.locator("#submit-title").fill("浏览器提案")
            page.locator("#submit-content").fill("这是一条来自真实浏览器流程的提案。")
            page.get_by_test_id("portal-submit-text-button").click()
            expect(page.locator("#submit-text-status")).to_contain_text("item_id=")
            expect(page.get_by_test_id("portal-message")).to_contain_text("已提交文本意见")

            page.goto(f"{live['base_url']}/submit?lang=en", wait_until="domcontentloaded")
            expect(page.locator("body")).to_contain_text("Text feedback")
            expect(page.locator("body")).not_to_contain_text("文本意见")
            page.locator("#upload-name").fill("Alice")
            expect(page.get_by_test_id("portal-upload-file-selection")).to_have_text("No files selected")
            page.get_by_test_id("portal-upload-file").set_input_files(
                [
                    {
                        "name": "bundle-a.md",
                        "mimeType": "text/markdown",
                        "buffer": b"# Bundle A\n\nfirst\n",
                    },
                    {
                        "name": "bundle-b.txt",
                        "mimeType": "text/plain",
                        "buffer": b"second\n",
                    },
                ]
            )
            expect(page.get_by_test_id("portal-upload-file-selection")).to_contain_text("Selected 2 files")
            expect(page.get_by_test_id("portal-upload-file-selection")).to_contain_text("bundle-a.md")
            page.get_by_test_id("portal-submit-file-button").click()
            expect(page.locator("#submit-file-status")).to_contain_text("item_id=")


def test_portal_browser_e2e_submit_draft_survives_primary_nav_switch(
    tmp_path: Path, monkeypatch
) -> None:
    with live_server(tmp_path, monkeypatch) as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/submit", wait_until="domcontentloaded")
            page.get_by_test_id("portal-submit-name").fill("Alice")
            page.get_by_test_id("portal-submit-title").fill("切页也要保留")
            page.get_by_test_id("portal-submit-content").fill("这个草稿在同标签页切换后不应丢失。")

            page.goto(f"{live['base_url']}/tutorial", wait_until="domcontentloaded")
            expect(page.get_by_test_id("portal-page-title")).to_have_text("接入教程")

            page.goto(f"{live['base_url']}/submit", wait_until="domcontentloaded")
            expect(page.get_by_test_id("portal-submit-name")).to_have_value("Alice")
            expect(page.get_by_test_id("portal-submit-title")).to_have_value("切页也要保留")
            expect(page.get_by_test_id("portal-submit-content")).to_have_value(
                "这个草稿在同标签页切换后不应丢失。"
            )


def test_portal_tutorial_page_and_skill_download(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch, locale="zh") as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/tutorial", wait_until="domcontentloaded")
            expect(page.get_by_test_id("portal-page-title")).to_have_text("接入教程")
            title_box = page.get_by_test_id("portal-page-title").bounding_box()
            nav_row_box = page.locator("[data-shell-nav]").bounding_box()
            assert title_box is not None and nav_row_box is not None
            assert nav_row_box["y"] > title_box["y"]
            mcp_panel = page.get_by_test_id("tutorial-mcp-panel")
            skill_panel = page.get_by_test_id("tutorial-skill-panel")
            decision_panel = page.get_by_test_id("tutorial-decision-panel")
            mcp_box = mcp_panel.bounding_box()
            skill_box = skill_panel.bounding_box()
            decision_box = decision_panel.bounding_box()
            assert mcp_box is not None and skill_box is not None and decision_box is not None
            assert mcp_box["x"] < skill_box["x"]
            assert abs(skill_box["x"] - decision_box["x"]) < 2
            assert skill_box["y"] < decision_box["y"]
            expect(page.locator('[data-testid="tutorial-skill-downloads"] .card')).to_have_count(1)
            expect(page.locator('[data-testid="tutorial-decision-cards"] .card')).to_have_count(2)
            expect(page.locator('[data-testid="tutorial-tool-cards"] .card')).to_have_count(3)
            expect(page.locator('[data-testid="tutorial-agent-guides"] .card')).to_have_count(3)
            expect(page.locator("body")).to_contain_text("通过 MCP 接入")
            expect(page.locator("body")).to_contain_text("knowledge_ask")
            expect(page.locator("body")).to_contain_text("knowledge_list")
            expect(page.locator("body")).to_contain_text("knowledge_read")
            expect(page.locator("body")).to_contain_text("http://127.0.0.1")
            expect(page.locator("body")).not_to_contain_text("传输协议")
            expect(page.locator("body")).not_to_contain_text("公开浏览默认匿名")
            expect(page.locator("body")).not_to_contain_text("推荐工作流")
            tooltip = page.locator('[data-testid="tutorial-mcp-intro"] .tip-panel')
            expect(tooltip).not_to_be_visible()
            page.locator('[data-testid="tutorial-mcp-intro"] .tip-trigger').hover()
            expect(tooltip).to_be_visible()
            expect(tooltip).to_contain_text("tool allowlist")
            with page.expect_download() as download_info:
                page.get_by_role("link", name="下载 SKILL").first.click()
            download = download_info.value
            assert download.suggested_filename == "sediment-mcp-explore-SKILL.md"


def test_admin_browser_e2e_review_and_edit(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch, admin_token="top-secret") as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/submit", wait_until="domcontentloaded")
            page.locator("#submit-name").fill("Alice")
            page.locator("#submit-title").fill("浏览器管理台文本意见")
            page.locator("#submit-content").fill("这条提交会进入提交收件箱，并由 committer 手工解决。")
            page.get_by_test_id("portal-submit-text-button").click()
            expect(page.locator("#submit-text-status")).to_contain_text("item_id=")
            page.locator("#upload-name").fill("Alice")
            page.get_by_test_id("portal-upload-file").set_input_files(
                {
                    "name": "browser-admin-bundle.md",
                    "mimeType": "text/markdown",
                    "buffer": "# Browser Admin Bundle\n\n这份文档会被放进 ready to ingest。\n".encode("utf-8"),
                }
            )
            page.get_by_test_id("portal-submit-file-button").click()
            expect(page.locator("#submit-file-status")).to_contain_text("item_id=")

            page.goto(f"{live['base_url']}/admin", wait_until="domcontentloaded")
            expect(page.get_by_test_id("admin-page-title")).to_have_text("管理台登录")
            expect(page.get_by_test_id("admin-login-token")).to_be_visible()
            page.get_by_test_id("admin-login-token").fill("top-secret")
            page.get_by_test_id("admin-login-button").click()
            expect(page.get_by_test_id("admin-page-title")).to_have_text("总览")
            expect(page.get_by_test_id("admin-message")).to_contain_text("管理台已就绪")
            expect(page.locator('[data-testid="admin-refresh-button"]')).to_have_count(0)
            queue_box = page.get_by_test_id("admin-overview-queue-panel").bounding_box()
            health_box = page.get_by_test_id("admin-overview-health-panel").bounding_box()
            issue_box = page.get_by_test_id("admin-overview-issue-panel").bounding_box()
            activity_box = page.get_by_test_id("admin-overview-activity-panel").bounding_box()
            assert queue_box is not None and issue_box is not None and health_box is not None and activity_box is not None
            assert health_box["x"] > queue_box["x"]
            assert abs(queue_box["y"] - health_box["y"]) < 2
            assert abs(issue_box["y"] - activity_box["y"]) < 2
            assert issue_box["y"] > queue_box["y"]
            assert abs(queue_box["height"] - health_box["height"]) < 2
            assert abs(issue_box["height"] - activity_box["height"]) < 2

            page.goto(f"{live['base_url']}/admin/system", wait_until="networkidle")
            expect(page.get_by_test_id("admin-page-title")).to_have_text("设置")
            expect(page.get_by_test_id("admin-settings-raw-text")).to_be_visible()
            expect(page.get_by_test_id("admin-settings-restart-button")).to_be_visible()
            page.wait_for_function(
                """
                () => {
                  const configPath = document.querySelector('[data-testid="admin-settings-config-path"]');
                  const effectiveConfig = document.querySelector('[data-testid="admin-settings-effective-text"]');
                  if (!configPath || !effectiveConfig) return false;
                  const loadingPattern = /(加载中|Loading)/;
                  return (
                    !loadingPattern.test(configPath.textContent || "") &&
                    !loadingPattern.test(effectiveConfig.textContent || "")
                  );
                }
                """
            )
            _wait_for_shared_row_alignment(
                page,
                "admin-settings-reload-button",
                "admin-settings-save-button",
                "admin-settings-restart-button",
            )
            reload_box = page.get_by_test_id("admin-settings-reload-button").bounding_box()
            save_box = page.get_by_test_id("admin-settings-save-button").bounding_box()
            restart_box = page.get_by_test_id("admin-settings-restart-button").bounding_box()
            assert reload_box is not None and save_box is not None and restart_box is not None
            assert abs(reload_box["y"] - save_box["y"]) < 2
            assert abs(save_box["y"] - restart_box["y"]) < 2
            assert reload_box["x"] < save_box["x"] < restart_box["x"]
            assert abs(reload_box["height"] - save_box["height"]) < 2
            assert abs(save_box["height"] - restart_box["height"]) < 2
            build_box = page.get_by_test_id("admin-quartz-build-button").bounding_box()
            open_box = page.locator('[data-testid="admin-quartz-actions"] a.button').bounding_box()
            assert build_box is not None and open_box is not None
            assert abs(build_box["width"] - open_box["width"]) < 2
            assert abs(build_box["height"] - open_box["height"]) < 2

            page.goto(f"{live['base_url']}/admin/kb", wait_until="domcontentloaded")
            expect(page.get_by_test_id("admin-ingest-dropzone")).to_be_visible()
            expect(page.locator('[data-testid="admin-file-index-tree"]')).to_have_count(0)
            top_layout_box = page.get_by_test_id("admin-kb-top-layout").bounding_box()
            side_stack_box = page.get_by_test_id("admin-kb-side-stack").bounding_box()
            ingest_box = page.get_by_test_id("admin-kb-ingest-panel").bounding_box()
            tidy_box = page.get_by_test_id("admin-kb-tidy-panel").bounding_box()
            explore_box = page.get_by_test_id("admin-kb-explore-panel").bounding_box()
            live_box = page.get_by_test_id("admin-kb-live-panel").bounding_box()
            runtime_console_box = page.get_by_test_id("admin-runtime-console").bounding_box()
            result_box = page.get_by_test_id("admin-kb-result").bounding_box()
            live_log_box = page.get_by_test_id("admin-kb-live-log").bounding_box()
            live_clear_box = page.get_by_test_id("admin-kb-live-clear").bounding_box()
            assert top_layout_box is not None and side_stack_box is not None
            assert ingest_box is not None and tidy_box is not None and explore_box is not None and live_box is not None
            assert runtime_console_box is not None and result_box is not None and live_log_box is not None
            assert live_clear_box is not None
            assert ingest_box["x"] < tidy_box["x"]
            assert abs(ingest_box["width"] - side_stack_box["width"]) < 2
            assert abs(ingest_box["y"] - side_stack_box["y"]) < 2
            assert abs(tidy_box["x"] - explore_box["x"]) < 2
            assert tidy_box["y"] < explore_box["y"]
            assert live_box["y"] > top_layout_box["y"] + top_layout_box["height"] - 2
            assert abs(live_box["x"] - top_layout_box["x"]) < 2
            assert live_box["width"] > ingest_box["width"] * 1.8
            assert page.get_by_test_id("admin-runtime-console").evaluate(
                "el => getComputedStyle(el).resize"
            ) == "vertical"
            assert runtime_console_box["height"] > 900
            assert result_box["height"] > 240
            assert live_log_box["height"] > 650
            assert result_box["y"] < live_log_box["y"]
            assert abs(result_box["x"] - live_log_box["x"]) < 2
            assert abs(result_box["width"] - live_log_box["width"]) < 2
            assert live_clear_box["y"] + live_clear_box["height"] <= runtime_console_box["y"] + 2
            assert live_clear_box["x"] + live_clear_box["width"] <= live_box["x"] + live_box["width"] + 2
            expect(page.get_by_test_id("admin-ingest-status")).to_contain_text("下方运行台会同步显示请求与任务反馈")
            page.get_by_test_id("admin-manual-tidy-button").click()
            expect(page.get_by_test_id("admin-tidy-status")).to_contain_text("请填写整理原因")
            expect(page.get_by_test_id("admin-ingest-status")).to_contain_text("下方运行台会同步显示请求与任务反馈")
            expect(page.get_by_test_id("admin-kb-live-log")).to_have_value(re.compile("请填写整理原因"))
            page.get_by_test_id("admin-explore-input").fill("什么是热备份？")
            page.get_by_test_id("admin-explore-button").click()
            expect(page.get_by_test_id("admin-kb-result")).to_contain_text("热备份是在故障切换前准备好的可接管能力")
            expect(page.get_by_test_id("admin-kb-result-status")).to_contain_text("探索已完成")
            expect(page.get_by_test_id("admin-kb-explore-panel")).not_to_contain_text("热备份是在故障切换前准备好的可接管能力")
            expect(page.get_by_test_id("admin-kb-live-log")).to_have_value(re.compile("POST /api/admin/explore/live"))
            live_log = page.get_by_test_id("admin-kb-live-log").input_value()
            assert "什么是热备份？" in live_log
            assert "claude -p" not in live_log
            assert "--json-schema" not in live_log
            assert len([line for line in live_log.splitlines() if line.strip()]) >= 3

            page.goto(f"{live['base_url']}/admin/inbox", wait_until="domcontentloaded")
            expect(page.get_by_test_id("admin-page-title")).to_have_text("提交收件箱")
            feedback_card = page.locator("#inbox-open-feedback-list .card").filter(
                has_text="浏览器管理台文本意见"
            ).first
            expect(feedback_card).to_be_visible()
            feedback_card.get_by_role("button", name="已解决").click()
            expect(page.get_by_test_id("admin-inbox-history-list")).to_contain_text("浏览器管理台文本意见")

            staged_card = page.locator("#inbox-staged-documents-list .card").filter(
                has_text="browser-admin-bundle"
            ).first
            expect(staged_card).to_be_visible()
            staged_card.get_by_role("button", name="放入待导入区").click()
            ready_card = page.locator("#inbox-ready-documents-list .card").filter(
                has_text="browser-admin-bundle"
            ).first
            expect(ready_card).to_be_visible()
            ready_card.locator('input[type="checkbox"]').check()
            page.get_by_test_id("admin-inbox-create-batch-button").click()
            expect(page).to_have_url(re.compile("/admin/kb\\?ingest_batch=.*"))

            assert live["worker_module"].process_queue_until_idle(max_jobs=1) == 1
            expect(page.get_by_test_id("admin-kb-result")).to_contain_text("Generated one conservative ingest draft.")
            expect(page.get_by_test_id("admin-kb-result")).to_contain_text("提交")
            expect(page.get_by_test_id("admin-kb-result")).to_contain_text("热备份提交草案")

            page.goto(f"{live['base_url']}/admin/files", wait_until="domcontentloaded")
            expect(page.locator('[data-testid="admin-load-entry-button"]')).to_have_count(0)
            source_pane = page.get_by_test_id("admin-file-source-pane")
            editor_pane = page.get_by_test_id("admin-file-editor-pane")
            editor_header = page.get_by_test_id("admin-file-editor-header")
            source_box = source_pane.bounding_box()
            editor_pane_box = editor_pane.bounding_box()
            editor_header_box = editor_header.bounding_box()
            assert source_box is not None and editor_pane_box is not None and editor_header_box is not None
            assert editor_pane_box["x"] > source_box["x"]
            assert abs(editor_pane_box["y"] - source_box["y"]) < 4
            assert editor_header_box["y"] < editor_pane_box["y"] + 32
            assert (
                page.evaluate(
                    "() => getComputedStyle(document.querySelector('[data-testid=\"admin-file-editor-header\"]')).position"
                )
                == "static"
            )
            search_input = page.get_by_test_id("admin-file-search")
            search_input.fill("薄弱")
            expect(page.get_by_test_id("admin-file-suggestions")).to_contain_text("薄弱条目")
            expect(page.locator("#admin-file-suggestion-0")).to_have_attribute(
                "aria-selected", "true"
            )
            search_input.press("ArrowDown")
            expect(page.locator("#admin-file-suggestion-1")).to_have_attribute(
                "aria-selected", "true"
            )
            search_input.press("Enter")
            save_box = page.get_by_test_id("admin-save-entry-button").bounding_box()
            editor = page.get_by_test_id("admin-editor-content")
            editor_box = editor.bounding_box()
            assert save_box is not None and editor_box is not None
            assert save_box["y"] < editor_box["y"]
            assert save_box["y"] + save_box["height"] <= editor_header_box["y"] + editor_header_box["height"] + 4
            expect(page.get_by_test_id("admin-file-current-name")).to_have_text("index.root")
            expect(editor).to_have_value(re.compile("entry_count"))
            expect(page.get_by_test_id("admin-reload-entry-button")).to_be_enabled()
            search_input.fill("薄弱条目")
            expect(page.get_by_test_id("admin-file-suggestions")).to_contain_text("薄弱条目")
            search_input.press("Enter")
            expect(page.get_by_test_id("admin-file-current-name")).to_have_text("薄弱条目")
            expect(editor).to_have_value(re.compile("单一关系"))
            original = editor.input_value()
            updated = original.replace(
                "## Related\n- [[暗流]] - 单一关系",
                "## Scope\n适用于浏览器 E2E 编辑。\n\n## Related\n- [[暗流]] - 单一关系",
            )
            expect(page.get_by_test_id("admin-reset-entry-button")).to_be_disabled()
            editor.fill(updated)
            expect(page.get_by_test_id("admin-file-dirty-indicator")).to_contain_text("未保存修改")
            expect(page.get_by_test_id("admin-reset-entry-button")).to_be_enabled()
            page.get_by_test_id("admin-reset-entry-button").click()
            expect(editor).to_have_value(original)
            expect(page.get_by_test_id("admin-editor-status")).to_contain_text("已恢复到最近一次载入的内容")
            expect(page.get_by_test_id("admin-file-dirty-indicator")).to_contain_text("已保存")
            expect(page.get_by_test_id("admin-reset-entry-button")).to_be_disabled()
            assert page.evaluate(
                """() => {
                    const node = document.getElementById('admin-doc-meta');
                    if (!node) return false;
                    const style = getComputedStyle(node);
                    return style.overflowY === 'auto' && node.scrollHeight > node.clientHeight;
                }"""
            )
            editor.fill(updated)
            expect(page.get_by_test_id("admin-reset-entry-button")).to_be_enabled()
            page.get_by_test_id("admin-reload-entry-button").click()
            expect(page.get_by_test_id("admin-file-switch-modal")).to_be_visible()
            expect(page.get_by_test_id("admin-file-switch-target")).to_contain_text("重新载入当前文档")
            page.get_by_test_id("admin-file-switch-cancel").click()
            expect(page.get_by_test_id("admin-file-switch-modal")).to_be_hidden()
            expect(editor).to_have_value(re.compile("适用于浏览器 E2E 编辑"))
            page.get_by_test_id("admin-reload-entry-button").click()
            expect(page.get_by_test_id("admin-file-switch-modal")).to_be_visible()
            page.get_by_test_id("admin-file-switch-confirm").click()
            expect(editor).to_have_value(original)
            expect(page.get_by_test_id("admin-editor-status")).to_contain_text("已重新载入服务器版本")
            expect(page.get_by_test_id("admin-file-dirty-indicator")).to_contain_text("已保存")
            editor.fill(updated)
            page.get_by_test_id("admin-file-preview-button").click()
            expect(page.get_by_test_id("admin-file-preview-modal")).to_be_visible()
            expect(page.get_by_test_id("admin-file-preview-name")).to_have_text("薄弱条目")
            expect(page.get_by_test_id("admin-editor-preview")).to_contain_text("适用于浏览器 E2E 编辑")
            expect(page.get_by_test_id("admin-editor-preview")).not_to_contain_text("type:")
            expect(page.get_by_test_id("admin-editor-preview")).not_to_contain_text("status:")
            preview_name_box = page.get_by_test_id("admin-file-preview-name").bounding_box()
            assert preview_name_box is not None
            assert preview_name_box["width"] > preview_name_box["height"]
            page.get_by_test_id("admin-file-preview-close").click()
            expect(page.get_by_test_id("admin-file-preview-modal")).to_be_hidden()
            page.get_by_role("tab", name="健康队列").click()
            health_card = page.locator('#admin-doc-health-list [data-action="open-document"]').filter(
                has_text="回音壁"
            ).first
            expect(health_card).to_be_visible()
            health_card.click()
            expect(page.get_by_test_id("admin-file-switch-modal")).to_be_visible()
            expect(page.get_by_test_id("admin-file-switch-target")).to_contain_text("回音壁")
            page.get_by_test_id("admin-file-switch-cancel").click()
            expect(page.get_by_test_id("admin-file-switch-modal")).to_be_hidden()
            expect(page.get_by_test_id("admin-file-current-name")).to_have_text("薄弱条目")
            expect(editor).to_have_value(re.compile("适用于浏览器 E2E 编辑"))
            health_card.click()
            expect(page.get_by_test_id("admin-file-switch-modal")).to_be_visible()
            page.get_by_test_id("admin-file-switch-confirm").click()
            expect(page.get_by_test_id("admin-file-current-name")).to_have_text("回音壁")
            expect(page.locator('#admin-file-console-tabs [aria-selected="true"]')).to_have_text("关联问题")
            assert page.evaluate(
                """() => {
                    const node = document.getElementById('admin-doc-linked-issues');
                    if (!node) return false;
                    return getComputedStyle(node).overflowY === 'auto';
                }"""
            )
            expect(page.get_by_test_id("admin-file-console-issues")).to_have_attribute(
                "data-highlighted", "true"
            )
            page.get_by_role("tab", name="索引导航").click()
            search_input.fill("薄弱条目")
            expect(page.get_by_test_id("admin-file-suggestions")).to_contain_text("薄弱条目")
            search_input.press("Enter")
            expect(page.get_by_test_id("admin-file-current-name")).to_have_text("薄弱条目")
            expect(editor).to_have_value(re.compile("单一关系"))
            expect(editor).not_to_have_value(re.compile("适用于浏览器 E2E 编辑"))
            editor.fill(updated)
            page.get_by_test_id("admin-save-entry-button").click()
            expect(page.get_by_test_id("admin-editor-status")).to_contain_text("保存成功")
            expect(page.get_by_test_id("admin-file-dirty-indicator")).to_contain_text("已保存")

            page.goto(f"{live['base_url']}/admin/version-control", wait_until="domcontentloaded")
            expect(page.get_by_test_id("admin-version-tracked-changes-list")).to_contain_text("薄弱条目.md")
            page.get_by_test_id("admin-version-commit-reason").fill(
                "edit: keep browser E2E scope change\n\nCommit the manual edit from the file manager."
            )
            page.get_by_test_id("admin-version-commit-button").click()
            expect(page.get_by_test_id("admin-version-status-line")).to_contain_text("已创建提交")
            expect(page.get_by_test_id("admin-version-tracked-changes-list")).to_contain_text("tracked 路径当前没有未提交改动")

            page.goto(f"{live['base_url']}/search", wait_until="domcontentloaded")
            page.get_by_test_id("portal-search-input").fill("薄弱条目")
            page.get_by_test_id("portal-search-button").click()
            page.locator("#search-results .card").filter(has_text="薄弱条目").first.click()
            expect(page.get_by_test_id("portal-entry-sections")).to_contain_text(
                "适用于浏览器 E2E 编辑"
            )

            page.goto(f"{live['base_url']}/admin/users", wait_until="domcontentloaded")
            expect(page.locator('[data-testid="admin-user-token-view"]')).to_have_count(0)
            user_card = page.locator("#user-list .card").first
            user_card.locator('button[data-action="show-token"]').click()
            expect(user_card.locator(".inline-token")).to_contain_text("top-secret")


def test_admin_browser_e2e_keeps_leaked_runtime_output_out_of_result_panel(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MOCK_EXPLORE_LEAKED_ANSWER", "1")

    with live_server(tmp_path, monkeypatch, admin_token="top-secret") as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/admin", wait_until="domcontentloaded")
            page.get_by_test_id("admin-login-token").fill("top-secret")
            page.get_by_test_id("admin-login-button").click()
            expect(page.get_by_test_id("admin-page-title")).to_have_text("总览")

            page.goto(f"{live['base_url']}/admin/kb", wait_until="domcontentloaded")
            page.get_by_test_id("admin-explore-input").fill("什么是热备份？")
            page.get_by_test_id("admin-explore-button").click()

            expect(page.get_by_test_id("admin-kb-result-status")).to_contain_text("探索失败")
            expect(page.get_by_test_id("admin-kb-result")).to_contain_text("内部运行内容")
            expect(page.get_by_test_id("admin-kb-result")).not_to_contain_text("claude -p")
            expect(page.get_by_test_id("admin-kb-live-log")).to_have_value(
                re.compile("internal Sediment explore runtime")
            )


def test_admin_browser_e2e_files_workspace_collapses_to_single_column_on_mobile(
    tmp_path: Path, monkeypatch
) -> None:
    with live_server(tmp_path, monkeypatch, admin_token="top-secret") as live:
        with _browser_page() as page:
            page.set_viewport_size({"width": 390, "height": 900})
            page.goto(f"{live['base_url']}/admin", wait_until="domcontentloaded")
            page.get_by_test_id("admin-login-token").fill("top-secret")
            page.get_by_test_id("admin-login-button").click()
            expect(page.get_by_test_id("admin-page-title")).to_have_text("总览")
            page.goto(f"{live['base_url']}/admin/files", wait_until="domcontentloaded")

            source_box = page.get_by_test_id("admin-file-source-pane").bounding_box()
            editor_box = page.get_by_test_id("admin-file-editor-pane").bounding_box()
            assert source_box is not None and editor_box is not None
            assert abs(source_box["x"] - editor_box["x"]) < 2
            assert editor_box["y"] > source_box["y"]
            assert page.evaluate(
                "() => document.documentElement.scrollWidth <= window.innerWidth + 1"
            )

            search_input = page.get_by_test_id("admin-file-search")
            search_input.fill("薄弱条目")
            expect(page.get_by_test_id("admin-file-suggestions")).to_contain_text("薄弱条目")
            search_input.press("Enter")
            expect(page.get_by_test_id("admin-file-current-name")).to_have_text("薄弱条目")

            editor_box_after_open = page.get_by_test_id("admin-file-editor-pane").bounding_box()
            console_panel_box = page.get_by_test_id("admin-file-console-panel").bounding_box()
            console_tabs_box = page.get_by_test_id("admin-file-console-tabs").bounding_box()
            assert editor_box_after_open is not None
            assert console_panel_box is not None and console_tabs_box is not None
            assert editor_box_after_open["y"] < 180
            assert console_tabs_box["y"] < console_panel_box["y"]
            assert console_panel_box["height"] >= 200


def test_admin_browser_e2e_recovers_structured_output_summary(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MOCK_EXPLORE_STRUCTURED_SUMMARY", "1")

    with live_server(tmp_path, monkeypatch, admin_token="top-secret") as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/admin", wait_until="domcontentloaded")
            page.get_by_test_id("admin-login-token").fill("top-secret")
            page.get_by_test_id("admin-login-button").click()
            expect(page.get_by_test_id("admin-page-title")).to_have_text("总览")

            page.goto(f"{live['base_url']}/admin/kb", wait_until="domcontentloaded")
            page.get_by_test_id("admin-explore-input").fill("什么是热备份？")
            page.get_by_test_id("admin-explore-button").click()

            expect(page.get_by_test_id("admin-kb-result-status")).to_contain_text("探索已完成")
            expect(page.get_by_test_id("admin-kb-result")).to_contain_text("Prepared capability")
            expect(page.get_by_test_id("admin-kb-result")).to_contain_text("热备份是在故障切换前准备好的可接管能力")
            expect(page.get_by_test_id("admin-kb-result")).not_to_contain_text("探索失败")
            expect(page.get_by_test_id("admin-kb-live-log")).to_have_value(
                re.compile("structured-output summary")
            )
            expect(page.get_by_test_id("admin-kb-live-log")).not_to_have_value(
                re.compile(r"claude -p|--json-schema")
            )


def test_admin_browser_e2e_kb_runtime_state_survives_primary_nav_switch(
    tmp_path: Path, monkeypatch
) -> None:
    with live_server(tmp_path, monkeypatch, admin_token="top-secret") as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/admin", wait_until="domcontentloaded")
            page.get_by_test_id("admin-login-token").fill("top-secret")
            page.get_by_test_id("admin-login-button").click()
            expect(page.get_by_test_id("admin-page-title")).to_have_text("总览")

            page.goto(f"{live['base_url']}/admin/kb", wait_until="domcontentloaded")
            page.get_by_test_id("admin-tidy-reason").fill("先保留这个整理原因")
            page.get_by_test_id("admin-explore-input").fill("什么是热备份？")
            page.get_by_test_id("admin-explore-button").click()
            expect(page.get_by_test_id("admin-kb-result-status")).to_contain_text("探索已完成")
            expect(page.get_by_test_id("admin-kb-result")).to_contain_text("热备份是在故障切换前准备好的可接管能力")
            expect(page.get_by_test_id("admin-kb-live-log")).to_have_value(re.compile("POST /api/admin/explore/live"))

            page.goto(f"{live['base_url']}/admin/overview", wait_until="domcontentloaded")
            expect(page.get_by_test_id("admin-page-title")).to_have_text("总览")

            page.goto(f"{live['base_url']}/admin/kb", wait_until="domcontentloaded")
            expect(page.get_by_test_id("admin-tidy-reason")).to_have_value("先保留这个整理原因")
            expect(page.get_by_test_id("admin-explore-input")).to_have_value("什么是热备份？")
            expect(page.get_by_test_id("admin-kb-result-status")).to_contain_text("探索已完成")
            expect(page.get_by_test_id("admin-kb-result")).to_contain_text("热备份是在故障切换前准备好的可接管能力")
            expect(page.get_by_test_id("admin-kb-live-log")).to_have_value(re.compile("POST /api/admin/explore/live"))
            expect(page.get_by_test_id("admin-kb-live-log")).not_to_have_value(
                re.compile(r"claude -p|--json-schema")
            )


def test_portal_graph_page_renders_dynamic_insights_surface(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch) as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/portal/graph-view?lang=zh", wait_until="domcontentloaded")
            expect(page).to_have_title(re.compile("知识宇宙"))
            expect(page.get_by_test_id("portal-graph-immersive-page")).to_be_visible()
            expect(page.get_by_test_id("portal-graph-hint")).to_be_visible()
            expect(page.get_by_test_id("portal-graph-focus")).to_be_hidden()
            expect(page.locator(".hero")).to_have_count(0)
            page.wait_for_function(
                "() => document.querySelector('#portal-insights-graph')?.dataset.graphReady === 'true'"
            )
            assert page.locator("#portal-insights-graph canvas").count() >= 1
            node_ids = page.evaluate(
                """() => {
                  const api = document.querySelector('#portal-insights-graph')?.__sedimentGraphApi;
                  return typeof api?.nodeIds === 'function' ? api.nodeIds() : [];
                }"""
            )
            selectable = [item for item in node_ids if not str(item).startswith("anchor::")]
            assert selectable
            page.evaluate(
                """(nodeId) => {
                  const api = document.querySelector('#portal-insights-graph')?.__sedimentGraphApi;
                  if (typeof api?.selectNodeById === 'function') api.selectNodeById(nodeId);
                }""",
                selectable[0],
            )
            expect(page.get_by_test_id("portal-graph-focus")).to_be_visible()
            expect(page.get_by_test_id("portal-graph-focus")).to_contain_text("最近事件")
            expect(page.get_by_test_id("portal-graph-focus")).not_to_contain_text("打开条目")


def test_portal_graph_page_keeps_quartz_as_new_tab_link(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch) as live:
        quartz_index = live["server_module"].QUARTZ_SITE_DIR / "index.html"
        quartz_index.parent.mkdir(parents=True, exist_ok=True)
        quartz_index.write_text(
            (
                "<!doctype html><html><head><title>Quartz Ready</title></head>"
                "<body><h1>Quartz Ready</h1></body></html>"
            ),
            encoding="utf-8",
        )

        with _browser_page() as page:
            page.goto(f"{live['base_url']}/portal/graph-view", wait_until="domcontentloaded")
            with page.expect_popup() as popup_info:
                page.get_by_test_id("portal-graph-quartz-link").locator('a[target="_blank"]').click()
            popup = popup_info.value
            popup.wait_for_load_state("domcontentloaded")
            expect(page).to_have_url(re.compile(".*/portal/graph-view.*"))
            expect(popup).to_have_url(re.compile(".*/quartz/.*"))
            expect(popup.locator("body")).to_contain_text("Quartz Ready")


def test_quartz_graph_hides_index_pages_and_renders_entry_pages_when_served_through_sediment(
    tmp_path: Path, monkeypatch
) -> None:
    with live_server(tmp_path, monkeypatch) as live:
        runtime_dir = _installed_quartz_runtime_dir()
        if not ((runtime_dir / "package.json").exists() and (runtime_dir / "node_modules").exists()):
            pytest.skip("Quartz runtime is not installed in the local Sediment user state.")

        monkeypatch.setattr(live["server_module"], "QUARTZ_RUNTIME_DIR", runtime_dir)
        build_quartz_site(
            kb_path=live["server_module"].KB_PATH,
            runtime_dir=runtime_dir,
            site_dir=live["server_module"].QUARTZ_SITE_DIR,
            knowledge_name=live["server_module"].KNOWLEDGE_NAME,
            locale="zh",
        )

        with _browser_page() as page:
            page.goto(f"{live['base_url']}/quartz/", wait_until="networkidle")
            page.wait_for_timeout(1500)
            expect(page.locator(".graph-container")).to_have_count(0)
            expect(page.locator(".global-graph-container")).to_have_count(0)

            page.goto(
                f"{live['base_url']}/quartz/entries/%E7%83%AD%E5%A4%87%E4%BB%BD",
                wait_until="networkidle",
            )
            page.wait_for_timeout(1500)
            expect(page).to_have_title(re.compile("热备份"))
            expect(page.locator(".graph-container canvas")).to_have_count(1)
