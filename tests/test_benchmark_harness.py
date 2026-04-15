from __future__ import annotations

import importlib.util
import json
import sys
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_HARNESS_ENTRY = REPO_ROOT / "benchmarks" / "scripts" / "harness_contract.py"
pytestmark = pytest.mark.skipif(
    not BENCHMARK_HARNESS_ENTRY.exists(),
    reason="local benchmark harness is not checked into git",
)


def _load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    if relative_path == "benchmarks/scripts/harness_contract.py":
        sys.modules.setdefault("harness_contract", module)
    spec.loader.exec_module(module)
    return module


def test_harness_contract_points_to_benchmark_results_and_repo_skills() -> None:
    contract = _load_module("benchmark_harness_contract", "benchmarks/scripts/harness_contract.py")

    paths = contract.load_benchmark_paths()

    assert paths.test_plan_path.name == "TEST_PLAN.md"
    assert paths.results_dir == paths.project_root / "benchmarks" / "results"
    assert paths.sample_workspace_dir == paths.project_root / "examples"
    assert (paths.skills_dir / "ingest" / "SKILL.md").exists()
    assert (paths.skills_dir / "tidy" / "SKILL.md").exists()


def test_run_all_scores_preflight_uses_repo_skill_sources() -> None:
    _load_module(
        "benchmark_harness_contract_preflight",
        "benchmarks/scripts/harness_contract.py",
    )
    run_all_scores = _load_module(
        "benchmark_run_all_scores",
        "benchmarks/scripts/run_all_scores.py",
    )

    preflight = run_all_scores.run_preflight_checks()

    assert preflight["results_layout"]["test_plan_path"].endswith("benchmarks/TEST_PLAN.md")
    for name, source in preflight["skill_sources"].items():
        assert f"src/sediment/skills/{name}/SKILL.md" in source


def test_copy_sample_kb_creates_clean_sample_workspace(tmp_path: Path) -> None:
    contract = _load_module(
        "benchmark_harness_contract_copy",
        "benchmarks/scripts/harness_contract.py",
    )

    kb_dir = tmp_path / "isolated" / "knowledge-base"
    (kb_dir / "entries").mkdir(parents=True)
    (kb_dir / "entries" / "热备份.md").write_text("# 热备份\n", encoding="utf-8")
    destination_root = tmp_path / "examples"

    copied = contract.copy_sample_kb(
        build_type="full",
        kb_dir=kb_dir,
        source_isolated_dir=tmp_path / "isolated",
        destination_root=destination_root,
        diagnostics={"entry_count": 1, "placeholder_count": 0, "avg_entry_size": 6.0},
    )

    assert (copied / "entries" / "热备份.md").exists()
    assert copied == destination_root
    assert not (copied / "manifest.json").exists()


def test_isolated_build_maps_cli_contract_to_agent_settings() -> None:
    _load_module("benchmark_harness_contract_settings", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build",
        "benchmarks/scripts/isolated_build.py",
    )

    claude_settings = isolated_build.build_benchmark_agent_settings("claude")["agent"]

    assert claude_settings["backend"] == "claude-code"
    codex_settings = isolated_build.build_benchmark_agent_settings("codex")["agent"]

    assert codex_settings["backend"] == "codex"
    assert codex_settings["reasoning_effort"] == "medium"
    assert "--full-auto" in codex_settings["extra_args"]
    assert "--ephemeral" in codex_settings["extra_args"]


def test_isolated_build_uses_smaller_full_batches_for_codex() -> None:
    _load_module("benchmark_harness_contract_batches", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_batches",
        "benchmarks/scripts/isolated_build.py",
    )

    assert isolated_build.full_build_ingest_batches("claude") == 3
    assert isolated_build.full_build_ingest_batches("codex") == 6


def test_ingest_prompt_hardens_execution_contract(tmp_path: Path) -> None:
    _load_module("benchmark_harness_contract_prompt", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_prompt",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)
    materials = [isolated_build.MATERIAL_DIR / "md" / "哈基米系统架构设计.md"]

    prompt = isolated_build.build_ingest_prompt(
        materials,
        isolated_dir,
        cli_value="codex",
    )

    assert "The run is considered failed if no formal entries are written." in prompt
    assert "Start writing into `$SEDIMENT_KB_PATH` within your first work cycle." in prompt
    assert "validate-entry" in prompt
    assert "sediment kb health --json" in prompt
    assert "## Active Batch Files" in prompt
    assert "哈基米系统架构设计.md" in prompt


def test_score_tc02_uses_shared_cli_settings_for_llm_scoring(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("benchmark_harness_contract_score", "benchmarks/scripts/harness_contract.py")
    _load_module("benchmark_isolated_build_score", "benchmarks/scripts/isolated_build.py")
    score_tc02 = _load_module(
        "benchmark_score_tc02",
        "benchmarks/scripts/score_tc02.py",
    )

    captured: dict[str, object] = {}

    def fake_build_settings(cli_value: str) -> dict:
        captured["cli_value"] = cli_value
        return {
            "agent": {
                "backend": "codex",
                "command": "codex",
                "model": None,
                "profile": None,
                "reasoning_effort": "medium",
                "sandbox": "workspace-write",
                "permission_mode": None,
                "variant": None,
                "agent_name": None,
                "dangerously_skip_permissions": False,
                "extra_args": ["--full-auto", "--ephemeral"],
            }
        }

    def fake_build_cli_command(settings, prompt, **kwargs):
        captured["settings"] = settings
        captured["prompt"] = prompt
        captured["extra_args"] = kwargs.get("extra_args")
        return SimpleNamespace(
            command=["fake-cli"],
            stdin_data=prompt,
            output_file=None,
            backend=settings["agent"]["backend"],
        )

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["stdin"] = kwargs.get("input")
        return SimpleNamespace(
            stdout='[{"id": 1, "accuracy": 0.9, "completeness": 0.8, "keyword_coverage": 0.7, "reasoning": 0.6}]',
            stderr="",
        )

    monkeypatch.setattr(score_tc02, "build_benchmark_agent_settings", fake_build_settings)
    monkeypatch.setattr(score_tc02, "build_cli_command", fake_build_cli_command)
    monkeypatch.setattr(score_tc02.subprocess, "run", fake_run)
    monkeypatch.setenv("SEDIMENT_CLI", "codex")

    scores = score_tc02.run_llm_scoring(
        [
            {
                "id": 1,
                "question": "什么是哈基米？",
                "difficulty": "easy",
                "standard_answer": "哈基米是基础能量单元。",
                "expected_keywords": ["哈基米"],
                "answer": "哈基米是基础能量单元。",
            }
        ],
        workdir=tmp_path,
    )

    assert captured["cli_value"] == "codex"
    assert captured["settings"]["agent"]["backend"] == "codex"
    assert captured["extra_args"][-1] == "--no-session-persistence"
    assert scores[1]["accuracy"] == 0.9


def test_offline_benchmark_mode_writes_white_box_kb(tmp_path: Path, monkeypatch) -> None:
    _load_module("benchmark_harness_contract_offline", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_offline",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    material_path = tmp_path / "role_permissions.yaml"
    material_path.write_text(
        """
        roles:
          outsider:
            display_name: "外乡人"
            description: "新员工称呼，仅拥有只读观察权限"
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [material_path]))

    assert ok is True
    entry = isolated_dir / "knowledge-base" / "entries" / "外乡人.md"
    assert entry.exists()
    assert "只读观察权限" in entry.read_text(encoding="utf-8")


def test_builder_falls_back_to_inprocess_transport_when_loopback_is_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("benchmark_harness_contract_transport", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_transport",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    kb_dir = isolated_dir / "knowledge-base"
    (kb_dir / "entries").mkdir(parents=True)

    monkeypatch.delenv("SEDIMENT_BENCHMARK_TRANSPORT", raising=False)
    monkeypatch.setattr(isolated_build, "loopback_bind_supported", lambda host, port: False)

    builder = isolated_build.IsolatedBuilder(build_type="full", port=18800)
    builder.isolated_dir = isolated_dir
    builder.kb_dir = kb_dir

    server = builder.start_query_server(port=18800)

    assert isinstance(server, isolated_build.InProcessMCPServer)
    assert server.transport_name == "inprocess"


def test_inprocess_transport_calls_white_box_answer_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("benchmark_harness_contract_inprocess", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_inprocess",
        "benchmarks/scripts/isolated_build.py",
    )

    project_root = tmp_path / "project"
    kb_dir = project_root / "knowledge-base"
    (kb_dir / "entries").mkdir(parents=True)
    (kb_dir / "entries" / "清道夫.md").write_text(
        """---
type: concept
status: fact
aliases: []
sources:
  - ops.md
---
# 清道夫

清道夫是清理散斑的自动化维护流程。
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("SEDIMENT_EXPLORE_FAST_ONLY", "0")
    monkeypatch.delenv("SEDIMENT_RUNTIME_ALLOW_MATERIAL_FALLBACK", raising=False)

    server = isolated_build.InProcessMCPServer(kb_dir, project_root)
    assert asyncio.run(server.start()) is True
    try:
        payload = asyncio.run(
            server.call_tool("knowledge_ask", {"question": "什么是清道夫？"})
        )
    finally:
        asyncio.run(server.stop())

    result = json.loads(payload)
    assert "清道夫" in result["answer"]
    assert result["sources"] == ["清道夫"]


def test_offline_builder_promotes_bare_terms_and_cleans_contrastive_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("benchmark_harness_contract_canonical", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_canonical",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    material_path = tmp_path / "ops.md"
    material_path.write_text(
        """
        引雷针：用于引导潮涌能量，不是泄洪。
        借东风专项：在丰水窗口全量谐振腔投入运行。
        掌握定音鼓标准操作流程。
        点睛阶段注入的初始参数已归档至千机匣系统。
        谐振腔扩容与借东风行动是丰水窗口的扩容专项。
        定音鼓频率设定与校准是叠韵阶段的标准校准流程。
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [material_path]))

    assert ok is True
    kb_entries = isolated_dir / "knowledge-base" / "entries"
    assert (kb_entries / "借东风.md").exists()
    assert (kb_entries / "定音鼓.md").exists()
    assert (kb_entries / "点睛.md").exists()
    lines = (kb_entries / "引雷针.md").read_text(encoding="utf-8").splitlines()
    assert any("引导潮涌能量" in line for line in lines[:12])
    assert all("不是泄洪" not in line for line in lines[:12])


def test_offline_builder_promotes_structured_config_entries_and_queryable_aliases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("benchmark_harness_contract_structured", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_structured",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    scheduler = tmp_path / "千机匣任务调度配置.xml"
    scheduler.write_text(
        """
        <config>
          <section name="日常任务">
            <task id="TASK-MORNING" name="晨祷" type="系统检查" schedule="0 0 6 * * *">
              <description>每日一次的系统启动检查流程</description>
              <step order="1" action="唤醒所有谐振腔" timeout="300"/>
              <step order="2" action="清浊比检测" timeout="60"/>
            </task>
          </section>
        </config>
        """,
        encoding="utf-8",
    )
    routing = tmp_path / "信使路由表.xml"
    routing.write_text(
        """
        <config>
          <section name="路由规则">
            <route id="RT-001" source="A" destination="B" type="分流">
              <branch id="BR-1"><hop order="1" node="驿站-E01" type="中转"/></branch>
              <branch id="BR-2"><hop order="1" node="驿站-E02" type="中转"/></branch>
              <param name="分流比例" value="60:40" unit="BR-1:BR-2"/>
            </route>
          </section>
        </config>
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [scheduler, routing]))

    assert ok is True
    kb_entries = isolated_dir / "knowledge-base" / "entries"
    scheduler_entry = (kb_entries / "千机匣任务调度配置.md").read_text(encoding="utf-8")
    assert "晨祷每日06:00" in scheduler_entry
    morning_entry = (kb_entries / "晨祷.md").read_text(encoding="utf-8")
    assert "执行周期为每日06:00" in morning_entry
    routing_entry = (kb_entries / "信使路由策略.md").read_text(encoding="utf-8")
    assert "信使路由表" in routing_entry
    split_entry = (kb_entries / "分流.md").read_text(encoding="utf-8")
    assert "并行支路" in split_entry


def test_offline_builder_avoids_wrapper_titles_when_structured_subject_is_known(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("benchmark_harness_contract_structured_subjects", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_structured_subjects",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    routing = tmp_path / "信使路由表.xml"
    routing.write_text(
        """
        <config>
          <section name="路由规则">
            <route id="RT-001" source="A" destination="B" type="分流">
              <param name="分流比例" value="60:40"/>
            </route>
            <route id="RT-002" source="B" destination="C" type="合流"/>
          </section>
        </config>
        """,
        encoding="utf-8",
    )
    protocol = tmp_path / "旋涡协议报文定义.xml"
    protocol.write_text(
        """
        <config>
          <section name="消息类型">
            <enum value="STD" label="标准传输"/>
            <enum value="JUMP" label="跃迁请求"/>
            <enum value="LATTICE" label="晶格化指令"/>
          </section>
        </config>
        """,
        encoding="utf-8",
    )
    monitor = tmp_path / "回音壁监测点配置.xml"
    monitor.write_text(
        """
        <config>
          <section name="监测点列表">
            <monitor id="MON-001" location="A区主通道" type="固定式"/>
            <monitor id="MON-002" location="B区谐振腔组" type="嵌入式"/>
          </section>
          <section name="盲区覆盖策略">
            <param name="盲区补偿方式" value="移动式回音壁巡航"/>
            <blindspot id="BS-001" area="地下管线交汇区" coverage="0.65"/>
          </section>
        </config>
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [routing, protocol, monitor]))

    assert ok is True
    kb_entries = isolated_dir / "knowledge-base" / "entries"
    assert (kb_entries / "信使路由策略.md").exists()
    assert (kb_entries / "旋涡协议消息类型.md").exists()
    assert (kb_entries / "回音壁监测点.md").exists()
    assert (kb_entries / "盲区.md").exists()
    assert not (kb_entries / "信使路由表.md").exists()
    assert not (kb_entries / "旋涡协议报文定义.md").exists()
    assert not (kb_entries / "消息类型.md").exists()

    route_entry = (kb_entries / "信使路由策略.md").read_text(encoding="utf-8")
    assert "接力、分流、合流" in route_entry
    protocol_entry = (kb_entries / "旋涡协议消息类型.md").read_text(encoding="utf-8")
    assert "标准传输、跃迁" in protocol_entry
    monitor_entry = (kb_entries / "回音壁监测点.md").read_text(encoding="utf-8")
    assert "固定式、嵌入式" in monitor_entry
    blindspot_entry = (kb_entries / "盲区.md").read_text(encoding="utf-8")
    assert "移动式回音壁巡航" in blindspot_entry


def test_offline_builder_rejects_generic_fragment_titles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("benchmark_harness_contract_fragments", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_fragments",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    material_path = tmp_path / "ops.md"
    material_path.write_text(
        """
        核心术语
        热备份
        在主腔故障时立即接管的备用谐振腔。
        建议
        启明前完成设备检查。
        执行
        由掌灯人发起。
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [material_path]))

    assert ok is True
    kb_entries = isolated_dir / "knowledge-base" / "entries"
    assert (kb_entries / "热备份.md").exists()
    assert not (kb_entries / "建议.md").exists()
    assert not (kb_entries / "执行.md").exists()


def test_offline_builder_promotes_markdown_sections_and_code_taxonomy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("harness_contract", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_sections",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    markdown = tmp_path / "ops.md"
    markdown.write_text(
        """
        ## 破茧恢复

        封窖结束后的恢复操作称为破茧，从静默态恢复到正常态。

        ## 隐身衣对抗

        隐身衣只能绕过回音壁等常规监测，不能完全避免账房审计检测。
        """,
        encoding="utf-8",
    )
    python_code = tmp_path / "resonator.py"
    python_code.write_text(
        '''
        """谐振腔控制模块"""

        class ResonatorError(Exception):
            """谐振腔基础异常"""

        class CollapseError(ResonatorError):
            """坍缩异常"""

        class RedLineError(ResonatorError):
            """红线异常"""

        class CoatingError(ResonatorError):
            """镀层缺陷异常"""

        def measure_transmission_loss():
            """量天尺 - 测量传输损耗"""

        # TODO: 未完成，待实现实际环境接入判官决策接口
        ''',
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [markdown, python_code]))

    assert ok is True
    kb_entries = isolated_dir / "knowledge-base" / "entries"
    assert (kb_entries / "破茧.md").exists()
    assert (kb_entries / "隐身衣.md").exists()
    taxonomy_entry = (kb_entries / "谐振腔故障类型.md").read_text(encoding="utf-8")
    assert "坍缩" in taxonomy_entry
    assert "镀层缺陷" in taxonomy_entry
    todo_entry = (kb_entries / "代码待实现项.md").read_text(encoding="utf-8")
    assert "TODO" in todo_entry
    assert "判官决策接口" in todo_entry
    tool_entry = (kb_entries / "量天尺.md").read_text(encoding="utf-8")
    assert "measure_transmission_loss" in tool_entry


def test_offline_builder_merges_supporting_title_variants_into_canonical_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("harness_contract_merge_titles", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_merge_titles",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    markdown = tmp_path / "debug.md"
    markdown.write_text(
        """
        ## 无字碑

        无字碑是调试期间不记录日志的模式。

        ## 无字碑调试模式

        无字碑调试模式是调优期间启用无字碑模式进行不记录日志的调试。
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [markdown]))

    assert ok is True
    kb_entries = isolated_dir / "knowledge-base" / "entries"
    assert (kb_entries / "无字碑.md").exists()
    assert not (kb_entries / "无字碑调试模式.md").exists()
    entry = (kb_entries / "无字碑.md").read_text(encoding="utf-8")
    assert "无字碑调试模式" in entry


def test_offline_builder_projects_runbook_sections_into_core_subject(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("harness_contract_runbook_projection", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_runbook_projection",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    runbook = tmp_path / "潮涌应急预案V3.md"
    runbook.write_text(
        """
        # 潮涌应急预案 V3

        ## 1. 定义

        潮涌：指嗡鸣度在短时间内剧烈攀升，通常突增幅值超过 300%。

        ## 2. 首 10 分钟处置流程

        - 守望者在通天塔创建事件，生成唯一事件编号
        - 判官确认热备份是否就绪，预热泄洪通道但不直接开闸
        - 如存在跨区传播迹象，立即执行分水岭隔离
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [runbook]))

    assert ok is True
    entry = (isolated_dir / "knowledge-base" / "entries" / "潮涌.md").read_text(encoding="utf-8")
    assert "突增幅值超过 300%" in entry
    assert "创建事件" in entry
    assert "分水岭隔离" in entry


def test_offline_builder_projects_structured_trigger_and_deployment_facts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("harness_contract_structured_facts", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_structured_facts",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    coating = tmp_path / "镀层材质参数.xml"
    coating.write_text(
        """
        <config>
          <section name="更换管理">
            <param name="换羽触发阈值" value="照骨灯反射率&lt;0.70或状态判定为晦暗" unit="规则">
              <description>出现晦暗或反射率低于阈值时立即触发换羽</description>
            </param>
            <rule id="MOLT-001" priority="2">
              <condition field="镀层状态" operator="==" threshold="晦暗">
                <description>镀层进入晦暗状态时直接执行换羽</description>
              </condition>
              <action type="换羽" target="铁匠团队" />
            </rule>
          </section>
        </config>
        """,
        encoding="utf-8",
    )
    routing = tmp_path / "信使路由表.xml"
    routing.write_text(
        """
        <config>
          <section name="路由策略">
            <param name="驿站部署策略" value="高频路径双中继、跨区边界分布部署、偏远节点种月部署" unit="策略">
              <description>驿站作为中继和缓冲节点分布在高负载链路与偏远区域，用于负载均衡</description>
            </param>
          </section>
        </config>
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [coating, routing]))

    assert ok is True
    kb_entries = isolated_dir / "knowledge-base" / "entries"
    coating_entry = (kb_entries / "换羽.md").read_text(encoding="utf-8")
    assert "出现晦暗或反射率低于阈值时立即触发换羽" in coating_entry
    station_entry = (kb_entries / "驿站.md").read_text(encoding="utf-8")
    assert "高频路径双中继" in station_entry
    assert "负载均衡" in station_entry


def test_offline_builder_keeps_structural_fanout_focused_on_target_clause(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("harness_contract_structural_fanout_focus", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_structural_fanout_focus",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    architecture = tmp_path / "哈基米系统架构设计.md"
    architecture.write_text(
        """
        # 哈基米系统架构设计

        千机匣是系统的自动化控制中枢，也是自动化控制谐振腔集群的管理系统。
        """,
        encoding="utf-8",
    )
    maintenance = tmp_path / "镀层维护守则.md"
    maintenance.write_text(
        """
        # 镀层维护守则

        换羽是定期更换镀层的维护操作。若照骨灯发现晦暗或溢彩消失，应提前触发换羽。
        """,
        encoding="utf-8",
    )
    audit = tmp_path / "渡鸦团队年度工作总结.md"
    audit.write_text(
        """
        # 渡鸦团队年度工作总结

        账房系统每日自动生成差额报告，差额超过0.5%即触发渡鸦调查。
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [architecture, maintenance, audit]))
    assert ok is True
    assert asyncio.run(isolated_build.run_tidy(isolated_dir)) is True

    kb_entries = isolated_dir / "knowledge-base" / "entries"
    recoating_summary = (kb_entries / "换羽.md").read_text(encoding="utf-8").split("## Scope", 1)[0]
    assert "晦暗" in recoating_summary
    assert "千机匣是系统的自动化控制中枢" not in recoating_summary

    raven_summary = (kb_entries / "渡鸦.md").read_text(encoding="utf-8").split("## Scope", 1)[0]
    assert "差额超过0.5%" in raven_summary
    assert "千机匣是系统的自动化控制中枢" not in raven_summary


def test_offline_builder_uses_system_config_for_metric_and_rule_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("harness_contract_system_config", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_system_config",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    config = tmp_path / "system_config.yaml"
    config.write_text(
        """
        monitoring:
          safety_string: "base_noise < hum_level <= resonance_peak.max < red_line"
          hum_level:
            red_line: 720.0
            resonance_peak:
              min: 420.0
              max: 580.0
            base_noise: 100.0
            sample_rate: 100
        resonator:
          purity_ratio:
            target: 19.0
            warning: 9.0
            emergency: 5.6
        security:
          three_strike_rule:
            enabled: true
            rolling_window_hours: 24
            isolation_duration_hours: 24
            require_manual_review: true
        design_philosophy:
          stability_first:
            description: "稳定性优先：多层安全机制保障稳定"
            mechanisms:
              - "红线阈值: 嗡鸣度不可超过的绝对安全边界"
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [config]))

    assert ok is True
    kb_entries = isolated_dir / "knowledge-base" / "entries"
    hum_level = (kb_entries / "嗡鸣度.md").read_text(encoding="utf-8")
    assert "衡量哈基米活跃状态" in hum_level
    peak = (kb_entries / "共振峰.md").read_text(encoding="utf-8")
    assert "420.0-580.0Hz" in peak
    rule = (kb_entries / "三振法则.md").read_text(encoding="utf-8")
    assert "24 小时滚动窗口" in rule
    philosophy = (kb_entries / "哈基米系统设计哲学.md").read_text(encoding="utf-8")
    assert "稳定性优先" in philosophy


def test_offline_tidy_preserves_strong_canonical_summaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("harness_contract_summary_guard", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_summary_guard",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    glossary = tmp_path / "核心术语.md"
    glossary.write_text(
        """
        核心术语
        调音师
        负责调整谐振腔嗡鸣度并使用定音鼓校准频率的专家角色。
        镀层
        保护哈基米免受外部干扰的防护外壳。
        """,
        encoding="utf-8",
    )
    config = tmp_path / "system_config.yaml"
    config.write_text(
        """
        monitoring:
          hum_level:
            red_line: 720.0
            resonance_peak:
              min: 420.0
              max: 580.0
        """,
        encoding="utf-8",
    )
    singer = tmp_path / "singer.py"
    singer.write_text(
        '''
        """调音师工具模块"""

        def check_safety_string():
            """检查是否在安全弦边界内"""
        ''',
        encoding="utf-8",
    )
    resonator = tmp_path / "resonator.py"
    resonator.write_text(
        '''
        class CoatingError(Exception):
            """镀层异常"""
        ''',
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [glossary, config, singer, resonator]))
    assert ok is True
    assert asyncio.run(isolated_build.run_tidy(isolated_dir)) is True

    kb_entries = isolated_dir / "knowledge-base" / "entries"
    hum_level = (kb_entries / "嗡鸣度.md").read_text(encoding="utf-8")
    assert "衡量哈基米活跃状态" in hum_level
    assert "系统运行中的一种模式或状态" not in hum_level

    tuner = (kb_entries / "调音师.md").read_text(encoding="utf-8")
    assert "专家角色" in tuner
    assert "检查是否在安全弦边界内" not in "\n".join(tuner.splitlines()[:8])

    coating = (kb_entries / "镀层.md").read_text(encoding="utf-8")
    assert "防护外壳" in coating
    assert "镀层异常。" not in "\n".join(coating.splitlines()[:8])


def test_offline_builder_projects_textual_doc_subjects_and_compound_summaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("harness_contract_textual_projection", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_textual_projection",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    lifecycle = tmp_path / "谐振腔生命周期管理.txt"
    lifecycle.write_text(
        """
        一、生命周期阶段
        谐振腔的完整生命周期包括五个阶段：建设验收、开光启用、正常运行、维护更新、退役处置。
        """,
        encoding="utf-8",
    )
    architecture = tmp_path / "哈基米系统架构设计.md"
    architecture.write_text(
        """
        # 哈基米系统架构设计

        千机匣内置了定海针算法，可在嗡鸣度出现毛刺时自动进行微调，确保系统维持在安全弦范围内运行。
        """,
        encoding="utf-8",
    )
    checklist = tmp_path / "启明仪式操作checklist.md"
    checklist.write_text(
        """
        # 启明仪式操作 Checklist

        启明是新谐振腔在开光与试音完成后的首次受控放量仪式，属于“开光 -> 试音 -> 启明 -> 试运行 -> 正式运行”链路中的正式投运步骤。启明仪式必须由掌灯人主持或授权执行。
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [lifecycle, architecture, checklist]))
    assert ok is True
    assert asyncio.run(isolated_build.run_tidy(isolated_dir)) is True

    kb_entries = isolated_dir / "knowledge-base" / "entries"
    lifecycle_entry = (kb_entries / "谐振腔生命周期.md").read_text(encoding="utf-8")
    assert "建设验收、开光启用、正常运行、维护更新、退役处置" in lifecycle_entry

    anchor = (kb_entries / "定海针.md").read_text(encoding="utf-8")
    assert "自动进行微调" in anchor

    initiation = (kb_entries / "启明.md").read_text(encoding="utf-8")
    assert "首次受控放量仪式" in initiation


def test_offline_builder_merges_supporting_title_variants_into_canonical_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("harness_contract_title_merge", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_title_merge",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    checklist = tmp_path / "启明仪式操作checklist.md"
    checklist.write_text(
        """
        # 启明仪式操作 Checklist

        启明是新谐振腔在开光与试音完成后的首次受控放量仪式，必须由掌灯人主持。
        """,
        encoding="utf-8",
    )
    execution = tmp_path / "启明执行.md"
    execution.write_text(
        """
        启明执行：必须复核注入速率，并确认千机匣自动化控制系统处于待命状态。
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(isolated_build.run_ingest(isolated_dir, [checklist, execution]))
    assert ok is True
    assert asyncio.run(isolated_build.run_tidy(isolated_dir)) is True

    kb_entries = isolated_dir / "knowledge-base" / "entries"
    initiation = (kb_entries / "启明.md").read_text(encoding="utf-8")
    assert "复核注入速率" in initiation
    assert not (kb_entries / "启明执行.md").exists()


def test_offline_builder_prioritizes_high_signal_scope_lines_for_core_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _load_module("harness_contract_signal_scope", "benchmarks/scripts/harness_contract.py")
    isolated_build = _load_module(
        "benchmark_isolated_build_signal_scope",
        "benchmarks/scripts/isolated_build.py",
    )

    isolated_dir = tmp_path / "isolated"
    architecture = tmp_path / "哈基米系统架构设计.md"
    architecture.write_text(
        """
        # 哈基米系统架构设计

        哈基米既是系统的核心资源，也是整套系统一切运作的物质基础。
        千机匣是系统的自动化控制中枢，也是自动化控制谐振腔集群的管理系统。
        传输路径的规划由驿站承担，驿站作为临时中转的缓冲节点和中继节点，在长距离传输中起到分段缓存与负载均衡的作用。
        """,
        encoding="utf-8",
    )
    maintenance = tmp_path / "镀层维护守则.md"
    maintenance.write_text(
        """
        # 镀层维护守则

        换羽是定期更换镀层的维护操作。若照骨灯发现晦暗或溢彩消失，应提前触发换羽。
        """,
        encoding="utf-8",
    )
    observability = tmp_path / "听风者周报模板.md"
    observability.write_text(
        """
        # 听风者周报模板

        嗡鸣度数据质量应同时检查底噪稳定性、毛刺频率、峰谷差和留声机历史记录完整性，排除幽灵读数干扰。
        """,
        encoding="utf-8",
    )
    (isolated_dir / "knowledge-base" / "entries").mkdir(parents=True)

    monkeypatch.setenv("SEDIMENT_BENCHMARK_BUILD_MODE", "offline")

    ok = asyncio.run(
        isolated_build.run_ingest(
            isolated_dir,
            [architecture, maintenance, observability],
        )
    )
    assert ok is True
    assert asyncio.run(isolated_build.run_tidy(isolated_dir)) is True

    kb_entries = isolated_dir / "knowledge-base" / "entries"
    hakimi = (kb_entries / "哈基米.md").read_text(encoding="utf-8")
    assert "核心资源" in hakimi
    scheduler = (kb_entries / "千机匣.md").read_text(encoding="utf-8")
    assert "谐振腔集群的管理系统" in scheduler
    station = (kb_entries / "驿站.md").read_text(encoding="utf-8")
    assert "负载均衡" in station
    assert "中继" in station
    recoating = (kb_entries / "换羽.md").read_text(encoding="utf-8")
    assert "晦暗" in recoating
    telemetry = (kb_entries / "嗡鸣度.md").read_text(encoding="utf-8")
    assert "留声机" in telemetry
