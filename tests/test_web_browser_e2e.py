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
        context = browser.new_context(locale="zh-CN")
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()


def test_portal_browser_e2e_search_and_submit(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch) as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/portal", wait_until="domcontentloaded")

            expect(page.get_by_test_id("portal-search-input")).to_be_visible()
            expect(page.get_by_test_id("portal-message")).to_contain_text("门户已就绪")

            page.get_by_test_id("portal-search-input").fill("热备份")
            page.get_by_test_id("portal-search-button").click()
            expect(page.get_by_test_id("portal-search-results")).to_contain_text("热备份")
            page.locator("#search-results .card").filter(has_text="热备份").first.click()
            expect(page.get_by_test_id("portal-entry-view")).to_contain_text("适用于需要连续服务的系统")
            page.get_by_test_id("portal-entry-close").click()

            page.locator("#submit-name").fill("Alice")
            page.locator("#submit-title").fill("浏览器提案")
            page.locator("#submit-content").fill("这是一条来自真实浏览器流程的提案。")
            page.get_by_test_id("portal-submit-text-button").click()
            expect(page.locator("#submit-text-status")).to_contain_text("submission_id=")
            expect(page.locator("#submit-text-analysis")).to_contain_text("Agent 建议")
            expect(page.get_by_test_id("portal-message")).to_contain_text("浏览器提案")

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


def test_admin_browser_e2e_review_and_edit(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch, admin_token="top-secret") as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/portal", wait_until="domcontentloaded")
            page.locator("#submit-name").fill("Alice")
            page.locator("#submit-title").fill("浏览器管理台提案")
            page.locator("#submit-content").fill("这条提交需要经历 ingest、review 和在线编辑。")
            page.get_by_test_id("portal-submit-text-button").click()
            expect(page.locator("#submit-text-status")).to_contain_text("submission_id=")

            page.goto(f"{live['base_url']}/admin", wait_until="domcontentloaded")
            expect(page.get_by_test_id("admin-login-token")).to_be_visible()
            page.get_by_test_id("admin-login-token").fill("top-secret")
            page.get_by_test_id("admin-login-button").click()
            expect(page.get_by_test_id("admin-message")).to_contain_text("管理台已就绪")

            page.goto(f"{live['base_url']}/admin/kb", wait_until="domcontentloaded")
            submission_card = page.locator("#submission-list .card").filter(
                has_text="浏览器管理台提案"
            ).first
            expect(submission_card).to_be_visible()
            expect(submission_card).to_contain_text("建议")
            submission_card.locator('button[data-action="run-ingest"]').click()
            expect(page.get_by_test_id("admin-message")).to_contain_text("创建 ingest 任务")

            assert live["worker_module"].process_queue_until_idle(max_jobs=1) == 1

            page.goto(f"{live['base_url']}/admin/reviews", wait_until="domcontentloaded")
            page.get_by_test_id("admin-refresh-button").click()
            review_card = page.locator("#review-list .card").first
            expect(review_card).to_be_visible()
            review_card.locator('button[data-action="show-diff"]').click()
            expect(page.get_by_test_id("admin-diff-view")).not_to_contain_text("选择待审 patch")

            review_card.locator('button[data-action="approve-review"]').click()
            expect(page.get_by_test_id("admin-message")).to_contain_text("已批准")

            page.goto(f"{live['base_url']}/admin/kb", wait_until="domcontentloaded")
            page.get_by_test_id("admin-editor-name").fill("薄弱条目")
            page.get_by_test_id("admin-load-entry-button").click()
            editor = page.get_by_test_id("admin-editor-content")
            expect(editor).to_have_value(re.compile("单一关系"))
            original = editor.input_value()
            updated = original.replace(
                "## Related\n- [[暗流]] - 单一关系",
                "## Scope\n适用于浏览器 E2E 编辑。\n\n## Related\n- [[暗流]] - 单一关系",
            )
            editor.fill(updated)
            page.get_by_test_id("admin-save-entry-button").click()
            expect(page.get_by_test_id("admin-editor-status")).to_contain_text("保存成功")

            page.goto(f"{live['base_url']}/portal", wait_until="domcontentloaded")
            page.get_by_test_id("portal-search-input").fill("薄弱条目")
            page.get_by_test_id("portal-search-button").click()
            page.locator("#search-results .card").filter(has_text="薄弱条目").first.click()
            expect(page.get_by_test_id("portal-entry-view")).to_contain_text(
                "适用于浏览器 E2E 编辑"
            )


def test_portal_quartz_page_shows_optional_state(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch) as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/portal/graph-view", wait_until="domcontentloaded")
            expect(page).to_have_title(re.compile("Quartz Graph"))
            expect(page.locator("body")).to_contain_text("Quartz 4 图谱")
            expect(page.locator("body")).to_contain_text("--quartz-only")
            expect(page.locator("body")).to_contain_text("npm i")


def test_portal_quartz_page_opens_full_site_in_new_tab(tmp_path: Path, monkeypatch) -> None:
    with live_server(tmp_path, monkeypatch) as live:
        quartz_index = live["server_module"].QUARTZ_SITE_DIR / "index.html"
        quartz_index.parent.mkdir(parents=True, exist_ok=True)
        quartz_index.write_text(
            "<!doctype html><html><head><title>Quartz Ready</title></head><body><h1>Quartz Ready</h1></body></html>",
            encoding="utf-8",
        )

        with _browser_page() as page:
            page.goto(f"{live['base_url']}/portal/graph-view", wait_until="domcontentloaded")
            expect(page.get_by_test_id("portal-open-quartz")).to_be_visible()
            with page.expect_popup() as popup_info:
                page.get_by_test_id("portal-open-quartz").click()
            popup = popup_info.value
            popup.wait_for_load_state("domcontentloaded")
            expect(popup).to_have_url(re.compile(".*/quartz/?$"))
            expect(popup.locator("body")).to_contain_text("Quartz Ready")
