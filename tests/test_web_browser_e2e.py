from __future__ import annotations

import importlib
import re
import socket
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

from sediment import server, worker
from tests.config_helpers import write_test_config
from tests.test_platform_workflow import _build_platform_project


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _live_server(tmp_path: Path, monkeypatch, *, admin_token: str = ""):
    project_root, kb_path = _build_platform_project(tmp_path)
    port = _free_port()
    state_dir = tmp_path / "state"
    cli_path = Path(__file__).parent / "fixtures" / "mock_workflow_cli.py"
    write_test_config(
        project_root,
        kb_path=kb_path,
        state_dir=state_dir,
        agent_backend="claude-code",
        agent_command=[__import__("sys").executable, str(cli_path)],
        host="127.0.0.1",
        port=port,
    )

    server_module = importlib.reload(server)
    worker_module = importlib.reload(worker)
    monkeypatch.setattr(server_module, "ADMIN_TOKEN", "")
    monkeypatch.setattr(server_module, "STARTUP_ADMIN_TOKEN", admin_token)
    monkeypatch.setattr(server_module, "SESSION_SECRET", "browser-e2e-session")
    monkeypatch.setattr(server_module, "RUN_JOBS_IN_PROCESS", False)
    monkeypatch.setattr(server_module, "TRUST_PROXY_HEADERS", False)
    monkeypatch.setattr(server_module, "TRUSTED_PROXY_CIDRS", ())
    monkeypatch.setattr(server_module, "JOB_STALE_AFTER_SECONDS", 1)
    monkeypatch.setattr(server_module, "JOB_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(server_module, "SUBMISSION_RATE_LIMIT_COUNT", 3)

    app = server_module.create_starlette_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    live_server = uvicorn.Server(config)
    live_server.install_signal_handlers = lambda: None
    thread = threading.Thread(target=live_server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=0.5) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.1)
    else:
        live_server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("Timed out waiting for live Sediment server")

    try:
        yield {
            "base_url": base_url,
            "server_module": server_module,
            "worker_module": worker_module,
        }
    finally:
        live_server.should_exit = True
        thread.join(timeout=5)


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
    with _live_server(tmp_path, monkeypatch) as live:
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
    with _live_server(tmp_path, monkeypatch, admin_token="top-secret") as live:
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

            submission_card = page.locator("#submission-list .card").filter(
                has_text="浏览器管理台提案"
            ).first
            expect(submission_card).to_be_visible()
            expect(submission_card).to_contain_text("建议")
            submission_card.locator('button[data-action="run-ingest"]').click()
            expect(page.get_by_test_id("admin-message")).to_contain_text("创建 ingest 任务")

            assert live["worker_module"].process_queue_until_idle(max_jobs=1) == 1

            page.get_by_test_id("admin-refresh-button").click()
            review_card = page.locator("#review-list .card").first
            expect(review_card).to_be_visible()
            review_card.locator('button[data-action="show-diff"]').click()
            expect(page.get_by_test_id("admin-diff-view")).not_to_contain_text("选择待审 patch")

            review_card.locator('button[data-action="approve-review"]').click()
            expect(page.get_by_test_id("admin-message")).to_contain_text("已批准")

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
    with _live_server(tmp_path, monkeypatch) as live:
        with _browser_page() as page:
            page.goto(f"{live['base_url']}/portal/graph-view", wait_until="domcontentloaded")
            expect(page).to_have_title(re.compile("Quartz Graph"))
            expect(page.locator("body")).to_contain_text("Quartz 4 图谱")
