from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_module(name: str, relative_path: str):
    module_path = Path(__file__).resolve().parent.parent / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_harness_contract_points_to_testcase_results_and_repo_skills() -> None:
    contract = _load_module("benchmark_harness_contract", "benchmarks/scripts/harness_contract.py")

    paths = contract.load_benchmark_paths()

    assert paths.test_plan_path.name == "TEST_PLAN.md"
    assert paths.results_dir == paths.project_root / "testcase" / "results"
    assert paths.sample_kb_builds_dir == paths.project_root / "testcase" / "samples" / "kb_builds"
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


def test_copy_sample_kb_writes_manifest(tmp_path: Path) -> None:
    contract = _load_module(
        "benchmark_harness_contract_copy",
        "benchmarks/scripts/harness_contract.py",
    )

    kb_dir = tmp_path / "isolated" / "knowledge-base"
    (kb_dir / "entries").mkdir(parents=True)
    (kb_dir / "entries" / "热备份.md").write_text("# 热备份\n", encoding="utf-8")
    destination_root = tmp_path / "samples" / "kb_builds"

    copied = contract.copy_sample_kb(
        build_type="full",
        kb_dir=kb_dir,
        source_isolated_dir=tmp_path / "isolated",
        destination_root=destination_root,
        diagnostics={"entry_count": 1, "placeholder_count": 0, "avg_entry_size": 6.0},
    )

    assert (copied / "entries" / "热备份.md").exists()
    manifest = json.loads((copied / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["build_type"] == "full"
    assert manifest["entry_count"] == 1
    assert manifest["source_kb_dir"] == str(kb_dir)


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
