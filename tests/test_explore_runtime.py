from __future__ import annotations

import asyncio
import importlib
import json
import sys
import textwrap
from pathlib import Path

import pytest

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
        project_root / "benchmarks" / "material" / "secret.md",
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


def test_answer_question_agent_only_surfaces_invalid_json_with_trace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    cli_path = Path(__file__).parent / "fixtures" / "mock_workflow_cli.py"

    monkeypatch.setenv("MOCK_EXPLORE_INVALID_JSON", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=[sys.executable, str(cli_path)],
    )

    events: list[dict[str, object]] = []

    with pytest.raises(RuntimeError, match="invalid JSON"):
        server_module.answer_question_agent_only(
            "什么是热备份？",
            kb_path,
            project_root,
            emit=events.append,
        )

    assert any(event.get("type") == "command" for event in events)
    assert any(event.get("type") == "retry" for event in events)
    assert any("not-json-response" in str(event.get("raw_excerpt", "")) for event in events)


def test_answer_question_agent_only_recovers_structured_output_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    cli_path = Path(__file__).parent / "fixtures" / "mock_workflow_cli.py"

    monkeypatch.setenv("MOCK_EXPLORE_STRUCTURED_SUMMARY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=[sys.executable, str(cli_path)],
    )

    events: list[dict[str, object]] = []
    payload = server_module.answer_question_agent_only(
        "什么是热备份？",
        kb_path,
        project_root,
        emit=events.append,
    )

    assert payload["sources"] == ["热备份"]
    assert payload["confidence"] == "high"
    assert payload["exploration_summary"]["mode"] == "structured-output-summary"
    assert "热备份是在故障切换前准备好的可接管能力" in payload["answer"]
    assert any(
        event.get("type") == "status"
        and "structured-output summary" in str(event.get("message", ""))
        for event in events
    )


def test_answer_question_agent_only_rejects_leaked_prompt_output_with_trace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    cli_path = Path(__file__).parent / "fixtures" / "mock_workflow_cli.py"

    monkeypatch.setenv("MOCK_EXPLORE_LEAKED_ANSWER", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=[sys.executable, str(cli_path)],
    )

    events: list[dict[str, object]] = []

    with pytest.raises(RuntimeError, match="invalid JSON"):
        server_module.answer_question_agent_only(
            "什么是热备份？",
            kb_path,
            project_root,
            emit=events.append,
        )

    assert any(event.get("type") == "retry" for event in events)
    assert any(
        "You are the internal Sediment explore runtime"
        in (
            event.get("raw_excerpt", {}).get("excerpt", "")
            if isinstance(event.get("raw_excerpt"), dict)
            else str(event.get("raw_excerpt", ""))
        )
        for event in events
    )
    assert any(
        "prompt/schema leakage" in str(event.get("reason", ""))
        for event in events
        if event.get("type") == "retry"
    )


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


def test_answer_question_local_fast_path_definition_uses_grounded_support(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "哈基米.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - architecture.md
        ---
        # 哈基米

        哈基米是基础能量单元。

        ## Scope
        哈基米既是系统的核心资源，也是整套系统一切运作的物质基础。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("什么是哈基米？", kb_path, project_root)

    assert result["sources"] == ["哈基米"]
    assert "基础能量单元" in result["answer"]
    assert "核心资源" in result["answer"]


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


def test_answer_question_local_fast_path_prefers_scope_for_rule_content_questions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "三振法则.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - safety.md
        ---
        # 三振法则

        三振法则是核心安全规则。

        ## Scope
        连续三次出现同类异常时自动隔离相关腔体或操作者。
        幽灵读数经照妖镜验证后记录异常但不计入三振。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("三振法则的内容是什么？", kb_path, project_root)

    assert result["sources"] == ["三振法则"]
    assert "连续三次" in result["answer"]
    assert "幽灵读数" in result["answer"]


def test_answer_question_local_fast_path_prefers_scope_for_flow_questions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "潮涌.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - runbook.md
        ---
        # 潮涌

        潮涌是嗡鸣度短时间剧烈上冲的异常事件。

        ## Scope
        守望者在通天塔创建事件并锁定受影响腔组视图。
        判官确认热备份是否就绪并预热泄洪通道。
        如存在跨区传播迹象，立即执行分水岭隔离。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("潮涌发生时，从检测到处置的完整流程是什么？", kb_path, project_root)

    assert result["sources"][0] == "潮涌"
    assert "创建事件" in result["answer"]
    assert "热备份" in result["answer"]
    assert "分水岭隔离" in result["answer"]


def test_answer_question_local_fast_path_preserves_dotted_numeric_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "红线.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - system_config.yaml
        ---
        # 红线

        红线是嗡鸣度绝对不可超过的安全阈值，标准腔默认值为 720.0Hz。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("红线是什么意思？", kb_path, project_root)

    assert result["sources"] == ["红线"]
    assert "720.0Hz" in result["answer"]
    assert result["answer"] != "0Hz"
    assert "嗡鸣度绝对不可超过的安全阈值" in result["answer"]


def test_answer_question_local_fast_path_prefers_scope_for_english_rule_questions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "三振法则.md",
        """
        ---
        type: concept
        status: fact
        aliases: [three-strike rule]
        sources:
          - safety.md
        ---
        # 三振法则

        三振法则是核心安全规则。

        ## Scope
        连续三次出现同类异常时自动隔离相关腔体或操作者。
        幽灵读数经照妖镜验证后记录异常但不计入三振。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "What is the content of the three-strike rule?",
        kb_path,
        project_root,
    )

    assert result["sources"] == ["三振法则"]
    assert "连续三次" in result["answer"]
    assert "幽灵读数" in result["answer"]


def test_answer_question_local_fast_path_prefers_scope_for_english_flow_questions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "潮涌.md",
        """
        ---
        type: concept
        status: fact
        aliases: [surge]
        sources:
          - runbook.md
        ---
        # 潮涌

        潮涌是嗡鸣度短时间剧烈上冲的异常事件。

        ## Scope
        守望者在通天塔创建事件并锁定受影响腔组视图。
        判官确认热备份是否就绪并预热泄洪通道。
        如存在跨区传播迹象，立即执行分水岭隔离。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "What is the process for handling a surge from detection to mitigation?",
        kb_path,
        project_root,
    )

    assert result["sources"][0] == "潮涌"
    assert "创建事件" in result["answer"]
    assert "热备份" in result["answer"]
    assert "分水岭隔离" in result["answer"]


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


def test_answer_question_local_fast_path_prefers_exact_terms_over_substring_fragments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "调音师.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - singer.md
        ---
        # 调音师

        调音师是负责调整谐振腔嗡鸣度并使用定音鼓校准频率的专家角色。
        """,
    )
    _write(
        kb_path / "entries" / "定音鼓.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - tools.md
        ---
        # 定音鼓

        定音鼓是用于校准谐振腔频率的标准工具。

        ## Scope
        调音师通过定音鼓发出标准频率脉冲，再根据响应波形微调嗡鸣度。
        """,
    )
    _write(
        kb_path / "entries" / "调音.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - singer.py
        ---
        # 调音

        调音异常。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("调音师和定音鼓如何配合工作？", kb_path, project_root)

    assert "调音师" in result["sources"]
    assert "定音鼓" in result["sources"]
    assert "调音" not in result["sources"]
    assert "校准频率" in result["answer"] or "标准频率脉冲" in result["answer"]


def test_answer_question_local_fast_path_definition_prefers_informative_scope_sentence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "嗡鸣度.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - metrics.md
        ---
        # 嗡鸣度

        嗡鸣度是系统运行中的一种模式或状态。

        ## Scope
        嗡鸣度衡量哈基米活跃状态和系统整体能量波动，连续偏离共振峰会触发进一步排查。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("嗡鸣度衡量什么？", kb_path, project_root)

    assert result["sources"] == ["嗡鸣度"]
    assert "衡量哈基米活跃状态" in result["answer"]
    assert "一种模式或状态" not in result["answer"]


def test_answer_question_local_fast_path_returns_multiple_definition_matches_for_respective_question(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "枯水期.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - dry_season.md
        ---
        # 枯水期

        枯水期是哈基米流量低、镀层状态相对稳定的运行时段。
        """,
    )
    _write(
        kb_path / "entries" / "丰水期.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - wet_season.md
        ---
        # 丰水期

        丰水期是哈基米流量大、镀层磨损加速的高负载运行时段。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("枯水期和丰水期分别指什么？", kb_path, project_root)

    assert result["sources"] == ["枯水期", "丰水期"]
    assert "枯水期是哈基米流量低" in result["answer"]
    assert "丰水期是哈基米流量大" in result["answer"]


def test_answer_question_local_fast_path_prefers_specific_target_phrase_over_generic_fragment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "技术.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - glossary.md
        ---
        # 技术

        技术是相关系统中的一种模式或状态。
        """,
    )
    _write(
        kb_path / "entries" / "隐身衣.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - security.md
        ---
        # 隐身衣

        隐身衣是用于隐藏暗流轨迹的伪装技术。

        ## Scope
        隐身衣只能绕过回音壁等常规监测，不能完全避免照妖镜与账房审计的联合检测。
        """,
    )
    _write(
        kb_path / "entries" / "哈基米系统设计哲学.md",
        """
        ---
        type: concept
        status: fact
        aliases: [设计哲学]
        sources:
          - system_config.yaml
        ---
        # 哈基米系统设计哲学

        哈基米系统设计哲学强调稳定性优先、全链路可追溯和冗余容错。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    stealth_result = server_module.answer_question(
        "从暗流调查报告和渡鸦守则看，隐身衣技术目前能完全避免检测吗？",
        kb_path,
        project_root,
    )
    philosophy_result = server_module.answer_question(
        "从全系统角度推断，哈基米系统的设计哲学是什么？",
        kb_path,
        project_root,
    )

    assert stealth_result["sources"][0] == "隐身衣"
    assert "不能完全避免" in stealth_result["answer"]
    assert philosophy_result["sources"][0] == "哈基米系统设计哲学"
    assert "稳定性优先" in philosophy_result["answer"]


def test_answer_question_local_fast_path_prefers_specific_artifact_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "部署拓扑.md",
        """
        ---
        type: concept
        status: fact
        aliases: [deployment_topology, deployment_topology.json]
        sources:
          - deployment_topology
        ---
        # 部署拓扑

        部署拓扑定义了当前拓扑共 5 个谐振腔节点。

        ## Scope
        包含 2 个主谐振腔、1 个热备份谐振腔、1 个标准谐振腔和 1 个种月部署的微型谐振腔。
        """,
    )
    _write(
        kb_path / "entries" / "谐振腔.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - resonator.md
        ---
        # 谐振腔

        谐振腔是存储哈基米的容器，可调节嗡鸣度。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "deployment_topology.json中定义了多少个谐振腔节点？",
        kb_path,
        project_root,
    )

    assert result["sources"] == ["部署拓扑"]
    assert "5 个谐振腔节点" in result["answer"]


def test_answer_question_local_fast_path_uses_scope_for_quantitative_fact_questions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "共振峰.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - metric_definitions.json
        ---
        # 共振峰

        共振峰是嗡鸣度的理想运行区间。

        ## Scope
        共振峰范围为 420.0-580.0Hz，低于下限会导致效能下降，高于上限需准备分流。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("从配置模板看，共振峰的范围是多少？", kb_path, project_root)

    assert result["sources"] == ["共振峰"]
    assert "420.0-580.0Hz" in result["answer"]


def test_answer_question_local_fast_path_prefers_artifact_target_over_generic_topic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "信使.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - messenger.md
        ---
        # 信使

        信使是传递状态信息的进程。
        """,
    )
    _write(
        kb_path / "entries" / "信使路由策略.md",
        """
        ---
        type: concept
        status: fact
        aliases: [信使路由表, 信使路由表.xml]
        sources:
          - routing.xml
        ---
        # 信使路由策略

        信使路由策略定义了接力、分流和合流等路径选择方式。

        ## Scope
        当前路由类型包括接力、分流、合流，默认算法为负载均衡优先的最短路径。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("信使路由表中定义了哪些路由策略？", kb_path, project_root)

    assert result["sources"] == ["信使路由策略"]
    assert "接力" in result["answer"]


def test_answer_question_local_fast_path_prefers_canonical_alias_entry_over_wrapper_title(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "信使路由表.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - routing.xml
        ---
        # 信使路由表

        信使路由表是路径规则是否允许动态调整。
        """,
    )
    _write(
        kb_path / "entries" / "信使路由策略.md",
        """
        ---
        type: concept
        status: fact
        aliases: [信使路由表, 信使路由表.xml]
        sources:
          - routing.xml
        ---
        # 信使路由策略

        信使路由策略定义了接力、分流、合流等路径选择方式。

        ## Scope
        当前路由类型包括接力、分流、合流，默认算法为负载均衡优先的最短路径。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("信使路由表中定义了哪些路由策略？", kb_path, project_root)

    assert result["sources"] == ["信使路由策略"]
    assert "接力" in result["answer"]
    assert "分流" in result["answer"]


def test_answer_question_local_fast_path_ignores_unrelated_alias_hijack(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "无字碑.md",
        """
        ---
        type: concept
        status: fact
        aliases: [暗流, 渡鸦]
        sources:
          - debug.md
        ---
        # 无字碑

        无字碑是旋涡协议的不记日志调试模式。
        """,
    )
    _write(
        kb_path / "entries" / "隐身衣.md",
        """
        ---
        type: concept
        status: fact
        aliases: [隐身衣技术]
        sources:
          - security.md
        ---
        # 隐身衣

        隐身衣是用于隐藏暗流轨迹的伪装技术。

        ## Scope
        隐身衣只能绕过回音壁等常规监测，不能完全避免照妖镜与账房审计的联合检测。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "从暗流调查报告和渡鸦守则看，隐身衣技术目前能完全避免检测吗？",
        kb_path,
        project_root,
    )

    assert result["sources"][0] == "隐身衣"
    assert "不能完全避免" in result["answer"]
    assert "账房审计" in result["answer"] or "照妖镜" in result["answer"]


def test_answer_question_local_fast_path_prefers_specific_fault_taxonomy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "谐振腔.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - resonator.md
        ---
        # 谐振腔

        谐振腔是存储哈基米的容器。
        """,
    )
    _write(
        kb_path / "entries" / "管理谐振腔的完整生命周期故障类型.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - lifecycle.txt
        ---
        # 管理谐振腔的完整生命周期故障类型

        管理谐振腔的完整生命周期故障类型是泛化整理残留条目。
        """,
    )
    _write(
        kb_path / "entries" / "谐振腔故障类型.md",
        """
        ---
        type: concept
        status: fact
        aliases: [异常类]
        sources:
          - resonator.py
        ---
        # 谐振腔故障类型

        谐振腔故障类型包括坍缩、红线异常和镀层缺陷等运行时故障。

        ## Scope
        常见故障包括坍缩、红线异常、镀层缺陷，通常需要结合看门狗与判官日志定位。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "从代码的异常类定义推断，谐振腔可能遇到哪些类型的故障？",
        kb_path,
        project_root,
    )

    assert result["sources"][0] == "谐振腔故障类型"
    assert "坍缩" in result["answer"]
    assert "镀层缺陷" in result["answer"]


def test_answer_question_fast_path_does_not_read_raw_materials_by_default(
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

    assert result["sources"] == []
    assert result["confidence"] == "low"
    assert "no formal entries" in result["answer"].lower()


def test_answer_question_material_fallback_requires_explicit_opt_in(
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
    monkeypatch.setenv("SEDIMENT_RUNTIME_ALLOW_MATERIAL_FALLBACK", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question("alert_rules.yaml中定义了多少种告警规则？", kb_path, project_root)

    assert "16" in result["answer"]
    assert "yaml/alert_rules.yaml" in result["sources"]
    assert result["exploration_summary"]["mode"] == "benchmark-material-fastpath"


def test_answer_question_local_fast_path_prefers_diagnostic_scope_and_supporting_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "回音壁.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - monitoring.md
        ---
        # 回音壁

        回音壁是监测嗡鸣度的传感器设备。

        ## Scope
        回音壁持续提供嗡鸣度与底噪数据。
        回音壁盲区会导致关键区域漏检，使判官拿到的样本不完整。

        ## Related
        - [[盲区]] - 盲区会直接削弱监测覆盖。
        """,
    )
    _write(
        kb_path / "entries" / "盲区.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - incident.md
        ---
        # 盲区

        盲区是回音壁无法覆盖的监测死角。

        ## Scope
        盲区会导致潮涌与暗流漏检，并放大误判风险。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "根据回音壁部署优化建议，当前监测系统的最大缺陷是什么？",
        kb_path,
        project_root,
    )

    assert result["sources"][0] == "回音壁"
    assert "盲区" in result["answer"]
    assert "漏检" in result["answer"]


def test_answer_question_local_fast_path_prefers_canonical_target_for_node_wrapper_queries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "驿站.md",
        """
        ---
        type: concept
        status: fact
        aliases: [驿站节点]
        sources:
          - topology.md
        ---
        # 驿站

        驿站是传输链路中的中继与缓冲节点。

        ## Scope
        驿站优先部署在高频路径、跨区边界和偏远接入区，用于负载均衡和分段缓存。
        """,
    )
    _write(
        kb_path / "entries" / "信使路由策略.md",
        """
        ---
        type: concept
        status: fact
        aliases: [信使路由表]
        sources:
          - routes.yaml
        ---
        # 信使路由策略

        信使路由策略定义了走线、接力、分流和合流等转发方式。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "从部署拓扑和路由表看，驿站节点的部署策略是什么？",
        kb_path,
        project_root,
    )

    assert result["sources"][0] == "驿站"
    assert "高频路径" in result["answer"]
    assert "负载均衡" in result["answer"]


def test_answer_question_local_fast_path_uses_related_causal_support_for_why_questions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "回音壁监测点.md",
        """
        ---
        type: concept
        status: fact
        aliases: [回音壁监测点配置, 回音壁监测点配置.xml]
        sources:
          - monitoring.xml
        ---
        # 回音壁监测点

        回音壁监测点定义了固定式、嵌入式和移动式回音壁在关键区域的部署位置与采样参数。

        ## Scope
        当前监测点类型包括固定式、嵌入式、移动式。

        ## Related
        - [[盲区]] - 盲区会直接削弱关键区域的监测覆盖。
        """,
    )
    _write(
        kb_path / "entries" / "盲区.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - incident.md
        ---
        # 盲区

        盲区是回音壁无法覆盖的监测死角。

        ## Scope
        盲区会导致潮涌与暗流漏检，并放大误判风险。
        过去两个季度发现的暗流事件中，71% 起始于盲区或盲区边缘。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "为什么Q3事故复盘建议增加回音壁监测点？",
        kb_path,
        project_root,
    )

    assert "盲区" in result["answer"]
    assert "漏检" in result["answer"]
    assert "盲区" in result["sources"]


def test_answer_question_local_fast_path_diagnosis_can_follow_related_causal_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "清浊比.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - metrics.md
        ---
        # 清浊比

        清浊比是纯净哈基米与散斑的比例。

        ## Scope
        清浊比持续下降通常说明散斑泄漏正在扩大。

        ## Related
        - [[镀层晦暗]] - 镀层老化会拉低清浊比。
        """,
    )
    _write(
        kb_path / "entries" / "回音壁.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - monitoring.md
        ---
        # 回音壁

        回音壁是监测嗡鸣度的传感器设备。

        ## Scope
        回音壁出现毛刺往往意味着嗡鸣度波动正在放大。

        ## Related
        - [[镀层晦暗]] - 镀层老化会诱发毛刺。
        """,
    )
    _write(
        kb_path / "entries" / "镀层晦暗.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - coating.md
        ---
        # 镀层晦暗

        镀层晦暗是镀层老化导致的故障征兆。

        ## Scope
        镀层晦暗会引发哈基米泄漏、散斑增加和回音壁毛刺，必要时需要安排换羽。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "综合推断：如果清浊比持续下降且回音壁出现毛刺，可能是什么问题？",
        kb_path,
        project_root,
    )

    assert "镀层晦暗" in result["answer"]
    assert "换羽" in result["answer"]
    assert "镀层晦暗" in result["sources"]


def test_answer_question_local_fast_path_prefers_tail_target_for_quality_question(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "听风者.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - weekly.md
        ---
        # 听风者

        听风者是负责分析嗡鸣度趋势的团队。
        """,
    )
    _write(
        kb_path / "entries" / "指标.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - metric_schema.md
        ---
        # 指标

        指标是系统中的通用统计项。
        """,
    )
    _write(
        kb_path / "entries" / "嗡鸣度.md",
        """
        ---
        type: concept
        status: fact
        aliases: [hum_level]
        sources:
          - metrics.md
        ---
        # 嗡鸣度

        嗡鸣度是衡量系统活跃状态的核心指标。

        ## Scope
        判断嗡鸣度数据质量时，必须同时检查底噪、毛刺数量、峰谷差和留声机回放中的幽灵读数。

        ## Related
        - [[留声机]] - 用于回放历史样本。
        """,
    )
    _write(
        kb_path / "entries" / "留声机.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - recorder.md
        ---
        # 留声机

        留声机用于回放历史嗡鸣度样本，辅助识别幽灵读数。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "综合听风者周报模板和指标定义，如何判断嗡鸣度数据的质量？",
        kb_path,
        project_root,
    )

    assert result["sources"][0] == "嗡鸣度"
    assert "底噪" in result["answer"]
    assert "峰谷差" in result["answer"]


def test_answer_question_local_fast_path_uses_condition_scope_for_decider_question(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "判官系统.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - judge.md
        ---
        # 判官系统

        判官系统是自动决策层，负责评估异常并触发处置。

        ## Scope
        当嗡鸣度突破红线且分流无法压低负载时，判官系统会决定触发泄洪。
        只有确认热备和锁龙井都无法化解过载时，才允许进入泄洪。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "判官系统在什么条件下会决定触发泄洪？",
        kb_path,
        project_root,
    )

    assert result["sources"][0] == "判官系统"
    assert "突破红线" in result["answer"]
    assert "泄洪" in result["answer"]


def test_answer_question_local_fast_path_trigger_question_can_follow_causal_neighbor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "换羽.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - coating.md
        ---
        # 换羽

        换羽是定期更换镀层的维护操作。

        ## Scope
        标准维护周期为 180 天，但存在镀层异常时需要提前执行。
        """,
    )
    _write(
        kb_path / "entries" / "晦暗.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - coating.md
        ---
        # 晦暗

        晦暗是镀层老化导致的故障征兆。

        ## Scope
        一旦照骨灯发现晦暗或镀层反射率低于 72%，就必须立即触发换羽。

        ## Related
        - [[换羽]] - 晦暗会直接触发换羽。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "镀层材质参数中，换羽的触发条件是什么？",
        kb_path,
        project_root,
    )

    assert "换羽" in result["sources"]
    assert "72%" in result["answer"] or "晦暗" in result["answer"]


def test_answer_question_local_fast_path_lifecycle_question_can_pull_canonical_stage_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)
    _write(
        kb_path / "entries" / "管理谐振腔的完整生命周期.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - lifecycle.md
        ---
        # 管理谐振腔的完整生命周期

        管理谐振腔的完整生命周期是一个包装性说明条目。

        ## Related
        - [[谐振腔生命周期]] - 更具体的正式阶段定义。
        """,
    )
    _write(
        kb_path / "entries" / "谐振腔生命周期.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - lifecycle.md
        ---
        # 谐振腔生命周期

        谐振腔生命周期包括五个阶段：建设验收、开光启用、正常运行、维护更新、退役处置。
        """,
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "1")
    server_module = _reload_server(
        project_root,
        kb_path,
        command=["definitely-not-a-real-cli"],
    )
    result = server_module.answer_question(
        "管理谐振腔的完整生命周期会经历哪些阶段？",
        kb_path,
        project_root,
    )

    assert "谐振腔生命周期" in result["sources"]
    assert "建设验收" in result["answer"]
    assert "退役处置" in result["answer"]


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
