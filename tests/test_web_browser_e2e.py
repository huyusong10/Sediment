from __future__ import annotations
import re
from contextlib import contextmanager
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

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


def test_portal_browser_e2e_search_and_submit(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch) as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/", wait_until="domcontentloaded")

            expect(page.get_by_test_id("portal-search-input")).to_be_visible()
            expect(page.get_by_test_id("portal-page-title")).to_have_class(re.compile("sr-only"))
            expect(page.get_by_test_id("portal-message")).to_contain_text("知识库已就绪")
            expect(page.locator("[data-shell-nav] a.nav-link")).to_have_count(5)
            expect(page.locator("[data-shell-utility] .utility-icon-button")).to_have_count(2)
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
            before_box = search_button.bounding_box()
            page.get_by_test_id("portal-search-input").fill("热备")
            expect(page.get_by_test_id("portal-search-suggestions")).to_contain_text("热备份")
            after_box = search_button.bounding_box()
            assert before_box is not None and after_box is not None
            assert abs(before_box["y"] - after_box["y"]) < 2

            stat_cards = page.locator("#portal-stats .stat")
            expect(stat_cards).to_have_count(5)
            first_stat_box = stat_cards.nth(0).bounding_box()
            second_stat_box = stat_cards.nth(1).bounding_box()
            assert first_stat_box is not None and second_stat_box is not None
            assert abs(first_stat_box["y"] - second_stat_box["y"]) < 4
            stats_box = page.get_by_test_id("portal-stats").bounding_box()
            updates_box = page.get_by_test_id("portal-recent-updates").bounding_box()
            assert stats_box is not None and updates_box is not None
            assert stats_box["y"] < updates_box["y"]

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
            expect(page.locator("body")).to_contain_text("文本提交")
            expect(page.locator("body")).not_to_contain_text("Text Submission")

            page.locator("#submit-name").fill("Alice")
            page.locator("#submit-title").fill("浏览器提案")
            page.locator("#submit-content").fill("这是一条来自真实浏览器流程的提案。")
            page.get_by_test_id("portal-submit-text-button").click()
            expect(page.locator("#submit-text-status")).to_contain_text("submission_id=")
            expect(page.locator("#submit-text-analysis")).to_contain_text("Agent 建议")
            expect(page.get_by_test_id("portal-message")).to_contain_text("已提交文本草案")

            page.locator("#upload-name").fill("Alice")
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
            page.get_by_test_id("portal-submit-file-button").click()
            expect(page.locator("#submit-file-status")).to_contain_text("submission_id=")


def test_portal_tutorial_page_and_skill_download(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch, locale="zh") as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/tutorial", wait_until="domcontentloaded")
            expect(page.get_by_test_id("portal-page-title")).to_have_text("接入教程")
            title_box = page.get_by_test_id("portal-page-title").bounding_box()
            nav_row_box = page.locator("[data-shell-nav]").bounding_box()
            assert title_box is not None and nav_row_box is not None
            assert nav_row_box["y"] > title_box["y"]
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
            page.locator("#submit-title").fill("浏览器管理台提案")
            page.locator("#submit-content").fill("这条提交需要经历 ingest、review 和在线编辑。")
            page.get_by_test_id("portal-submit-text-button").click()
            expect(page.locator("#submit-text-status")).to_contain_text("submission_id=")

            page.goto(f"{live['base_url']}/admin", wait_until="domcontentloaded")
            expect(page.get_by_test_id("admin-page-title")).to_have_text("管理台登录")
            expect(page.get_by_test_id("admin-login-token")).to_be_visible()
            page.get_by_test_id("admin-login-token").fill("top-secret")
            page.get_by_test_id("admin-login-button").click()
            expect(page.get_by_test_id("admin-page-title")).to_have_text("总览")
            expect(page.get_by_test_id("admin-message")).to_contain_text("管理台已就绪")
            expect(page.locator('[data-testid="admin-refresh-button"]')).to_have_count(0)

            page.goto(f"{live['base_url']}/admin/system", wait_until="domcontentloaded")
            expect(page.get_by_test_id("admin-page-title")).to_have_text("设置")
            expect(page.get_by_test_id("admin-settings-raw-text")).to_be_visible()
            expect(page.get_by_test_id("admin-settings-restart-button")).to_be_visible()
            build_box = page.get_by_test_id("admin-quartz-build-button").bounding_box()
            open_box = page.locator('[data-testid="admin-quartz-actions"] a.button').bounding_box()
            assert build_box is not None and open_box is not None
            assert abs(build_box["width"] - open_box["width"]) < 2
            assert abs(build_box["height"] - open_box["height"]) < 2

            page.goto(f"{live['base_url']}/admin/kb", wait_until="domcontentloaded")
            expect(page.get_by_test_id("admin-ingest-dropzone")).to_be_visible()
            expect(page.locator('[data-testid="admin-file-index-tree"]')).to_have_count(0)
            submission_card = page.locator("#submission-list .card").filter(
                has_text="浏览器管理台提案"
            ).first
            expect(submission_card).to_be_visible()
            expect(submission_card).to_contain_text("运行 Ingest")
            submission_card.locator('button[data-action="run-ingest"]').click()
            expect(page.get_by_test_id("admin-message")).to_contain_text("创建 ingest 任务")

            assert live["worker_module"].process_queue_until_idle(max_jobs=1) == 1

            page.goto(f"{live['base_url']}/admin/reviews", wait_until="domcontentloaded")
            review_card = page.locator('#review-list button[data-action="select-review"]').first
            expect(review_card).to_be_visible()
            review_card.click()
            page.get_by_test_id("admin-review-comment").fill("浏览器流程批准")
            expect(page.get_by_test_id("admin-diff-view")).not_to_contain_text("选择待审 patch")

            page.get_by_test_id("admin-approve-review-button").click()
            expect(page.get_by_test_id("admin-message")).to_contain_text("已批准")

            page.goto(f"{live['base_url']}/admin/files", wait_until="domcontentloaded")
            expect(page.locator('[data-testid="admin-load-entry-button"]')).to_have_count(0)
            search_input = page.get_by_test_id("admin-file-search")
            search_input.fill("薄弱")
            expect(page.get_by_test_id("admin-file-suggestions")).to_contain_text("薄弱条目")
            page.locator('#admin-file-suggestions button[data-name="薄弱条目"]').click()
            tree_box = page.get_by_test_id("admin-file-index-tree").bounding_box()
            editor = page.get_by_test_id("admin-editor-content")
            editor_box = editor.bounding_box()
            assert tree_box is not None and editor_box is not None
            assert editor_box["y"] > tree_box["y"]
            expect(editor).to_have_value(re.compile("单一关系"))
            original = editor.input_value()
            updated = original.replace(
                "## Related\n- [[暗流]] - 单一关系",
                "## Scope\n适用于浏览器 E2E 编辑。\n\n## Related\n- [[暗流]] - 单一关系",
            )
            editor.fill(updated)
            page.get_by_test_id("admin-save-entry-button").click()
            expect(page.get_by_test_id("admin-editor-status")).to_contain_text("保存成功")

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


def test_portal_quartz_page_shows_optional_state(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch) as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/portal/graph-view", wait_until="domcontentloaded")
            expect(page.get_by_test_id("portal-page-title")).to_have_text("Quartz")
            expect(page).to_have_title(re.compile("Quartz"))
            expect(page.locator("body")).to_contain_text("Quartz")
            expect(page.locator("body")).to_contain_text("打开 Quartz")


def test_portal_quartz_page_opens_full_site_in_new_tab(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch) as live:
        quartz_index = live["server_module"].QUARTZ_SITE_DIR / "index.html"
        quartz_index.parent.mkdir(parents=True, exist_ok=True)
        quartz_index.write_text(
            "<!doctype html><html><head><title>Quartz Ready</title></head><body><h1>Quartz Ready</h1></body></html>",
            encoding="utf-8",
        )

        with _browser_page() as page:
            page.goto(f"{live['base_url']}/", wait_until="domcontentloaded")
            with page.expect_popup() as popup_info:
                page.get_by_role("link", name="Quartz").click()
            popup = popup_info.value
            popup.wait_for_load_state("domcontentloaded")
            expect(page).not_to_have_url(re.compile(".*/quartz/.*"))
            expect(popup).to_have_url(re.compile(".*/quartz/.*"))
            expect(popup.locator("body")).to_contain_text("Quartz Ready")
