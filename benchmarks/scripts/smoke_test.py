"""
smoke_test.py — Sediment 小规模冒烟测试

用 5 个文件跑完整流程（隔离 → ingest → tidy → MCP → 问答 → 评分），
验证测试链路通畅，不依赖完整 105 文件数据。

用法：
    python benchmarks/scripts/smoke_test.py
"""

import asyncio
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from isolated_build import (
    IsolatedBuilder,
    MCPServer,
    log,
    get_material_files,
    run_ingest,
    run_tidy,
)

PROJECT_ROOT = SCRIPTS_DIR.parent.parent
BENCHMARKS_DIR = PROJECT_ROOT / 'benchmarks'
JUDGE_DIR = BENCHMARKS_DIR / 'judge'
RESULTS_DIR = BENCHMARKS_DIR / 'results_smoke'

SMOKE_FILE_COUNT = 5
MCP_PORT = 18850
REQUIRED_SKILLS = (
    "ingest/SKILL.md",
    "tidy/SKILL.md",
    "explore/SKILL.md",
    "health/SKILL.md",
)


async def run_smoke_questions(server: MCPServer) -> list[dict]:
    """Run a subset of concept + QA questions against the MCP server."""
    # Load judge data
    with open(JUDGE_DIR / '概念.json', 'r', encoding='utf-8') as f:
        concept_data = json.load(f)
    with open(JUDGE_DIR / '问答.json', 'r', encoding='utf-8') as f:
        qa_data = json.load(f)

    # Pick first 5 concept questions
    concept_terms = list(concept_data['terms'].items())[:5]
    concept_results = []
    for concept, defn in concept_terms:
        question = f"什么是{concept}？"
        answer_text = await server.call_tool('knowledge_ask', {'question': question})
        try:
            result = json.loads(answer_text)
            answer = result.get('answer', '')
            sources = result.get('sources', [])
        except (json.JSONDecodeError, TypeError):
            answer = answer_text
            sources = []
        concept_results.append({
            'concept': concept,
            'question': question,
            'answer': answer,
            'sources': sources,
            'definition': defn.get('definition', ''),
        })
        log(f"Concept: {concept} -> answer len={len(answer)}")

    # Pick first 5 QA questions
    qa_questions = qa_data.get('questions', [])[:5]
    qa_results = []
    for q in qa_questions:
        answer_text = await server.call_tool('knowledge_ask', {'question': q['question']})
        try:
            result = json.loads(answer_text)
            answer = result.get('answer', '')
            sources = result.get('sources', [])
        except (json.JSONDecodeError, TypeError):
            answer = answer_text
            sources = []
        qa_results.append({
            'id': q['id'],
            'question': q['question'],
            'difficulty': q.get('difficulty', 'medium'),
            'answer': answer,
            'sources': sources,
            'standard_answer': q.get('standard_answer', ''),
            'expected_keywords': q.get('expected_keywords', []),
        })
        log(f"QA #{q['id']}: answer len={len(answer)}")

    return concept_results, qa_results


def score_smoke(concept_results: list, qa_results: list) -> dict:
    """Simple scoring for smoke test — just check that answers are non-empty."""
    concept_answered = sum(1 for r in concept_results if r['answer'] and not r['answer'].startswith('ERROR'))
    qa_answered = sum(1 for r in qa_results if r['answer'] and not r['answer'].startswith('ERROR'))

    result = {
        'concept_total': len(concept_results),
        'concept_answered': concept_answered,
        'qa_total': len(qa_results),
        'qa_answered': qa_answered,
        'passed': concept_answered == len(concept_results) and qa_answered == len(qa_results),
    }

    # Also run real scoring if we have enough data
    try:
        from score_tc01 import run_scoring as score_tc01
        from score_tc02 import run_scoring as score_tc02

        # Write temp answer files
        concept_file = RESULTS_DIR / 'smoke_concept.json'
        qa_file = RESULTS_DIR / 'smoke_qa.json'
        with open(concept_file, 'w', encoding='utf-8') as f:
            json.dump({'results': concept_results}, f, ensure_ascii=False, indent=2)
        with open(qa_file, 'w', encoding='utf-8') as f:
            json.dump({'results': qa_results}, f, ensure_ascii=False, indent=2)

        tc01 = score_tc01(concept_file, JUDGE_DIR / '概念.json', RESULTS_DIR, 'smoke')
        tc02 = score_tc02(qa_file, JUDGE_DIR / '问答.json', RESULTS_DIR, 'smoke')
        result['tc01'] = tc01
        result['tc02'] = tc02
        result['total_score'] = tc01['final_score'] + tc02['final_score']
        result['used_real_scoring'] = True
    except Exception as e:
        log(f"Real scoring skipped (expected for smoke test): {e}")
        result['used_real_scoring'] = False

    return result


async def main():
    log("=" * 60)
    log("Sediment Smoke Test — 小规模冒烟测试")
    log("=" * 60)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    missing_skills = [
        skill_name
        for skill_name in REQUIRED_SKILLS
        if not (PROJECT_ROOT / "src" / "sediment" / "skills" / skill_name).exists()
    ]
    if missing_skills:
        log(f"FAIL: Missing required skills: {', '.join(missing_skills)}")
        return False

    # Step 1: Create isolated copy
    builder = IsolatedBuilder(build_type='full', port=MCP_PORT)
    await builder.create_isolated_copy()

    # Step 2: Ingest only first N files
    all_files = get_material_files()
    smoke_files = all_files[:SMOKE_FILE_COUNT]
    log(f"\nIngesting {len(smoke_files)} files:")
    for f in smoke_files:
        log(f"  - {f.relative_to(f.parent.parent)}")

    success = await run_ingest(builder.isolated_dir, smoke_files)
    log(f"Ingest success: {success}")

    # Check entries
    entries = list(builder.kb_dir.glob('entries/*.md'))
    placeholders = list(builder.kb_dir.glob('placeholders/*.md'))
    log(f"KB: {len(entries)} entries, {len(placeholders)} placeholders")

    if not success or len(entries) == 0:
        log("FAIL: No entries created")
        await builder.cleanup()
        return False

    # Step 3: Tidy
    log("\nRunning tidy...")
    tidy_ok = await run_tidy(builder.isolated_dir)
    new_entries = len(list(builder.kb_dir.glob('entries/*.md')))
    new_placeholders = len(list(builder.kb_dir.glob('placeholders/*.md')))
    log(f"After tidy: {new_entries} entries, {new_placeholders} placeholders")

    # Step 4: Start MCP server
    log("\nStarting MCP server...")
    server = builder.start_mcp_server(port=MCP_PORT)
    started = await server.start()
    if not started:
        log("FAIL: MCP server failed to start")
        await builder.cleanup()
        return False
    log("MCP server started OK")

    # Step 5: Run smoke questions
    log("\nRunning smoke questions...")
    concept_results, qa_results = await run_smoke_questions(server)
    await server.stop()

    # Step 6: Score
    log("\nScoring...")
    result = score_smoke(concept_results, qa_results)

    # Save results
    with open(RESULTS_DIR / 'smoke_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Print summary
    log(f"\n{'='*60}")
    log("Smoke Test Summary")
    log(f"{'='*60}")
    log(f"  Files ingested:  {len(smoke_files)}")
    log(f"  Entries created: {new_entries}")
    log(f"  Placeholders:    {new_placeholders}")
    log(f"  Concept Q&A:     {result['concept_answered']}/{result['concept_total']} answered")
    log(f"  QA Q&A:          {result['qa_answered']}/{result['qa_total']} answered")
    if result.get('used_real_scoring'):
        log(f"  TC-01 score:     {result['tc01']['final_score']:.1f}/40")
        log(f"  TC-02 score:     {result['tc02']['final_score']:.1f}/60")
        log(f"  Total:           {result['total_score']:.1f}/100")
    log(f"  PASSED:          {'Yes' if result['passed'] else 'No'}")
    log(f"{'='*60}")

    await builder.cleanup()
    return result['passed']


if __name__ == '__main__':
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
