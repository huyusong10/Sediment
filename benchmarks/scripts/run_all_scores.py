"""
run_all_scores.py — Sediment 全流程测试运行器

执行完整的测试流程：
1. 通过 isolated_build.py 隔离项目并构建 KB
2. 对每个构建启动 MCP server，执行 TC-01 和 TC-02
3. 计算平均分，输出 scorecard

用法：
    # 完整流程（全量 + 分批 + 评分）
    python benchmarks/scripts/run_all_scores.py

    # 仅全量构建
    python benchmarks/scripts/run_all_scores.py --build-type full

    # 仅分批构建
    python benchmarks/scripts/run_all_scores.py --build-type batched

    # 仅评分（已有构建结果时）
    python benchmarks/scripts/run_all_scores.py --skip-build
"""

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

# Add scripts dir to path for isolated_build imports
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from isolated_build import (
    IsolatedBuilder,
    MCPServer,
    collect_kb_diagnostics,
    log,
    get_material_files,
    chunk_list,
)
from harness_contract import ensure_results_layout, load_benchmark_paths

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PATHS = load_benchmark_paths()
PROJECT_ROOT = PATHS.project_root
TESTCASE_DIR = PATHS.testcase_dir
JUDGE_DIR = PATHS.judge_dir
RESULTS_DIR = PATHS.results_dir
BUILDS_DIR = PATHS.builds_dir
REPORTS_DIR = PATHS.reports_dir
IMPROVEMENTS_DIR = PATHS.improvements_dir
HISTORY_DIR = PATHS.history_dir

MCP_PORT_BASE = 18800
PASS_THRESHOLD = 90
QUESTION_CONCURRENCY = max(1, int(os.environ.get("SEDIMENT_BENCHMARK_QUESTION_CONCURRENCY", "8")))


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def archive_previous_results() -> Path | None:
    """Snapshot the previous run into history before overwriting current artifacts."""
    has_build_data = BUILDS_DIR.exists() and any(BUILDS_DIR.rglob('*.json'))
    has_report_data = REPORTS_DIR.exists() and any(REPORTS_DIR.iterdir())
    if not has_build_data and not has_report_data:
        return None

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    entry = HISTORY_DIR / datetime.now().strftime('%Y%m%d_%H%M%S')
    entry.mkdir(parents=True, exist_ok=True)

    if BUILDS_DIR.exists():
        shutil.copytree(BUILDS_DIR, entry / 'builds', dirs_exist_ok=True)
    if REPORTS_DIR.exists():
        shutil.copytree(REPORTS_DIR, entry / 'reports', dirs_exist_ok=True)

    return entry


def update_live_status(build_type: str | None, phase: str, status: str = 'running', **extra) -> None:
    """Persist a lightweight progress snapshot for long-running benchmark runs."""
    current = {}
    live_status_path = REPORTS_DIR / 'live_status.json'
    if live_status_path.exists():
        try:
            current = json.loads(live_status_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            current = {}

    builds = current.get('builds', {})
    if build_type:
        build_status = builds.get(build_type, {})
        build_status.update({
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'phase': phase,
            'status': status,
        })
        build_status.update(extra)
        builds[build_type] = build_status

        build_dir = BUILDS_DIR / build_type
        write_json(build_dir / 'status.json', build_status)

    current.update({
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status': status,
        'current_build': build_type,
        'current_phase': phase,
        'builds': builds,
    })
    write_json(live_status_path, current)


def reset_live_status(mode: str) -> None:
    write_json(
        REPORTS_DIR / 'live_status.json',
        {
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'running',
            'current_build': None,
            'current_phase': 'starting',
            'mode': mode,
            'builds': {},
        },
    )


def cleanup_isolated_dirs(results: dict[str, dict]) -> list[str]:
    """Remove preserved isolated directories once a run is healthy enough."""
    cleaned = []
    for result in results.values():
        isolated_dir = result.get('isolated_dir')
        if not isolated_dir:
            continue
        path = Path(isolated_dir)
        if not path.exists():
            continue
        shutil.rmtree(path, ignore_errors=True)
        cleaned.append(str(path))
    return cleaned


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def run_preflight_checks() -> dict:
    """Validate that the test harness is using project-owned sources and clean output layout."""
    skill_files = {
        'ingest': PATHS.skills_dir / 'ingest' / 'SKILL.md',
        'tidy': PATHS.skills_dir / 'tidy' / 'SKILL.md',
        'explore': PATHS.skills_dir / 'explore' / 'SKILL.md',
        'health': PATHS.skills_dir / 'health' / 'SKILL.md',
    }
    missing = [name for name, path in skill_files.items() if not path.exists()]
    if missing:
        raise RuntimeError(f'Missing required skill files: {", ".join(missing)}')

    isolated_build_source = (SCRIPTS_DIR / 'isolated_build.py').read_text(encoding='utf-8')
    if 'PROMPTS_DIR' in isolated_build_source or "testcase' / 'prompts" in isolated_build_source:
        raise RuntimeError('isolated_build.py still references benchmarks/prompts; benchmark must use skills/*.md')

    prompt_dir = PATHS.benchmarks_dir / 'prompts'
    forbidden_results_items = sorted(
        p.name for p in RESULTS_DIR.iterdir()
        if p.exists()
        and p.name not in {'README.md', 'builds', 'reports', 'improvements', 'history'}
    ) if RESULTS_DIR.exists() else []
    forbidden_kb_dirs = sorted(
        p.name for p in RESULTS_DIR.iterdir()
        if p.is_dir() and (p.name.startswith('kb_') or p.name.startswith('knowledge-base'))
    ) if RESULTS_DIR.exists() else []
    if forbidden_kb_dirs:
        raise RuntimeError(
            f'benchmarks/results contains KB snapshot directories: {", ".join(forbidden_kb_dirs)}'
        )

    return {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'skill_sources': {name: str(path) for name, path in skill_files.items()},
        'benchmark_role': 'internal_evaluation_only',
        'uses_temp_kb_only': True,
        'pass_threshold': PASS_THRESHOLD,
        'shared_llm_cli': os.environ.get('SEDIMENT_CLI', 'claude'),
        'benchmark_build_mode': os.environ.get('SEDIMENT_BENCHMARK_BUILD_MODE', '').strip() or 'default',
        'benchmark_transport_mode': os.environ.get('SEDIMENT_BENCHMARK_TRANSPORT', '').strip() or 'auto',
        'results_layout': {
            'builds_dir': str(BUILDS_DIR),
            'reports_dir': str(REPORTS_DIR),
            'improvements_dir': str(IMPROVEMENTS_DIR),
            'history_dir': str(HISTORY_DIR),
            'test_plan_path': str(PATHS.test_plan_path),
        },
        'stray_prompt_dir_exists': prompt_dir.exists(),
        'forbidden_results_items': forbidden_results_items,
        'root_artifacts_present': [
            name for name in ('scores.json', 'scoring_result.json')
            if (PROJECT_ROOT / name).exists()
        ],
    }


# ---------------------------------------------------------------------------
# Test Execution
# ---------------------------------------------------------------------------

async def _ask_window(
    server: MCPServer,
    *,
    items: list[dict],
    start_index: int,
    total: int,
) -> list[tuple[dict, str, float]]:
    starts: list[float] = []
    tasks = []
    for offset, item in enumerate(items):
        idx = start_index + offset
        log(f"  [{idx+1}/{total}] {item['question'][:60]}...")
        starts.append(time.time())
        tasks.append(
            asyncio.create_task(
                server.call_tool('knowledge_ask', {'question': item['question']})
            )
        )
    responses = await asyncio.gather(*tasks)
    results: list[tuple[dict, str, float]] = []
    for offset, (item, answer_text) in enumerate(zip(items, responses)):
        elapsed = time.time() - starts[offset]
        log(f"    -> {len(answer_text)} chars in {elapsed:.1f}s")
        results.append((item, answer_text, elapsed))
    return results


async def run_concept_test(
    server: MCPServer,
    judge_file: Path,
    *,
    progress_callback: Callable[[dict], None] | None = None,
) -> list[dict]:
    """Run TC-01: concept coverage test."""
    with open(judge_file, 'r', encoding='utf-8') as f:
        judge_data = json.load(f)

    concept_items = [
        {
            'concept': concept,
            'question': f"什么是{concept}？",
            'definition': defn.get('definition', ''),
        }
        for concept, defn in judge_data['terms'].items()
    ]
    results = []
    total = len(concept_items)
    empty_count = 0

    for start in range(0, total, QUESTION_CONCURRENCY):
        window = concept_items[start:start + QUESTION_CONCURRENCY]
        window_results = await _ask_window(
            server,
            items=window,
            start_index=start,
            total=total,
        )
        for offset, (item, answer_text, _elapsed) in enumerate(window_results):
            try:
                result = json.loads(answer_text)
                answer = result.get('answer', '')
                sources = result.get('sources', [])
            except (json.JSONDecodeError, TypeError):
                answer = answer_text
                sources = []

            absolute_index = start + offset
            if not answer:
                empty_count += 1
                if empty_count >= 3 and absolute_index < 10:
                    log(
                        f"  ERROR: First {empty_count} answers are empty — KB likely empty or server misconfigured"
                    )
                    raise RuntimeError(
                        f"Empty answers detected early in concept test ({empty_count}/{absolute_index+1} empty)"
                    )

            results.append({
                'concept': item['concept'],
                'question': item['question'],
                'answer': answer,
                'sources': sources,
                'definition': item['definition'],
            })
        if progress_callback:
            progress_callback(
                {
                    'phase': 'tc01',
                    'answered': len(results),
                    'total_questions': total,
                    'empty_answers': empty_count,
                }
            )

    log(f"Concept test complete: {len(results)}/{total}")
    return results


async def run_qa_test(
    server: MCPServer,
    judge_file: Path,
    *,
    progress_callback: Callable[[dict], None] | None = None,
) -> list[dict]:
    """Run TC-02: QA accuracy test."""
    with open(judge_file, 'r', encoding='utf-8') as f:
        judge_data = json.load(f)

    results = []
    questions = judge_data.get('questions', [])
    total = len(questions)
    empty_count = 0

    for start in range(0, total, QUESTION_CONCURRENCY):
        window = questions[start:start + QUESTION_CONCURRENCY]
        window_results = await _ask_window(
            server,
            items=window,
            start_index=start,
            total=total,
        )
        for offset, (q, answer_text, _elapsed) in enumerate(window_results):
            try:
                result = json.loads(answer_text)
                answer = result.get('answer', '')
                sources = result.get('sources', [])
            except (json.JSONDecodeError, TypeError):
                answer = answer_text
                sources = []

            absolute_index = start + offset
            if not answer:
                empty_count += 1
                if empty_count >= 3 and absolute_index < 10:
                    log(
                        f"  ERROR: First {empty_count} answers are empty — KB likely empty or server misconfigured"
                    )
                    raise RuntimeError(
                        f"Empty answers detected early in QA test ({empty_count}/{absolute_index+1} empty)"
                    )

            results.append({
                'id': q['id'],
                'question': q['question'],
                'difficulty': q.get('difficulty', 'medium'),
                'answer': answer,
                'sources': sources,
                'standard_answer': q.get('standard_answer', ''),
                'expected_keywords': q.get('expected_keywords', []),
            })
        if progress_callback:
            progress_callback(
                {
                    'phase': 'tc02',
                    'answered': len(results),
                    'total_questions': total,
                    'empty_answers': empty_count,
                }
            )

    log(f"QA test complete: {len(results)}/{total}")
    return results


# ---------------------------------------------------------------------------
# Build & Test Pipeline
# ---------------------------------------------------------------------------

async def build_and_test(build_type: str, output_dir: Path, port: int, preserve_isolated: bool = True) -> dict:
    """
    Full pipeline for one build type:
    1. Create isolated copy and build KB (via IsolatedBuilder)
    2. Start MCP server
    3. Run tests
    4. Score
    """
    log(f"\n{'='*60}")
    log(f"Starting {build_type} build on port {port}")
    log(f"{'='*60}")

    builder: IsolatedBuilder | None = None
    results = {
        'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'build_type': build_type,
        'artifacts_dir': str(output_dir),
        'preserve_isolated': preserve_isolated,
    }
    build_start = time.time()

    def on_build_progress(progress: dict) -> None:
        isolated_dir = str(builder.isolated_dir) if builder and builder.isolated_dir else None
        update_live_status(
            build_type,
            'build_kb',
            isolated_dir=isolated_dir,
            build_event=progress.get('event'),
            current_subphase=progress.get('subphase'),
            stage_label=progress.get('stage_label'),
            current_chunk=progress.get('current_chunk'),
            total_chunks=progress.get('total_chunks'),
            batch_file_count=progress.get('batch_file_count'),
            batch_size_kb=progress.get('batch_size_kb'),
            focus=progress.get('focus'),
            attempt=progress.get('attempt'),
            max_retries=progress.get('max_retries'),
            material_count=progress.get('material_count'),
            heartbeat_at=progress.get('heartbeat_at'),
            elapsed_seconds=progress.get('elapsed_seconds'),
            entry_count=progress.get('entry_count'),
            placeholder_count=progress.get('placeholder_count'),
            build_success=progress.get('success'),
            build_error=progress.get('error'),
            build_returncode=progress.get('returncode'),
        )

    def on_question_progress(progress: dict) -> None:
        phase = progress.get('phase') or 'questions'
        update_live_status(
            build_type,
            phase,
            answered=progress.get('answered'),
            total_questions=progress.get('total_questions'),
            empty_answers=progress.get('empty_answers'),
        )

    def on_score_progress(progress: dict) -> None:
        phase = progress.get('phase') or 'scoring'
        update_live_status(
            build_type,
            phase,
            scoring_event=progress.get('event'),
            batch_num=progress.get('batch_num'),
            total_batches=progress.get('total_batches'),
            completed_batches=progress.get('completed_batches'),
            batch_method=progress.get('batch_method'),
            heartbeat_at=progress.get('heartbeat_at'),
            elapsed_seconds=progress.get('elapsed_seconds'),
            scored_questions=progress.get('scored_questions'),
            total_questions=progress.get('total_questions'),
            answered=progress.get('answered'),
            zero_score=progress.get('zero_score'),
            final_score=progress.get('final_score'),
            llm_scored=progress.get('llm_scored'),
            script_fallback=progress.get('script_fallback'),
            scoring_error=progress.get('error'),
        )

    try:
        builder = IsolatedBuilder(
            build_type=build_type,
            port=port,
            progress_callback=on_build_progress,
        )
        # Step 1: Create isolated copy
        log(f"\n[STEP 1/5] Creating isolated project copy...")
        update_live_status(build_type, 'create_isolated_copy')
        step_start = time.time()
        await builder.create_isolated_copy()
        results['isolated_dir'] = str(builder.isolated_dir)
        log(f"  Isolated copy ready in {time.time() - step_start:.1f}s")

        # Step 2: Build KB
        log(f"\n[STEP 2/5] Building knowledge base ({build_type})...")
        update_live_status(build_type, 'build_kb', isolated_dir=str(builder.isolated_dir))
        step_start = time.time()
        await builder.build()
        log(f"  Build phase complete in {time.time() - step_start:.1f}s")

        # Inspect KB stats without copying KB into benchmarks/results
        log(f"\n[STEP 2b] Inspecting KB stats...")
        update_live_status(build_type, 'inspect_kb')
        entry_count = 0
        placeholder_count = 0
        if builder.kb_dir and builder.kb_dir.exists():
            diagnostics = collect_kb_diagnostics(builder.kb_dir)
            entry_count = diagnostics.get('entry_count', 0)
            placeholder_count = diagnostics.get('placeholder_count', 0)
            results['kb_stats'] = {
                'entry_count': entry_count,
                'placeholder_count': placeholder_count,
                'avg_entry_size': diagnostics.get('avg_entry_size', 0.0),
                'isolated_kb_dir': str(builder.kb_dir),
            }
            results['kb_diagnostics_file'] = str(output_dir / f'kb_diagnostics_{build_type}.json')
            write_json(output_dir / f'kb_diagnostics_{build_type}.json', diagnostics)
            log(
                "  KB stats: "
                f"{entry_count} entries, {placeholder_count} placeholders, "
                f"avg entry size {diagnostics.get('avg_entry_size', 0.0)}"
            )
            log(
                "  KB health: "
                f"{diagnostics.get('orphan_entry_count', 0)} orphans, "
                f"{diagnostics.get('dangling_link_count', 0)} dangling links, "
                f"{diagnostics.get('placeholder_ref_summary', {}).get('high', 0)} high-ref placeholders"
            )
            update_live_status(
                build_type,
                'inspect_kb',
                entry_count=entry_count,
                placeholder_count=placeholder_count,
                orphan_entry_count=diagnostics.get('orphan_entry_count', 0),
                dangling_link_count=diagnostics.get('dangling_link_count', 0),
            )

        # Validate KB has entries before proceeding
        if entry_count == 0:
            log("  ERROR: Knowledge base is empty after build. Aborting.")
            results['error'] = 'KB empty after build — ingest may have failed or timed out'
            update_live_status(build_type, 'failed', status='failed', error=results['error'])
            return results

        # Step 3: Start benchmark query transport
        transport_mode = builder.query_transport_mode(port=port)
        log(f"\n[STEP 3/5] Starting benchmark query transport ({transport_mode})...")
        update_live_status(build_type, 'start_query_transport', port=port, query_transport=transport_mode)
        step_start = time.time()
        server = builder.start_query_server(port=port)
        results['query_transport'] = server.transport_name
        started = await server.start()
        if not started:
            log("  FAILED to start benchmark query transport")
            results['error'] = 'Benchmark query transport failed to start'
            update_live_status(build_type, 'failed', status='failed', error=results['error'])
            return results
        log(f"  Query transport ready in {time.time() - step_start:.1f}s")

        try:
            # Step 4: Run concept test
            log(f"\n[STEP 4/5] Running TC-01: Concept Coverage (100 questions)...")
            update_live_status(build_type, 'tc01')
            step_start = time.time()
            concept_results = await run_concept_test(
                server,
                JUDGE_DIR / '概念.json',
                progress_callback=on_question_progress,
            )
            log(f"  TC-01 complete in {time.time() - step_start:.1f}s")

            # Save concept answers
            concept_answers_file = output_dir / f'concept_answers_{build_type}.json'
            with open(concept_answers_file, 'w', encoding='utf-8') as f:
                json.dump({'results': concept_results}, f, ensure_ascii=False, indent=2)
            log(f"  Concept answers saved to {concept_answers_file.name}")

            # Score TC-01
            log(f"\n  Scoring TC-01...")
            from score_tc01 import run_scoring as score_tc01
            update_live_status(build_type, 'score_tc01')
            tc01_result = score_tc01(
                concept_answers_file,
                JUDGE_DIR / '概念.json',
                output_dir,
                build_type,
                progress_callback=on_score_progress,
            )
            results['tc01'] = tc01_result
            log(f"  TC-01 score: {tc01_result['final_score']:.1f}/40")

            # Run QA test
            log(f"\n[STEP 5/5] Running TC-02: QA Accuracy (100 questions)...")
            update_live_status(build_type, 'tc02', tc01_score=tc01_result['final_score'])
            step_start = time.time()
            qa_results = await run_qa_test(
                server,
                JUDGE_DIR / '问答.json',
                progress_callback=on_question_progress,
            )
            log(f"  TC-02 complete in {time.time() - step_start:.1f}s")

            # Save QA answers
            qa_answers_file = output_dir / f'qa_answers_{build_type}.json'
            with open(qa_answers_file, 'w', encoding='utf-8') as f:
                json.dump({'results': qa_results}, f, ensure_ascii=False, indent=2)
            log(f"  QA answers saved to {qa_answers_file.name}")

            # Score TC-02
            log(f"\n  Scoring TC-02...")
            from score_tc02 import run_scoring as score_tc02
            update_live_status(build_type, 'score_tc02', tc01_score=tc01_result['final_score'])
            tc02_result = score_tc02(
                qa_answers_file,
                JUDGE_DIR / '问答.json',
                output_dir,
                build_type,
                progress_callback=on_score_progress,
            )
            results['tc02'] = tc02_result
            log(f"  TC-02 score: {tc02_result['final_score']:.1f}/60")

            # Combined score
            total_score = tc01_result['final_score'] + tc02_result['final_score']
            results['total_score'] = total_score
            results['max_score'] = 100
            results['finished_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            results['duration_seconds'] = round(time.time() - build_start, 1)
            update_live_status(
                build_type,
                'completed',
                status='completed',
                total_score=round(total_score, 2),
                tc01_score=tc01_result['final_score'],
                tc02_score=tc02_result['final_score'],
                duration_seconds=results['duration_seconds'],
            )
            log(f"\n{'='*60}")
            log(f"{build_type} build total score: {total_score:.1f}/100")
            log(f"  TC-01: {tc01_result['final_score']:.1f}/40")
            log(f"  TC-02: {tc02_result['final_score']:.1f}/60")
            log(f"  Total time: {results['duration_seconds']:.0f}s")
            log(f"{'='*60}")

        finally:
            await server.stop()

    except Exception as e:
        log(f"Build {build_type} failed with exception: {e}")
        import traceback
        log(traceback.format_exc())
        results['error'] = str(e)
        update_live_status(build_type, 'failed', status='failed', error=str(e))

    finally:
        await builder.cleanup(remove_dir=not preserve_isolated)
        if preserve_isolated and results.get('isolated_dir'):
            results['cleanup_policy'] = f'preserved until run average reaches {PASS_THRESHOLD}'
        update_live_status(
            build_type,
            'teardown',
            status='preserved' if preserve_isolated else 'cleaned',
            isolated_dir=results.get('isolated_dir'),
        )

    return results


# ---------------------------------------------------------------------------
# Scoring Only (skip build)
# ---------------------------------------------------------------------------

def score_existing(build_type: str, output_dir: Path) -> dict:
    """Score existing build results without re-building."""
    concept_answers_file = output_dir / f'concept_answers_{build_type}.json'
    qa_answers_file = output_dir / f'qa_answers_{build_type}.json'

    if not concept_answers_file.exists():
        log(f"No concept answers found for {build_type} build")
        return {'error': f'Missing concept_answers_{build_type}.json'}

    if not qa_answers_file.exists():
        log(f"No QA answers found for {build_type} build")
        return {'error': f'Missing qa_answers_{build_type}.json'}

    from score_tc01 import run_scoring as score_tc01
    from score_tc02 import run_scoring as score_tc02

    def on_score_progress(progress: dict) -> None:
        phase = progress.get('phase') or 'scoring'
        update_live_status(
            build_type,
            phase,
            scoring_event=progress.get('event'),
            batch_num=progress.get('batch_num'),
            total_batches=progress.get('total_batches'),
            completed_batches=progress.get('completed_batches'),
            batch_method=progress.get('batch_method'),
            heartbeat_at=progress.get('heartbeat_at'),
            elapsed_seconds=progress.get('elapsed_seconds'),
            scored_questions=progress.get('scored_questions'),
            total_questions=progress.get('total_questions'),
            answered=progress.get('answered'),
            zero_score=progress.get('zero_score'),
            final_score=progress.get('final_score'),
            llm_scored=progress.get('llm_scored'),
            script_fallback=progress.get('script_fallback'),
            scoring_error=progress.get('error'),
        )

    update_live_status(build_type, 'score_tc01')
    tc01_result = score_tc01(
        concept_answers_file,
        JUDGE_DIR / '概念.json',
        output_dir,
        build_type,
        progress_callback=on_score_progress,
    )
    update_live_status(build_type, 'score_tc02', tc01_score=tc01_result['final_score'])
    tc02_result = score_tc02(
        qa_answers_file,
        JUDGE_DIR / '问答.json',
        output_dir,
        build_type,
        progress_callback=on_score_progress,
    )

    total_score = tc01_result['final_score'] + tc02_result['final_score']

    return {
        'tc01': tc01_result,
        'tc02': tc02_result,
        'total_score': total_score,
        'max_score': 100,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description='Sediment Full Test Runner')
    parser.add_argument(
        '--build-type', choices=['full', 'batched', 'both'], default='both',
        help='Which build(s) to run: full, batched, or both (default: both)',
    )
    parser.add_argument(
        '--skip-build', action='store_true',
        help='Skip build, only score existing results',
    )
    parser.add_argument(
        '--no-report', action='store_true',
        help='Skip HTML report generation',
    )
    args = parser.parse_args()

    log(f"\n{'#'*60}")
    log(f"Sediment 全流程测试运行器")
    log(f"{'#'*60}")
    log(f"Project root: {PROJECT_ROOT}")
    if not args.skip_build:
        log(f"Material files: {len(get_material_files())}")
    log(f"Test cases: 概念(100), 问答(100)")
    log(f"Mode: {'SKIP-BUILD (score only)' if args.skip_build else f'build={args.build_type}'}")
    log(f"Pass threshold: {PASS_THRESHOLD}/100")

    ensure_results_layout(PATHS)
    preflight = run_preflight_checks()
    write_json(REPORTS_DIR / 'preflight.json', preflight)
    log(f"Preflight OK: skills={', '.join(preflight['skill_sources'].values())}")

    # Determine which builds to run
    build_types = []
    if args.build_type in ('full', 'both'):
        build_types.append('full')
    if args.build_type in ('batched', 'both'):
        build_types.append('batched')

    all_results = {}
    overall_start = time.time()
    archived = None

    if not args.skip_build:
        archived = archive_previous_results()
        if archived:
            log(f"Archived previous results to {archived}")

    mode = 'skip-build' if args.skip_build else args.build_type
    reset_live_status(mode)
    update_live_status(None, 'starting', status='running', mode=mode)

    if args.skip_build:
        log(f"\nScoring existing results for: {', '.join(build_types)}")
        for build_type in build_types:
            update_live_status(build_type, 'score_existing')
            all_results[build_type] = score_existing(build_type, BUILDS_DIR / build_type)
    else:
        for i, build_type in enumerate(build_types):
            port = MCP_PORT_BASE + (i * 100)
            label = "全量" if build_type == 'full' else "分批"
            log(f"\n{'*'*60}")
            log(f"BUILD {i+1}/{len(build_types)}: {label} ({build_type})")
            log(f"{'*'*60}")
            build_output_dir = BUILDS_DIR / build_type
            shutil.rmtree(build_output_dir, ignore_errors=True)
            build_output_dir.mkdir(parents=True, exist_ok=True)
            all_results[build_type] = await build_and_test(
                build_type, build_output_dir, port, preserve_isolated=True
            )
            elapsed = time.time() - overall_start
            log(f"\n  Overall elapsed: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    # Calculate average
    scores = []
    for build_type, result in all_results.items():
        if 'total_score' in result:
            scores.append(result['total_score'])

    if scores:
        avg_score = sum(scores) / len(scores)
        log(f"\n{'='*60}")
        log(f"AVERAGE SCORE: {avg_score:.1f}/100")
        log(f"{'='*60}")

        # Write scorecard
        scorecard = {
            'builds': {k: {
                'tc01': v.get('tc01', {}).get('final_score', 0),
                'tc02': v.get('tc02', {}).get('final_score', 0),
                'total': v.get('total_score', 0),
                'error': v.get('error'),
                'started_at': v.get('started_at'),
                'finished_at': v.get('finished_at'),
                'duration_seconds': v.get('duration_seconds'),
                'isolated_dir': v.get('isolated_dir'),
                'cleanup_policy': v.get('cleanup_policy'),
                'kb_diagnostics_file': v.get('kb_diagnostics_file'),
                'query_transport': v.get('query_transport'),
            } for k, v in all_results.items()},
            'average_score': round(avg_score, 2),
            'max_score': 100,
            'pass_threshold': PASS_THRESHOLD,
            'passed': avg_score >= PASS_THRESHOLD,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'archived_previous_run': str(archived) if archived else None,
        }

        if avg_score >= PASS_THRESHOLD:
            cleaned_dirs = cleanup_isolated_dirs(all_results)
            scorecard['cleaned_isolated_dirs'] = cleaned_dirs
            for result in all_results.values():
                if result.get('isolated_dir') in cleaned_dirs:
                    result['cleanup_policy'] = f'cleaned after passing threshold {PASS_THRESHOLD}'
            log(f"Cleaned preserved isolated dirs: {len(cleaned_dirs)}")
        else:
            preserved_dirs = [r.get('isolated_dir') for r in all_results.values() if r.get('isolated_dir')]
            scorecard['preserved_isolated_dirs'] = preserved_dirs
            log("Preserving isolated dirs for diagnosis because the average is below threshold")

        write_json(REPORTS_DIR / 'scorecard.json', scorecard)
        log(f"Scorecard saved: {REPORTS_DIR / 'scorecard.json'}")

        # Write markdown scorecard
        md_lines = [
            "# Sediment 测试评分卡",
            "",
            f"**平均分：{avg_score:.1f}/100** {'通过' if avg_score >= PASS_THRESHOLD else '未通过'}",
            f"**通过标准：≥ {PASS_THRESHOLD} 分**",
            "",
            "| 构建方式 | TC-01 (40分) | TC-02 (60分) | 总分 |",
            "|---------|-------------|-------------|------|",
        ]
        for build_type, result in all_results.items():
            t01 = result.get('tc01', {}).get('final_score', 0)
            t02 = result.get('tc02', {}).get('final_score', 0)
            total = result.get('total_score', 0)
            label = "全量" if build_type == 'full' else "分批"
            md_lines.append(f"| {label} | {t01:.1f} | {t02:.1f} | {total:.1f} |")
        md_lines.append(f"| **平均** | | | **{avg_score:.1f}** |")
        md_lines.append("")
        if avg_score < PASS_THRESHOLD:
            md_lines.append("## 已保留的临时 KB")
            for build_type, result in all_results.items():
                if result.get('isolated_dir'):
                    md_lines.append(f"- {build_type}: `{result['isolated_dir']}`")
            md_lines.append("")

        with open(REPORTS_DIR / 'scorecard.md', 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))
        log(f"Scorecard saved: {REPORTS_DIR / 'scorecard.md'}")

        run_summary = {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'preflight': preflight,
            'builds': all_results,
            'average_score': round(avg_score, 2),
            'layout': {
                'builds_dir': str(BUILDS_DIR),
                'reports_dir': str(REPORTS_DIR),
                'improvements_dir': str(IMPROVEMENTS_DIR),
                'history_dir': str(HISTORY_DIR),
            },
            'pass_threshold': PASS_THRESHOLD,
            'archived_previous_run': str(archived) if archived else None,
        }
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        write_json(REPORTS_DIR / 'last_run.json', run_summary)
        write_json(REPORTS_DIR / f'run_{ts}.json', run_summary)
        log(f"Run summary saved: {REPORTS_DIR / 'last_run.json'}")
        update_live_status(None, 'completed', status='completed', average_score=round(avg_score, 2))

        # Generate HTML report
        if not args.no_report:
            try:
                update_live_status(None, 'reporting', status='running', average_score=round(avg_score, 2))
                from generate_report import generate_report_from_results
                report_files = generate_report_from_results(RESULTS_DIR, all_results)
                for rf in report_files:
                    log(f"HTML report: {rf}")
                update_live_status(
                    None,
                    'reporting',
                    status='completed',
                    average_score=round(avg_score, 2),
                    report_files=report_files,
                )
            except Exception as e:
                log(f"Warning: Failed to generate HTML report: {e}")
                import traceback
                log(traceback.format_exc())
                update_live_status(
                    None,
                    'reporting',
                    status='failed',
                    average_score=round(avg_score, 2),
                    error=f'report generation failed: {e}',
                )

    else:
        log("No valid scores obtained")
        update_live_status(None, 'failed', status='failed', error='No valid scores obtained')
        return 0

    overall_elapsed = time.time() - overall_start
    log(f"\n{'#'*60}")
    log(f"ALL DONE. Total elapsed: {overall_elapsed:.0f}s ({overall_elapsed/60:.1f}min)")
    log(f"{'#'*60}")

    return avg_score


if __name__ == '__main__':
    try:
        score = asyncio.run(main())
    except KeyboardInterrupt:
        update_live_status(
            None,
            'interrupted',
            status='interrupted',
            interrupted_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        log("Benchmark interrupted by user. Preserved current artifacts and isolated dirs for diagnosis.")
        sys.exit(130)
    print(f"\nFINAL_SCORE={score:.1f}")
    if score >= PASS_THRESHOLD:
        print(f"PASSED: Score exceeds {PASS_THRESHOLD} points")
    else:
        print(f"FAILED: Score {score:.1f}/100 is below {PASS_THRESHOLD}")
    sys.exit(0 if score >= PASS_THRESHOLD else 1)
