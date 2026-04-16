from __future__ import annotations

import textwrap
from pathlib import Path

import yaml

from sediment.settings import clear_settings_cache
from sediment.skills.explore.scripts.kb_query import (
    audit_kb,
    inventory,
    neighbors,
    prepare_explore_context,
    shortlist,
    snippets,
    validate_answer,
    validate_entry,
)
from sediment.skills.tidy.scripts.tidy_utils import (
    collect_ref_contexts,
    find_dangling_links,
    plan_index_repairs,
)
from tests.config_helpers import write_test_config


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _build_sample_kb(root: Path) -> Path:
    kb_path = root / "knowledge-base"

    _write(
        kb_path / "entries" / "热备份.md",
        """
        ---
        type: concept
        status: fact
        aliases: [热切换, hot swap]
        sources:
          - backup_design.md
        ---
        # 热备份

        热备份是在主链路失效前准备好的可接管路径能力。

        ## Scope
        适用于需要连续服务、不能接受长时间中断的核心系统，尤其适用于存在主备切换流程的场景。

        ## Related
        - [[金蝉脱壳]] - 热备份依赖的切换策略
        - [[回音壁]] - 需要同步观测链路
        """,
    )

    _write(
        kb_path / "entries" / "泄洪前先确认热备份.md",
        """
        ---
        type: lesson
        status: inferred
        aliases: []
        sources:
          - flood_runbook.md
        ---
        # 泄洪前先确认热备份

        进行[[泄洪]]之前，必须先确认[[热备份]]处于可接管状态。

        ## Trigger
        适用于需要主动切流、泄洪或保护性降载的高风险操作场景。

        ## Why
        泄洪会改变流量和容量分布，如果热备份没有准备好，系统会在保护动作之后暴露新的单点故障。

        ## Risks
        常见误区是把“已有备份数据”误当成“可热切换”，从而在执行[[泄洪]]后放大恢复风险。

        ## Related
        - [[热备份]] - 本规则的前提能力
        - [[泄洪]] - 适用的风险动作
        """,
    )

    _write(
        kb_path / "entries" / "暗流检测.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - darkflow_notes.md
        ---
        # 暗流检测

        暗流检测需要联合[[暗流]]症状和[[回音壁]]观测来判断异常。

        ## Scope
        适用于故障排查和异常定位场景，需要结合观测指标与链路行为做综合判断。

        ## Related
        - [[暗流]] - 被检测的异常概念
        - [[回音壁]] - 关键观测来源
        """,
    )

    _write(
        kb_path / "entries" / "账房审计.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - audit_playbook.md
        ---
        # 账房审计

        账房审计会跟踪[[暗流]]带来的异常收支，并与[[回音壁]]记录做交叉验证。

        ## Scope
        适用于审计、异常回放和事后追责场景，需要将系统行为和账务痕迹对齐。

        ## Related
        - [[暗流]] - 审计对象之一
        - [[回音壁]] - 关键交叉验证来源
        """,
    )

    _write(
        kb_path / "entries" / "暗流回放.md",
        """
        ---
        type: lesson
        status: inferred
        aliases: []
        sources:
          - darkflow_replay.md
        ---
        # 暗流回放时优先对齐回音壁

        暗流回放时应先对齐[[回音壁]]时间线，再解释[[暗流]]传播路径。

        ## Trigger
        适用于故障复盘、异常回放和时间线重建场景。

        ## Why
        如果时间线没有先对齐，就会把观测抖动误判为真正的暗流传播。

        ## Risks
        直接解释[[暗流]]扩散路径，容易在复盘中制造错误因果链。

        ## Related
        - [[暗流]] - 被回放的异常对象
        - [[回音壁]] - 时间线基准
        """,
    )

    _write(
        kb_path / "entries" / "薄弱条目.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - weak_note.md
        ---
        # 薄弱条目

        这是一个过于简单的[[暗流]]描述。

        ## Related
        - [[暗流]] - 单一关系
        """,
    )

    _write(
        kb_path / "placeholders" / "泄洪.md",
        """
        ---
        type: placeholder
        aliases: []
        ---
        # 泄洪

        这个概念在知识库中被引用了，但目前还没有足够清晰的定义可供提升。
        """,
    )

    _write(
        kb_path / "placeholders" / "暗流.md",
        """
        ---
        type: placeholder
        aliases: []
        ---
        # 暗流

        这个概念在知识库中被引用了，但目前还没有足够清晰的定义可供提升。

        > Appears in: [[暗流检测]]
        """,
    )

    _write(
        kb_path / "index.root.md",
        """
        ---
        kind: index
        segment: root
        ---
        # 索引入口

        这是全局导航入口，优先跳转到子索引。

        - [[index.ops]]
        - [[index.darkflow]]
        """,
    )
    _write(
        kb_path / "indexes" / "index.ops.md",
        """
        ---
        kind: index
        segment: ops
        ---
        # 运维索引

        聚焦切流、泄洪和热备份策略。

        - [[热备份]]
        - [[泄洪前先确认热备份]]
        """,
    )
    _write(
        kb_path / "indexes" / "index.darkflow.md",
        """
        ---
        kind: index
        segment: darkflow
        ---
        # 暗流索引

        聚焦暗流定位与回放。

        - [[暗流检测]]
        - [[暗流回放]]
        """,
    )

    write_test_config(
        root,
        kb_path=kb_path,
        state_dir=root / "state",
    )
    return kb_path


def test_inventory_shortlist_neighbors_and_snippets(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)

    data = inventory(kb_path)
    assert "热备份" in data["entries"]
    assert data["aliases"]["热切换"] == ["热备份"]
    assert data["docs"]["热备份"]["entry_type"] == "concept"
    assert data["docs"]["泄洪前先确认热备份"]["entry_type"] == "lesson"
    assert data["docs"]["热备份"]["summary"] == "热备份是在主链路失效前准备好的可接管路径能力。"
    assert "index.root" in data["indexes"]
    assert "index.ops" in data["indexes"]

    ranked = shortlist("什么是热切换？", inventory_data=data, limit=3)
    assert ranked[0]["name"] == "热备份"

    graph = neighbors(["泄洪前先确认热备份"], inventory_data=data, depth=1, limit=6)
    graph_names = {item["name"] for item in graph}
    assert "热备份" in graph_names
    assert "泄洪" in graph_names

    excerpt_map = snippets(["热备份"], question="热备份适用于什么场景", inventory_data=data)
    sections = {item["section"] for item in excerpt_map["热备份"]["snippets"]}
    assert "Scope" in sections


def test_inventory_preserves_dotted_numbers_and_versions_in_summary(tmp_path: Path) -> None:
    kb_path = tmp_path / "knowledge-base"
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

        红线是嗡鸣度绝对不可超过的安全阈值，标准腔默认值为 720.0Hz，判官配置版本为 v3.2.1。
        """,
    )

    data = inventory(kb_path)

    assert "720.0Hz" in data["docs"]["红线"]["summary"]
    assert "v3.2.1" in data["docs"]["红线"]["summary"]


def test_snippets_prioritize_why_for_lesson_queries(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)
    excerpt_map = snippets(
        ["泄洪前先确认热备份"],
        question="为什么泄洪前要先确认热备份？",
        inventory_data=inventory(kb_path),
    )

    assert excerpt_map["泄洪前先确认热备份"]["snippets"][0]["section"] == "Why"


def test_multilingual_query_support_for_shortlist_and_focus(tmp_path: Path, monkeypatch) -> None:
    kb_path = _build_sample_kb(tmp_path)
    data = inventory(kb_path)

    ranked = shortlist("What is hot swap?", inventory_data=data, limit=3)
    assert ranked[0]["name"] == "热备份"

    config_path = write_test_config(
        tmp_path,
        kb_path=kb_path,
        state_dir=tmp_path / "state",
    )
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    payload["knowledge"] = {"query_languages": "EN"}
    config_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    clear_settings_cache()
    ranked_with_override = shortlist("What is hot swap?", inventory_data=data, limit=3)
    assert ranked_with_override[0]["name"] == "热备份"

    excerpt_map = snippets(
        ["泄洪前先确认热备份"],
        question="Why should we confirm backup before draining traffic?",
        inventory_data=data,
    )
    assert excerpt_map["泄洪前先确认热备份"]["snippets"][0]["section"] == "Why"


def test_shortlist_prefers_specific_targets_over_generic_fragments(tmp_path: Path) -> None:
    kb_path = tmp_path / "knowledge-base"

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

        ## Scope
        这里只提供泛化说明，不直接回答任何具体能力边界。
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

        哈基米是系统运转依赖的基础能量单元。
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

        ## Scope
        设计哲学要求把安全阈值、审计链路和热备切换统一纳入系统骨架，而不是依赖单点经验。
        """,
    )

    data = inventory(kb_path)

    ranked = shortlist(
        "从暗流调查报告和渡鸦守则看，隐身衣技术目前能完全避免检测吗？",
        inventory_data=data,
        limit=4,
    )
    ranked_names = [item["name"] for item in ranked]
    assert ranked_names.index("隐身衣") < ranked_names.index("技术")

    design_ranked = shortlist(
        "从全系统角度推断，哈基米系统的设计哲学是什么？",
        inventory_data=data,
        limit=4,
    )
    assert design_ranked[0]["name"] == "哈基米系统设计哲学"


def test_shortlist_prefers_fault_taxonomy_over_generic_or_wrapped_entries(tmp_path: Path) -> None:
    kb_path = tmp_path / "knowledge-base"

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
        """,
    )

    ranked = shortlist(
        "从代码的异常类定义推断，谐振腔可能遇到哪些类型的故障？",
        inventory_data=inventory(kb_path),
        limit=4,
    )

    assert ranked[0]["name"] == "谐振腔故障类型"


def test_shortlist_prefers_canonical_monitoring_surface_over_q3_wrapper_phrase(tmp_path: Path) -> None:
    kb_path = tmp_path / "knowledge-base"

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
        """,
    )
    _write(
        kb_path / "entries" / "复盘.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - review.md
        ---
        # 复盘

        复盘是历史事件的回顾整理。
        """,
    )

    ranked = shortlist(
        "为什么Q3事故复盘建议增加回音壁监测点？",
        inventory_data=inventory(kb_path),
        limit=4,
    )

    assert ranked[0]["name"] == "回音壁监测点"


def test_shortlist_prefers_canonical_bare_term_from_node_wrapper_surface(tmp_path: Path) -> None:
    kb_path = tmp_path / "knowledge-base"

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

    ranked = shortlist(
        "从部署拓扑和路由表看，驿站节点的部署策略是什么？",
        inventory_data=inventory(kb_path),
        limit=4,
    )

    assert ranked[0]["name"] == "驿站"


def test_shortlist_normalizes_complete_target_surface(tmp_path: Path) -> None:
    kb_path = tmp_path / "knowledge-base"

    _write(
        kb_path / "entries" / "谐振腔生命周期.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - lifecycle.txt
        ---
        # 谐振腔生命周期

        谐振腔生命周期包括五个阶段：建设验收、开光启用、正常运行、维护更新、退役处置。
        """,
    )
    _write(
        kb_path / "entries" / "生命周期.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - glossary.md
        ---
        # 生命周期

        生命周期是正式流程中的一个阶段。
        """,
    )

    ranked = shortlist(
        "谐振腔的完整生命周期需要经历哪些阶段？",
        inventory_data=inventory(kb_path),
        limit=4,
    )

    assert ranked[0]["name"] == "谐振腔生命周期"


def test_validate_entry_supports_v4_types(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)

    concept = validate_entry(path=kb_path / "entries" / "热备份.md")
    lesson = validate_entry(path=kb_path / "entries" / "泄洪前先确认热备份.md")
    placeholder = validate_entry(path=kb_path / "placeholders" / "泄洪.md")

    assert concept["valid"] is True
    assert lesson["valid"] is True
    assert placeholder["valid"] is True


def test_validate_entry_rejects_title_only_entries(tmp_path: Path) -> None:
    kb_path = tmp_path / "knowledge-base"

    _write(
        kb_path / "entries" / "空概念.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - doc.md
        ---
        # 空概念

        ## Scope
        适用于任何需要测试空摘要校验的场景。

        ## Related
        - [[热备份]] - 参考已有概念
        """,
    )
    _write(
        kb_path / "placeholders" / "空占位.md",
        """
        ---
        type: placeholder
        aliases: []
        ---
        # 空占位
        """,
    )

    concept = validate_entry(path=kb_path / "entries" / "空概念.md")
    placeholder = validate_entry(path=kb_path / "placeholders" / "空占位.md")

    assert concept["valid"] is False
    assert "summary/core proposition" in " ".join(concept["hard_failures"])
    assert placeholder["valid"] is False
    assert "gap description" in " ".join(placeholder["hard_failures"])


def test_validate_answer_rejects_placeholder_only_sources(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)
    data = inventory(kb_path)

    valid = validate_answer(
        {
            "answer": "热备份用于在故障前准备接管路径。",
            "sources": ["热备份"],
            "confidence": "high",
            "exploration_summary": {
                "entries_scanned": 6,
                "entries_read": 2,
                "links_followed": 1,
                "mode": "definition-driven",
            },
            "gaps": [],
            "contradictions": [],
        },
        inventory_data=data,
    )
    assert valid["valid"] is True

    invalid = validate_answer(
        {
            "answer": "泄洪是一个动作。",
            "sources": ["泄洪"],
            "confidence": "medium",
            "exploration_summary": {
                "entries_scanned": 6,
                "entries_read": 1,
                "links_followed": 0,
                "mode": "definition-driven",
            },
            "gaps": [],
            "contradictions": [],
        },
        inventory_data=data,
    )
    assert invalid["valid"] is False
    assert any("formal source" in error for error in invalid["errors"])


def test_validate_answer_rejects_runtime_prompt_leakage(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)
    data = inventory(kb_path)

    leaked = validate_answer(
        {
            "answer": (
                'claude -p --bare --json-schema {"type":"object","additionalProperties": false} '
                'You are the internal Sediment explore runtime. Return JSON only.'
            ),
            "sources": ["热备份", "正式流程"],
            "confidence": "low",
            "exploration_summary": {
                "entries_scanned": 6,
                "entries_read": 2,
                "links_followed": 1,
                "mode": "definition-driven",
            },
            "gaps": [],
            "contradictions": [],
        },
        inventory_data=data,
    )

    assert leaked["valid"] is False
    assert any("prompt/schema leakage" in error for error in leaked["errors"])


def test_audit_kb_reports_v4_quality_and_concept_gaps(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)

    report = audit_kb(kb_path)
    assert report["hard_fail_entry_count"] >= 1
    assert "薄弱条目" in report["hard_fail_entries"]
    assert report["promotable_placeholder_count"] >= 1
    assert any(item["name"] == "暗流" for item in report["promotable_placeholders"])
    assert report["canonical_gap_count"] >= 1
    assert any(item["name"] == "泄洪" for item in report["canonical_gaps"])
    assert report["index_count"] >= 3
    assert report["root_index_present"] is True
    assert report["unknown_index_link_count"] == 0
    assert report["invalid_index_count"] == 0


def test_audit_kb_reports_invalid_placeholder_and_provenance_noise(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)
    _write(
        kb_path / "entries" / "来源污染.md",
        """
        ---
        type: lesson
        status: inferred
        aliases: []
        sources:
          - retro.md
        ---
        # 来源污染

        先定义[[热备份]]，再执行变更。

        ## Trigger
        在执行高风险变更前。

        ## Why
        这样可以减少误判和切换期间的放大故障。

        ## Risks
        跳过这一步会放大恢复成本。

        ## Sources
        [[不该入图的来源]]

        ## Related
        - [[热备份]] - 前置概念
        """,
    )
    _write(
        kb_path / "placeholders" / "坏占位.md",
        """
        ---
        type: placeholder
        aliases: []
        ---
        # 坏占位

        > Appears in: [[来源污染]]
        """,
    )

    report = audit_kb(kb_path)

    assert report["invalid_placeholder_count"] >= 1
    assert "坏占位" in report["invalid_placeholder_entries"]
    assert report["provenance_contamination_count"] >= 1
    assert any(item["name"] == "来源污染" for item in report["provenance_contamination"])


def test_provenance_sections_do_not_create_graph_noise(tmp_path: Path) -> None:
    kb_path = tmp_path / "knowledge-base"
    _write(
        kb_path / "entries" / "权限边界.md",
        """
        ---
        type: lesson
        status: inferred
        aliases: []
        sources:
          - 2024年Q3支付模块故障复盘
          - 权限系统重构设计文档
        ---
        # 权限边界

        先定义[[权限模型]]，再讨论接口细节。

        ## Trigger
        适用于多角色接口设计场景。

        ## Why
        权限是结构性决策，顺序错了会导致返工。

        ## Risks
        如果跳过这一步，测试和实现会基于不同权限假设展开。

        ## Related
        - [[权限模型]] - 前置依赖

        ## 来源
        [[2024年Q3支付模块故障复盘]] [[权限系统重构设计文档]]
        """,
    )
    _write(
        kb_path / "entries" / "来源别名.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - source_bundle.md
        ---
        # 来源别名

        来源别名用于验证 Sources 标题不会污染图谱。

        ## Scope
        适用于来源字段兼容性测试。

        ## Sources
        [[另一份来源文档]]

        ## Related
        - [[权限模型]] - 同样依赖 provenance 兼容
        """,
    )

    dangling = find_dangling_links(str(kb_path))
    contexts = collect_ref_contexts(str(kb_path), "权限模型")

    dangling_names = {item["link"] for item in dangling}
    assert "2024年Q3支付模块故障复盘" not in dangling_names
    assert "权限系统重构设计文档" not in dangling_names
    assert "另一份来源文档" not in dangling_names
    assert all("2024年Q3支付模块故障复盘" not in item for item in contexts)


def test_prepare_explore_context_prefers_index_routed_entries(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)
    data = inventory(kb_path)

    context = prepare_explore_context("泄洪前做什么检查？", inventory_data=data)

    assert context["index_routing"]["selected_indexes"]
    assert context["index_routing"]["selected_indexes"][0]["name"] == "index.root"
    assert any("index" in item["matched_fields"] for item in context["initial_shortlist"])


def test_prepare_explore_context_supports_root_only_index_routing(tmp_path: Path) -> None:
    kb_path = tmp_path / "knowledge-base"
    _write(
        kb_path / "entries" / "热备份.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - sample.md
        ---
        # 热备份

        热备份是在主链路失效前准备好的可接管路径能力。

        ## Scope
        适用于需要连续服务、不能接受长时间中断的核心系统。

        ## Related
        - [[回音壁]] - 同步观测链路
        """,
    )
    _write(
        kb_path / "placeholders" / "回音壁.md",
        """
        ---
        type: placeholder
        aliases: []
        ---
        # 回音壁

        等待补充定义。
        """,
    )
    _write(
        kb_path / "index.root.md",
        """
        ---
        kind: index
        segment: root
        ---
        # 根索引

        直接把常用正式条目挂在根索引下。

        - [[热备份]]
        """,
    )
    write_test_config(
        tmp_path,
        kb_path=kb_path,
        state_dir=tmp_path / "state",
    )
    data = inventory(kb_path)

    context = prepare_explore_context("什么是热备份？", inventory_data=data)

    assert context["index_routing"]["selected_indexes"]
    assert context["index_routing"]["selected_indexes"][0]["name"] == "index.root"
    assert context["index_routing"]["preferred_entries"] == ["热备份"]
    assert any(item["name"] == "热备份" for item in context["expanded_candidates"])


def test_prepare_explore_context_keeps_shortlist_priority_in_expanded_candidates(
    tmp_path: Path,
) -> None:
    kb_path = _build_sample_kb(tmp_path)
    data = inventory(kb_path)

    context = prepare_explore_context("什么是热备份？", inventory_data=data)

    assert context["initial_shortlist"][0]["name"] == "热备份"
    assert context["expanded_candidates"][0]["name"] == "热备份"


def test_audit_kb_reports_invalid_index_contracts(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)
    _write(
        kb_path / "indexes" / "index.bad.md",
        """
        ---
        kind: note
        segment: wrong
        last_tidied_at: 2026/04/13
        entry_count: 1
        estimated_tokens: 64
        ---
        # 错误索引

        这个索引契约是坏的。

        - [[热备份]]
        """,
    )

    report = audit_kb(kb_path)

    assert report["invalid_index_count"] >= 1
    assert "index.bad" in report["invalid_indexes"]


def test_plan_index_repairs_surfaces_index_governance_actions(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)
    _write(
        kb_path / "indexes" / "index.bad.md",
        """
        ---
        kind: note
        segment: wrong
        ---
        # 错误索引

        错误入口。

        - [[不存在的条目]]
        """,
    )
    _write(
        kb_path / "entries" / "未覆盖条目.md",
        """
        ---
        type: concept
        status: fact
        aliases: []
        sources:
          - extra.md
        ---
        # 未覆盖条目

        这是一个没有被索引覆盖的概念。

        ## Scope
        用于验证索引覆盖修复队列。

        ## Related
        - [[热备份]] - 只是一个连接
        """,
    )

    actions = plan_index_repairs(kb_path)
    action_names = {item["action"] for item in actions}

    assert "repair_index_contract" in action_names
    assert "repair_index_link" in action_names
    assert "cover_entry_from_index" in action_names
