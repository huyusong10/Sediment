"""
run_all_scores.py — Sediment 全流程测试运行器

执行完整的测试流程：
1. 通过 isolated_build.py 隔离项目并构建 KB
2. 对每个构建启动 MCP server，执行 TC-01 和 TC-02
3. 计算平均分，输出 scorecard

用法：
    # 完整流程（全量 + 分批 + 评分）
    python testcase/scripts/run_all_scores.py

    # 仅全量构建
    python testcase/scripts/run_all_scores.py --build-type full

    # 仅分批构建
    python testcase/scripts/run_all_scores.py --build-type batched

    # 仅评分（已有构建结果时）
    python testcase/scripts/run_all_scores.py --skip-build
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

# Add scripts dir to path for isolated_build imports
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from isolated_build import (
    IsolatedBuilder,
    MCPServer,
    log,
    get_material_files,
    chunk_list,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = SCRIPTS_DIR.parent.parent
TESTCASE_DIR = PROJECT_ROOT / 'testcase'
JUDGE_DIR = TESTCASE_DIR / 'judge'
RESULTS_DIR = TESTCASE_DIR / 'results'

MCP_PORT_BASE = 18800


# ---------------------------------------------------------------------------
# Test Execution
# ---------------------------------------------------------------------------

async def run_concept_test(server: MCPServer, judge_file: Path) -> list[dict]:
    """Run TC-01: concept coverage test."""
    with open(judge_file, 'r', encoding='utf-8') as f:
        judge_data = json.load(f)

    results = []
    total = len(judge_data['terms'])

    for i, (concept, defn) in enumerate(judge_data['terms'].items()):
        question = f"什么是{concept}？"
        answer_text = await server.call_tool('knowledge_ask', {'question': question})

        try:
            result = json.loads(answer_text)
            answer = result.get('answer', '')
            sources = result.get('sources', [])
        except (json.JSONDecodeError, TypeError):
            answer = answer_text
            sources = []

        results.append({
            'concept': concept,
            'question': question,
            'answer': answer,
            'sources': sources,
            'definition': defn.get('definition', ''),
        })

        if (i + 1) % 20 == 0:
            log(f"Concept test: {i + 1}/{total}")

    log(f"Concept test complete: {len(results)}/{total}")
    return results


async def run_qa_test(server: MCPServer, judge_file: Path) -> list[dict]:
    """Run TC-02: QA accuracy test."""
    with open(judge_file, 'r', encoding='utf-8') as f:
        judge_data = json.load(f)

    results = []
    questions = judge_data.get('questions', [])
    total = len(questions)

    for i, q in enumerate(questions):
        answer_text = await server.call_tool('knowledge_ask', {'question': q['question']})

        try:
            result = json.loads(answer_text)
            answer = result.get('answer', '')
            sources = result.get('sources', [])
        except (json.JSONDecodeError, TypeError):
            answer = answer_text
            sources = []

        results.append({
            'id': q['id'],
            'question': q['question'],
            'difficulty': q.get('difficulty', 'medium'),
            'answer': answer,
            'sources': sources,
            'standard_answer': q.get('standard_answer', ''),
            'expected_keywords': q.get('expected_keywords', []),
        })

        if (i + 1) % 20 == 0:
            log(f"QA test: {i + 1}/{total}")

    log(f"QA test complete: {len(results)}/{total}")
    return results


# ---------------------------------------------------------------------------
# Build & Test Pipeline
# ---------------------------------------------------------------------------

async def build_and_test(build_type: str, output_dir: Path, port: int) -> dict:
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

    builder = IsolatedBuilder(build_type=build_type, port=port)
    results = {'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    build_start = time.time()

    try:
        # Step 1: Create isolated copy and build
        await builder.create_isolated_copy()
        await builder.build()

        # Save KB snapshot
        kb_snapshot = output_dir / f'kb_{build_type}'
        if builder.kb_dir and builder.kb_dir.exists():
            shutil.copytree(builder.kb_dir, kb_snapshot, dirs_exist_ok=True)
            entry_count = len(list((builder.kb_dir / 'entries').glob('*.md')))
            placeholder_count = len(list((builder.kb_dir / 'placeholders').glob('*.md')))
            log(f"KB snapshot saved: {entry_count} entries, {placeholder_count} placeholders")

        # Step 2: Start MCP server
        server = builder.start_mcp_server(port=port)
        started = await server.start()
        if not started:
            log("Failed to start MCP server")
            results['error'] = 'MCP server failed to start'
            return results

        try:
            # Step 3: Run concept test
            log("\nRunning TC-01: Concept Coverage...")
            concept_results = await run_concept_test(server, JUDGE_DIR / '概念.json')

            # Save concept answers
            concept_answers_file = output_dir / f'concept_answers_{build_type}.json'
            with open(concept_answers_file, 'w', encoding='utf-8') as f:
                json.dump({'results': concept_results}, f, ensure_ascii=False, indent=2)

            # Score TC-01
            from score_tc01 import run_scoring as score_tc01
            tc01_result = score_tc01(concept_answers_file, JUDGE_DIR / '概念.json', output_dir, build_type)
            results['tc01'] = tc01_result

            # Run QA test
            log("\nRunning TC-02: QA Accuracy...")
            qa_results = await run_qa_test(server, JUDGE_DIR / '问答.json')

            # Save QA answers
            qa_answers_file = output_dir / f'qa_answers_{build_type}.json'
            with open(qa_answers_file, 'w', encoding='utf-8') as f:
                json.dump({'results': qa_results}, f, ensure_ascii=False, indent=2)

            # Score TC-02
            from score_tc02 import run_scoring as score_tc02
            tc02_result = score_tc02(qa_answers_file, JUDGE_DIR / '问答.json', output_dir, build_type)
            results['tc02'] = tc02_result

            # Combined score
            total_score = tc01_result['final_score'] + tc02_result['final_score']
            results['total_score'] = total_score
            results['max_score'] = 100
            results['finished_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            results['duration_seconds'] = round(time.time() - build_start, 1)
            log(f"\n{'='*60}")
            log(f"{build_type} build total score: {total_score:.1f}/100")
            log(f"  TC-01: {tc01_result['final_score']:.1f}/40")
            log(f"  TC-02: {tc02_result['final_score']:.1f}/60")
            log(f"{'='*60}")

        finally:
            await server.stop()

    except Exception as e:
        log(f"Build {build_type} failed with exception: {e}")
        import traceback
        log(traceback.format_exc())
        results['error'] = str(e)

    finally:
        # Cleanup isolated dir
        await builder.cleanup()

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

    tc01_result = score_tc01(concept_answers_file, JUDGE_DIR / '概念.json', output_dir, build_type)
    tc02_result = score_tc02(qa_answers_file, JUDGE_DIR / '问答.json', output_dir, build_type)

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

    log(f"Project root: {PROJECT_ROOT}")
    if not args.skip_build:
        log(f"Material files: {len(get_material_files())}")
    log(f"Test cases: 概念(100), 问答(100)")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Determine which builds to run
    build_types = []
    if args.build_type in ('full', 'both'):
        build_types.append('full')
    if args.build_type in ('batched', 'both'):
        build_types.append('batched')

    all_results = {}

    if args.skip_build:
        for build_type in build_types:
            all_results[build_type] = score_existing(build_type, RESULTS_DIR)
    else:
        for i, build_type in enumerate(build_types):
            port = MCP_PORT_BASE + (i * 100)
            all_results[build_type] = await build_and_test(build_type, RESULTS_DIR, port)

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
            } for k, v in all_results.items()},
            'average_score': round(avg_score, 2),
            'max_score': 100,
            'passed': avg_score >= 80,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        with open(RESULTS_DIR / 'scorecard.json', 'w', encoding='utf-8') as f:
            json.dump(scorecard, f, ensure_ascii=False, indent=2)

        # Write markdown scorecard
        md_lines = [
            "# Sediment 测试评分卡",
            "",
            f"**平均分：{avg_score:.1f}/100** {'✅ 通过' if avg_score >= 80 else '❌ 未通过'}",
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

        with open(RESULTS_DIR / 'scorecard.md', 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))

        # Generate HTML report
        if not args.no_report:
            try:
                from generate_report import generate_report_from_results
                report_files = generate_report_from_results(RESULTS_DIR, all_results)
                for rf in report_files:
                    log(f"HTML report: {rf}")
            except Exception as e:
                log(f"Warning: Failed to generate HTML report: {e}")
                import traceback
                log(traceback.format_exc())

    else:
        log("No valid scores obtained")
        return 0

    return avg_score


if __name__ == '__main__':
    score = asyncio.run(main())
    print(f"\nFINAL_SCORE={score:.1f}")
    if score >= 80:
        print("PASSED: Score exceeds 80 points")
    else:
        print(f"FAILED: Score {score:.1f}/100 is below 80")
    sys.exit(0 if score >= 80 else 1)
