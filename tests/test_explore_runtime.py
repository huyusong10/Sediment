from __future__ import annotations

import asyncio
import importlib
import json
import sys
import textwrap
from pathlib import Path

from mcp_server import server
from tests.config_helpers import write_test_config


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _build_project(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    kb_path = project_root / "knowledge-base"

    _write(
        project_root / "skills" / "explore" / "SKILL.md",
        """
        ---
        name: test-explore
        ---

        EXPLORE-RUNTIME-MARKER

        Return JSON only.
        """,
    )

    _write(
        kb_path / "entries" / "热备份.md",
        """
        ---
        type: concept
        status: fact
        aliases: [热切换]
        sources:
          - backup_design.md
        ---
        # 热备份

        热备份是在切换前准备好[[金蝉脱壳]]和[[回音壁]]接管能力的备份路径。

        ## Scope
        适用于需要连续服务且必须缩短恢复时间的系统，在主备或双活架构中尤为常见。

        ## Related
        - [[金蝉脱壳]] - 切换策略
        - [[回音壁]] - 观测同步
        """,
    )
    _write(
        kb_path / "index.root.md",
        """
        ---
        kind: index
        segment: root
        last_tidied_at: 2026-04-13
        entry_count: 1
        estimated_tokens: 64
        ---
        # 索引入口

        运维导航入口。

        - [[index.ops]]
        """,
    )
    _write(
        kb_path / "indexes" / "index.ops.md",
        """
        ---
        kind: index
        segment: ops
        last_tidied_at: 2026-04-13
        entry_count: 1
        estimated_tokens: 64
        ---
        # 运维索引

        热备份相关入口。

        - [[热备份]]
        """,
    )

    return project_root, kb_path


def _reload_server(
    project_root: Path,
    kb_path: Path,
    *,
    locale: str = "en",
    command: str | list[str] | None = None,
):
    write_test_config(
        project_root,
        kb_path=kb_path,
        state_dir=project_root / ".sediment_state",
        locale=locale,
        agent_backend="claude-code",
        agent_command=command,
    )
    server_module = importlib.reload(server)
    server_module._PROJECT_ROOT = project_root
    server_module.KB_PATH = kb_path
    return server_module


def test_knowledge_ask_uses_explore_skill_and_cli(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_project(tmp_path)
    cli_path = Path(__file__).parent / "fixtures" / "mock_explore_cli.py"

    monkeypatch.setenv("MOCK_REQUIRED_MARKER", "EXPLORE-RUNTIME-MARKER")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=[sys.executable, str(cli_path)],
    )

    raw = asyncio.run(server_module._knowledge_ask("什么是热备份？"))
    payload = json.loads(raw)

    assert payload["sources"] == ["热备份"]
    assert payload["confidence"] == "high"
    assert payload["exploration_summary"]["mode"] == "definition-driven"
    assert "热备份" in payload["answer"]


def test_answer_question_does_not_fall_back_to_materials(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    kb_path = project_root / "knowledge-base"

    _write(
        project_root / "skills" / "explore" / "SKILL.md",
        """
        ---
        name: test-explore
        ---

        Explore skill body.
        """,
    )
    _write(
        project_root / "testcase" / "material" / "secret.md",
        """
        # 外部秘密

        外部秘密是一个只存在于原始材料里的概念。
        """,
    )

    server_module = _reload_server(project_root, kb_path)
    result = server_module.answer_question("什么是外部秘密？", kb_path, project_root)
    assert result["sources"] == []
    assert result["confidence"] == "low"
    assert "no formal entries" in result["answer"].lower()


def test_answer_question_returns_explicit_error_when_cli_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)

    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("什么是热备份？", kb_path, project_root)

    assert result["sources"] == []
    assert result["confidence"] == "low"
    assert "unavailable" in result["error"].lower()


def test_direct_jsonrpc_malformed_body_returns_error_payload() -> None:
    class DummySSE:
        async def handle_post_message(self, scope, receive, send):  # pragma: no cover
            raise AssertionError("unexpected SSE POST fallback")

        async def connect_sse(self, scope, receive, send):  # pragma: no cover
            raise AssertionError("unexpected SSE connect")

    router = importlib.reload(server)._make_router(DummySSE())
    messages = [
        {"type": "http.request", "body": b"{invalid", "more_body": False},
    ]
    sent: list[dict] = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    }

    asyncio.run(router(scope, receive, send))

    payload = json.loads(sent[-1]["body"].decode("utf-8"))
    assert payload["error"]["code"] == -32603


def test_tool_definitions_follow_locale(tmp_path: Path) -> None:
    project_root, kb_path = _build_project(tmp_path)
    tools_en = _reload_server(project_root, kb_path, locale="en")._tool_definitions()
    assert "Return all knowledge document names" in tools_en[0].description

    tools_zh = _reload_server(project_root, kb_path, locale="zh")._tool_definitions()
    assert "返回知识库中所有知识文档的名称列表" in tools_zh[0].description


def test_white_box_tools_expose_indexes(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_project(tmp_path)
    server_module = _reload_server(project_root, kb_path)

    names = asyncio.run(server_module._knowledge_list())
    assert "index.root" in names
    assert "index.ops" in names

    content = asyncio.run(server_module._knowledge_read("index.root"))
    assert "# 索引入口" in content
