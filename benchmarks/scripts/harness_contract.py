from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BenchmarkPaths:
    project_root: Path
    benchmarks_dir: Path
    testcase_dir: Path
    judge_dir: Path
    results_dir: Path
    builds_dir: Path
    reports_dir: Path
    improvements_dir: Path
    history_dir: Path
    examples_dir: Path
    sample_workspace_dir: Path
    skills_dir: Path
    test_plan_path: Path


def load_benchmark_paths() -> BenchmarkPaths:
    scripts_dir = Path(__file__).resolve().parent
    project_root = scripts_dir.parent.parent
    benchmarks_dir = project_root / "benchmarks"
    testcase_dir = project_root / "testcase"
    results_dir = testcase_dir / "results"
    examples_dir = project_root / "examples"
    return BenchmarkPaths(
        project_root=project_root,
        benchmarks_dir=benchmarks_dir,
        testcase_dir=testcase_dir,
        judge_dir=benchmarks_dir / "judge",
        results_dir=results_dir,
        builds_dir=results_dir / "builds",
        reports_dir=results_dir / "reports",
        improvements_dir=results_dir / "improvements",
        history_dir=results_dir / "history",
        examples_dir=examples_dir,
        sample_workspace_dir=examples_dir,
        skills_dir=project_root / "src" / "sediment" / "skills",
        test_plan_path=benchmarks_dir / "TEST_PLAN.md",
    )


def ensure_results_layout(paths: BenchmarkPaths) -> None:
    for directory in (
        paths.results_dir,
        paths.builds_dir,
        paths.reports_dir,
        paths.improvements_dir,
        paths.history_dir,
        paths.examples_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def artifact_layout_payload(paths: BenchmarkPaths) -> dict[str, str]:
    return {
        "test_plan_path": str(paths.test_plan_path),
        "skills_dir": str(paths.skills_dir),
        "results_dir": str(paths.results_dir),
        "builds_dir": str(paths.builds_dir),
        "reports_dir": str(paths.reports_dir),
        "improvements_dir": str(paths.improvements_dir),
        "history_dir": str(paths.history_dir),
        "sample_workspace_dir": str(paths.sample_workspace_dir),
    }


def copy_sample_kb(
    *,
    build_type: str,
    kb_dir: Path,
    source_isolated_dir: str | Path | None,
    destination_root: Path,
    diagnostics: dict | None = None,
) -> Path:
    _ = source_isolated_dir, diagnostics
    destination = destination_root if build_type == "full" else destination_root / f"{build_type}-workspace"
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(kb_dir, destination)
    return destination
