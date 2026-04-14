from __future__ import annotations

import asyncio
import importlib
import json
import sys
import textwrap
from pathlib import Path

from sediment import server
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
        kb_path / "entries" / "哈基米.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - glossary.md
        ---
        # 哈基米

        哈基米是系统运转依赖的基础能量单元，也是各类传输、存储和结算流程的核心资源。

        ## Scope
        适用于采集、传输、存储和结算语境，治理规则直接围绕哈基米展开，而不是以外围流程节点替代。
        """,
    )
    _write(
        kb_path / "entries" / "启明.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - launch.md
        ---
        # 启明

        启明是新谐振腔在开光和试音之后进行的首次受控放量仪式。

        ## Scope
        适用于新谐振腔首次上线前的受控启动场景。启明前必须完成开光、试音、结构与镀层检查以及监测设备校准；启明期间需要掌灯人主持、分级控制注入速率并保持实时监测。
        """,
    )
    _write(
        kb_path / "entries" / "清道夫.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - ops.md
        ---
        # 清道夫

        清道夫是清理散斑的自动化维护流程。
        """,
    )
    _write(
        kb_path / "entries" / "园丁.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - ops.md
        ---
        # 园丁

        园丁是负责执行清道夫操作的运维团队。
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


def test_answer_question_uses_local_fast_path_when_enabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("什么是热备份？", kb_path, project_root)

    assert result["sources"] == ["热备份"]
    assert result["confidence"] == "high"
    assert result["exploration_summary"]["mode"] == "local-fastpath"
    assert "热备份" in result["answer"]


def test_answer_question_local_fast_path_keeps_definition_clean(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("什么是哈基米？", kb_path, project_root)

    assert result["sources"] == ["哈基米"]
    assert "基础能量单元" in result["answer"]
    assert "而不是" not in result["answer"]


def test_answer_question_local_fast_path_prefers_primary_scope_for_guidance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("启明前需要完成哪些准备？", kb_path, project_root)

    assert result["sources"] == ["启明"]
    assert "开光" in result["answer"]
    assert "监测设备校准" in result["answer"]
    assert "判官" not in result["answer"]


def test_answer_question_local_fast_path_keeps_multiple_direct_matches_for_relation_query(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("清道夫和园丁是什么关系？", kb_path, project_root)

    assert set(result["sources"]) == {"清道夫", "园丁"}
    assert "清理散斑" in result["answer"]
    assert "运维团队" in result["answer"]


def test_answer_question_fast_path_can_use_benchmark_materials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / "project"
    kb_path = project_root / "knowledge-base"
    (kb_path / "entries").mkdir(parents=True)
    _write(
        project_root / "benchmarks" / "material" / "yaml" / "alert_rules.yaml",
        """
        global:
          rules_count: 16
        rules:
          - name: 告警一
          - name: 告警二
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("alert_rules.yaml中定义了多少种告警规则？", kb_path, project_root)

    assert "16" in result["answer"]
    assert "yaml/alert_rules.yaml" in result["sources"]
    assert result["exploration_summary"]["mode"] == "benchmark-material-fastpath"


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
