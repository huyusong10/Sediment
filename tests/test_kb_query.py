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
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _build_sample_kb(root: Path) -> Path:
    kb_path = root / "knowledge-base"

    _write(
        kb_path / "entries" / "热备份.md",
        """
        ---
        aliases: [热切换]
        status: formal
        ---
        # 热备份

        热备份是在主链路失效前，先准备好可接管的[[金蝉脱壳]]与[[回音壁]]能力。

        ## Context
        适用于需要连续服务、不能接受长时间中断的核心系统，尤其适用于存在主备切换流程的场景。

        ## Why This Matters
        如果没有热备份，故障发生时只能临时拼装恢复路径，导致恢复时间变长，甚至放大业务损失。

        ## Common Pitfalls
        常见误区是把冷备份误当成热备份，或者只准备数据副本却没有验证[[回音壁]]和[[金蝉脱壳]]的接管链路。

        ## Related
        - [[金蝉脱壳]] - 热备份依赖的切换策略
        - [[回音壁]] - 需要保持观测链路同步

        ## Source
        - backup_design.md
        """,
    )

    _write(
        kb_path / "entries" / "泄洪前须确认热备份.md",
        """
        ---
        aliases: []
        status: formal
        ---
        # 泄洪前须确认热备份

        进行[[泄洪]]之前，必须先确认[[热备份]]处于可接管状态，否则风险会被放大。

        ## Context
        适用于需要执行主动流量转移、降载或保护性排洪的高风险操作场景，尤其适用于生产高峰时段。

        ## Why This Matters
        泄洪会主动改变流量与容量分布，如果热备份没有准备好，系统会在保护动作之后暴露出新的单点故障。

        ## Evidence / Reasoning
        多次故障复盘都表明，先确认热备份再执行泄洪，可以把恢复路径从临时抢修转成受控切换，减少二次事故。

        ## Common Pitfalls
        常见误区是把“已有备份数据”当成“可热切换”，或者认为泄洪只是临时动作，不需要依赖[[热备份]]和[[回音壁]]的协同。

        ## Related
        - [[热备份]] - 本规则的前提条件
        - [[泄洪]] - 适用的风险动作

        ## Source
        - flood_runbook.md
        """,
    )

    _write(
        kb_path / "entries" / "暗流检测.md",
        """
        ---
        aliases: []
        status: formal
        ---
        # 暗流检测

        暗流检测需要把[[暗流]]症状和[[回音壁]]观测联合起来判断。

        ## Context
        适用于故障排查和异常定位场景，需要结合观测指标与链路行为做综合判断。

        ## Why This Matters
        仅看单一指标容易漏掉暗流扩散的早期信号，联合检测可以更早发现风险。

        ## Common Pitfalls
        容易把短时抖动误判为暗流，或者忽略与[[回音壁]]观测之间的时序关系。

        ## Related
        - [[暗流]] - 被检测的异常概念
        - [[回音壁]] - 关键观测来源

        ## Source
        - darkflow_notes.md
        """,
    )

    _write(
        kb_path / "entries" / "账房审计.md",
        """
        ---
        aliases: []
        status: formal
        ---
        # 账房审计

        账房审计会跟踪[[暗流]]带来的异常收支，并与[[回音壁]]记录做交叉验证。

        ## Context
        适用于审计、异常回放和事后追责场景，需要将系统行为和账务痕迹对齐。

        ## Why This Matters
        没有账房审计时，暗流类问题会只留下模糊症状，难以还原影响范围。

        ## Common Pitfalls
        常见误区是只核对结果，不核对过程，导致[[暗流]]的来源无法追溯。

        ## Related
        - [[暗流]] - 审计对象之一
        - [[回音壁]] - 关键交叉验证来源

        ## Source
        - audit_playbook.md
        """,
    )

    _write(
        kb_path / "entries" / "薄弱条目.md",
        """
        ---
        aliases: []
        status: formal
        ---
        # 薄弱条目

        这是一个过于简单的[[暗流]]描述。

        ## Context
        太短。

        ## Related
        - [[暗流]] - 单一关系
        """,
    )

    _write(
        kb_path / "placeholders" / "泄洪.md",
        """
        ---
        aliases: []
        tags: [placeholder]
        status: placeholder
        ---
        # 泄洪

        #status/placeholder
        - [ ] Needs human or agent to perform inductive reasoning to complete this concept.

        > Appears in: [[泄洪前须确认热备份]]

        This concept is referenced but not yet defined.
        """,
    )

    _write(
        kb_path / "placeholders" / "暗流.md",
        """
        ---
        aliases: []
        tags: [placeholder]
        status: placeholder
        ---
        # 暗流

        #status/placeholder
        - [ ] Needs human or agent to perform inductive reasoning to complete this concept.

        > Appears in: [[暗流检测]]

        This concept is referenced but not yet defined.
        """,
    )

    return kb_path


def test_inventory_shortlist_neighbors_and_snippets(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)

    data = inventory(kb_path)
    assert "热备份" in data["entries"]
    assert data["aliases"]["热切换"] == ["热备份"]

    ranked = shortlist("什么是热切换？", inventory_data=data, limit=3)
    assert ranked[0]["name"] == "热备份"

    graph = neighbors(["泄洪前须确认热备份"], inventory_data=data, depth=1, limit=6)
    graph_names = {item["name"] for item in graph}
    assert "热备份" in graph_names
    assert "泄洪" in graph_names

    excerpt_map = snippets(["热备份"], question="为什么要热备份", inventory_data=data)
    sections = {item["section"] for item in excerpt_map["热备份"]["snippets"]}
    assert "Why This Matters" in sections


def test_validate_answer_rejects_placeholder_only_sources(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)
    data = inventory(kb_path)

    valid = validate_answer(
        {
            "answer": "热备份用于在故障前准备接管路径。",
            "sources": ["热备份"],
            "confidence": "high",
            "exploration_summary": {
                "entries_scanned": 4,
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
                "entries_scanned": 4,
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


def test_audit_kb_reports_quality_and_canonical_gaps(tmp_path: Path) -> None:
    kb_path = _build_sample_kb(tmp_path)

    report = audit_kb(kb_path)
    assert report["hard_fail_entry_count"] >= 1
    assert "薄弱条目" in report["hard_fail_entries"]
    assert report["promotable_placeholder_count"] >= 1
    assert any(item["name"] == "暗流" for item in report["promotable_placeholders"])
    assert report["canonical_gap_count"] >= 1
    assert any(item["name"] == "泄洪" for item in report["canonical_gaps"])
