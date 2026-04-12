from __future__ import annotations

import textwrap
from pathlib import Path

from skills.explore.scripts.kb_query import (
    audit_kb,
    inventory,
    neighbors,
    shortlist,
    snippets,
    validate_answer,
    validate_entry,
)
from skills.tidy.scripts.tidy_utils import collect_ref_contexts, find_dangling_links


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
        aliases: [热切换]
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

    return kb_path


def test_inventory_shortlist_neighbors_and_snippets(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)

    data = inventory(kb_path)
    assert "热备份" in data["entries"]
    assert data["aliases"]["热切换"] == ["热备份"]
    assert data["docs"]["热备份"]["entry_type"] == "concept"
    assert data["docs"]["泄洪前先确认热备份"]["entry_type"] == "lesson"
    assert data["docs"]["热备份"]["summary"] == "热备份是在主链路失效前准备好的可接管路径能力。"

    ranked = shortlist("什么是热切换？", inventory_data=data, limit=3)
    assert ranked[0]["name"] == "热备份"

    graph = neighbors(["泄洪前先确认热备份"], inventory_data=data, depth=1, limit=6)
    graph_names = {item["name"] for item in graph}
    assert "热备份" in graph_names
    assert "泄洪" in graph_names

    excerpt_map = snippets(["热备份"], question="热备份适用于什么场景", inventory_data=data)
    sections = {item["section"] for item in excerpt_map["热备份"]["snippets"]}
    assert "Scope" in sections


def test_snippets_prioritize_why_for_lesson_queries(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)
    excerpt_map = snippets(
        ["泄洪前先确认热备份"],
        question="为什么泄洪前要先确认热备份？",
        inventory_data=inventory(kb_path),
    )

    assert excerpt_map["泄洪前先确认热备份"]["snippets"][0]["section"] == "Why"


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


def test_audit_kb_reports_v4_quality_and_concept_gaps(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)

    report = audit_kb(kb_path)
    assert report["hard_fail_entry_count"] >= 1
    assert "薄弱条目" in report["hard_fail_entries"]
    assert report["promotable_placeholder_count"] >= 1
    assert any(item["name"] == "暗流" for item in report["promotable_placeholders"])
    assert report["canonical_gap_count"] >= 1
    assert any(item["name"] == "泄洪" for item in report["canonical_gaps"])


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
