"""
score_tc02.py — TC-02 问答准确率评分脚本（60 分）

读取问答结果，通过多维度评估每题质量：
- accuracy: 回答是否准确传达了标准答案的核心意思
- completeness: 是否覆盖了标准答案的主要要点
- keyword_coverage: 是否包含预期关键词
- reasoning: 回答是否展现了合理的推理链条

采用 LLM 评分器 + 脚本评分混合模式：
- LLM 评分器：批量（10题/组）通过共享 `SEDIMENT_CLI` 合约进行语义评分
- 脚本评分：作为 LLM 评分失败时的 fallback
- 否定检测：回答与标准答案矛盾时直接判 0 分
- 因果链验证：对 medium/hard 题检查回答是否包含与标准答案对应的逻辑关系

每题得分 = 综合评分 × 该题满分值
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / 'src'
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sediment.llm_cli import build_cli_command, collect_output


SCORING_HEARTBEAT_SECONDS = max(
    5,
    int(os.environ.get('SEDIMENT_BENCHMARK_SCORING_HEARTBEAT_SECONDS', '20')),
)


# ---------------------------------------------------------------------------
# Script-based Scoring (fallback)
# ---------------------------------------------------------------------------

def _extract_tokens(text):
    """Extract Chinese char bigrams and English words."""
    chars = re.findall(r'[\u4e00-\u9fff]', text)
    bigrams = set()
    for i in range(len(chars) - 1):
        bigrams.add(chars[i] + chars[i + 1])
    words = set(re.findall(r'[a-zA-Z][a-zA-Z0-9]*', text.lower()))
    return bigrams | words


def _check_contradiction(answer: str, standard_answer: str) -> bool:
    """
    检测回答是否与标准答案矛盾。
    如果标准答案说"X 是 Y"，回答中出现"X 不是 Y"等否定形式，返回 True。
    """
    # Extract key subject-predicate pairs from standard answer
    # Look for "X是Y" patterns
    is_patterns = re.findall(r'([\u4e00-\u9fff]{2,8})是([^，。、；：,!?\n]{2,20})', standard_answer)

    for subject, predicate in is_patterns:
        # Check if answer says the opposite
        negation_patterns = [
            rf'{subject}.*?不[是是]',
            rf'{subject}.*?(并非|不属于|不存在|没有)',
            rf'不[是是].*?{predicate[:4]}',
        ]
        for pattern in negation_patterns:
            if re.search(pattern, answer):
                return True

    return False


def _check_causal_chain(answer: str, standard_answer: str) -> float:
    """
    因果链验证：检查标准答案中的逻辑关系是否在回答中也得到体现。
    返回 0-1 的分数。
    """
    causal_markers = ['因为', '所以', '因此', '导致', '由于', '从而', '进而', '使得', '因而']

    # Find causal markers in standard answer
    standard_causals = [m for m in causal_markers if m in standard_answer]
    if not standard_causals:
        # No causal logic in standard answer, full score for this dimension
        return 1.0

    # Check if answer also contains causal markers
    answer_causals = [m for m in causal_markers if m in answer]
    if not answer_causals:
        return 0.0

    # Check overlap: does the answer use similar causal logic?
    overlap = len(set(standard_causals) & set(answer_causals))
    return min(overlap / len(standard_causals), 1.0)


def score_question_script(answer_text: str, question: dict) -> dict:
    """
    脚本评分单个问答，返回各维度分数。
    作为 LLM 评分失败时的 fallback。
    """
    if not answer_text or answer_text.startswith('ERROR'):
        return {
            'accuracy': 0, 'completeness': 0, 'keyword_coverage': 0,
            'reasoning': 0, 'composite': 0, 'earned': 0,
            'method': 'script',
        }

    difficulty = question.get('difficulty', 'medium')
    standard_answer = question.get('standard_answer', '')
    expected_keywords = question.get('expected_keywords', [])

    answer_lower = answer_text.lower()
    standard_lower = standard_answer.lower()

    # Negation check
    if _check_contradiction(answer_text, standard_answer):
        return {
            'accuracy': 0, 'completeness': 0, 'keyword_coverage': 0,
            'reasoning': 0, 'composite': 0, 'earned': 0,
            'method': 'script', 'contradiction': True,
        }

    # 1. Keyword coverage
    kw_matched = 0
    for kw in expected_keywords:
        kw_lower = kw.lower()
        if len(kw_lower) <= 4:
            if kw_lower in answer_lower:
                kw_matched += 1
        else:
            # Long keywords: check continuous substring
            if kw_lower in answer_lower:
                kw_matched += 1
            else:
                # Partial: check if significant contiguous portion appears
                min_sub = max(int(len(kw_lower) * 0.7), 3)
                for i in range(len(kw_lower) - min_sub + 1):
                    if kw_lower[i:i + min_sub] in answer_lower:
                        kw_matched += 0.5
                        break
    keyword_coverage = kw_matched / len(expected_keywords) if expected_keywords else 0

    # 2. Accuracy: token overlap
    standard_tokens = _extract_tokens(standard_answer)
    answer_tokens = _extract_tokens(answer_text)
    if standard_tokens:
        overlap = len(standard_tokens & answer_tokens)
        accuracy = overlap / len(standard_tokens)
    else:
        accuracy = 0
    if accuracy > 0.5:
        accuracy = min(accuracy * 1.2, 1.0)

    # 3. Completeness: chunk coverage
    standard_chunks = [c.strip() for c in re.split(r'[。！？.!?,，；;]', standard_answer) if len(c.strip()) > 1]
    if standard_chunks:
        chunk_hits = 0
        for chunk in standard_chunks:
            chunk_chars = set(re.findall(r'[\u4e00-\u9fff]', chunk))
            if chunk_chars and len(chunk_chars & set(re.findall(r'[\u4e00-\u9fff]', answer_text))) / len(chunk_chars) >= 0.5:
                chunk_hits += 1
        completeness = chunk_hits / len(standard_chunks)
    else:
        completeness = 0

    # 4. Reasoning depth: causal chain validation
    causal_score = _check_causal_chain(answer_text, standard_answer)
    reasoning = 0.0
    if difficulty in ('medium', 'hard'):
        reasoning = causal_score
        # Also consider explanatory markers
        reasoning_markers = ['因为', '所以', '因此', '导致', '原因', '机制', '过程',
                           '如果', '则', '意味着', '说明', '分为', '包括', '需要']
        marker_count = sum(1 for m in reasoning_markers if m in answer_text)
        marker_bonus = min(marker_count / 4, 0.3)
        reasoning = min(reasoning * 0.7 + marker_bonus, 1.0)

    # Composite
    if difficulty == 'easy':
        composite = accuracy * 0.4 + completeness * 0.3 + keyword_coverage * 0.3
    elif difficulty == 'medium':
        composite = accuracy * 0.3 + completeness * 0.3 + keyword_coverage * 0.3 + reasoning * 0.1
    else:
        composite = accuracy * 0.25 + completeness * 0.25 + keyword_coverage * 0.25 + reasoning * 0.25

    difficulty_max = {'easy': 0.3, 'medium': 0.6, 'hard': 0.69}
    max_points = difficulty_max.get(difficulty, 0.6)
    earned = composite * max_points

    return {
        'accuracy': round(accuracy, 4),
        'completeness': round(completeness, 4),
        'keyword_coverage': round(keyword_coverage, 4),
        'reasoning': round(reasoning, 4),
        'composite': round(composite, 4),
        'earned': round(earned, 4),
        'max_points': max_points,
        'method': 'script',
    }


# ---------------------------------------------------------------------------
# LLM-based Scoring
# ---------------------------------------------------------------------------

def build_llm_scoring_prompt(batch: list[dict]) -> str:
    """Build a prompt for LLM to score a batch of QA results."""
    parts = []
    parts.append("""你是一个考试评分助手。请对以下学生的回答进行评分。

评分标准（每个维度 0-1 分）：
1. accuracy（准确性）：回答是否准确传达了标准答案的核心意思，没有事实错误或矛盾
2. completeness（完整性）：是否覆盖了标准答案的主要要点
3. keyword_coverage（关键词覆盖）：是否包含预期关键词
4. reasoning（推理深度）：回答是否展现了合理的推理链条，是否解释了"为什么"而不仅仅是"是什么"

对于每个维度，请给出 0-1 的精确分数（可以有小数，如 0.75）。

请以 JSON 格式输出评分结果，格式为：
[
  {"id": 题目ID, "accuracy": 0.8, "completeness": 0.7, "keyword_coverage": 0.9, "reasoning": 0.6},
  ...
]

只输出 JSON 数组，不要任何其他文字。
""")

    parts.append(f"\n共 {len(batch)} 道题：\n")

    for i, q in enumerate(batch):
        parts.append(f"\n--- 题目 {i+1}/{len(batch)} ---")
        parts.append(f"ID: {q['id']}")
        parts.append(f"难度: {q.get('difficulty', 'medium')}")
        parts.append(f"问题: {q['question']}")
        parts.append(f"标准答案: {q.get('standard_answer', '')}")
        parts.append(f"预期关键词: {', '.join(q.get('expected_keywords', []))}")
        parts.append(f"学生回答: {q.get('answer', '')[:500]}")  # Truncate very long answers

    return '\n'.join(parts)


def run_llm_scoring(
    batch: list[dict],
    workdir: Path | None = None,
    *,
    progress_callback: Callable[[dict], None] | None = None,
    batch_num: int | None = None,
    total_batches: int | None = None,
) -> list[dict] | None:
    """
    Use the shared Sediment LLM CLI contract to score a batch of questions.
    Returns list of scoring results, or None if LLM scoring fails.
    """
    prompt = build_llm_scoring_prompt(batch)
    cli_value = os.environ.get('SEDIMENT_CLI', 'claude').strip()
    settings = build_benchmark_agent_settings(cli_value)
    needs_prompt_files = settings.get('agent', {}).get('backend') == 'codex'
    extra_args = _scoring_cli_extra_args(settings)
    temp_root = None
    prompt_file = None
    payload_file = None
    skill_file = None
    proc = None
    if needs_prompt_files:
        temp_root_parent = workdir if workdir and workdir.exists() else None
        temp_root = Path(
            tempfile.mkdtemp(
                prefix='sediment-benchmark-score-',
                dir=str(temp_root_parent) if temp_root_parent else None,
            )
        )
        prompt_file = temp_root / 'prompt.txt'
        payload_file = temp_root / 'payload.json'
        skill_file = temp_root / 'skill.md'
        prompt_file.write_text(prompt, encoding='utf-8')
        payload_file.write_text("{}", encoding='utf-8')
        skill_file.write_text("", encoding='utf-8')
    try:
        invocation = build_cli_command(
            settings,
            prompt,
            prompt_file=prompt_file,
            payload_file=payload_file,
            skill_file=skill_file,
            cwd=workdir,
            extra_args=extra_args,
        )
        started_at = time.time()
        proc = subprocess.Popen(
            invocation.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(workdir) if workdir else None,
        )
        stdout = ''
        stderr = ''
        pending_input = invocation.stdin_data
        while True:
            elapsed = time.time() - started_at
            remaining = 600 - elapsed
            if remaining <= 0:
                proc.kill()
                stdout, stderr = proc.communicate()
                raise subprocess.TimeoutExpired(invocation.command, 600, output=stdout, stderr=stderr)
            try:
                stdout, stderr = proc.communicate(
                    input=pending_input,
                    timeout=min(SCORING_HEARTBEAT_SECONDS, remaining),
                )
                break
            except subprocess.TimeoutExpired:
                pending_input = None
                if progress_callback:
                    progress_callback(
                        {
                            'phase': 'score_tc02',
                            'event': 'heartbeat',
                            'batch_num': batch_num,
                            'total_batches': total_batches,
                            'heartbeat_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                            'elapsed_seconds': round(elapsed, 1),
                        }
                    )

        output = collect_output(invocation, stdout=stdout, stderr=stderr)

        # Try to extract JSON from the output
        # Claude might wrap JSON in markdown code blocks
        json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', output, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON array directly
            json_match = re.search(r'\[.*\]', output, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                return None

        scores = json.loads(json_str)

        # Validate the structure
        if not isinstance(scores, list):
            return None

        # Match scores to question IDs
        result = {}
        for s in scores:
            if isinstance(s, dict) and 'id' in s:
                result[s['id']] = s

        return result

    except subprocess.TimeoutExpired:
        if progress_callback:
            progress_callback(
                {
                    'phase': 'score_tc02',
                    'event': 'batch_timeout',
                    'batch_num': batch_num,
                    'total_batches': total_batches,
                }
            )
        return None
    except json.JSONDecodeError:
        if progress_callback:
            progress_callback(
                {
                    'phase': 'score_tc02',
                    'event': 'batch_parse_failed',
                    'batch_num': batch_num,
                    'total_batches': total_batches,
                }
            )
        return None
    except Exception as exc:
        if progress_callback:
            progress_callback(
                {
                    'phase': 'score_tc02',
                    'event': 'batch_exception',
                    'batch_num': batch_num,
                    'total_batches': total_batches,
                    'error': str(exc),
                }
            )
        return None
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.communicate()
        if temp_root is not None:
            shutil.rmtree(temp_root, ignore_errors=True)


def build_benchmark_agent_settings(cli_value: str) -> dict[str, Any]:
    settings, _ = _build_scoring_agent_settings(
        cli_value=cli_value,
        max_budget_usd='3',
    )
    return settings


def _scoring_cli_extra_args(settings: dict[str, Any]) -> list[str]:
    agent = settings.get('agent', {})
    backend = str(agent.get('backend', '')).strip().lower()
    base_args = list(agent.get('extra_args', []) or [])
    if backend == 'codex':
        return [*base_args, '--no-session-persistence']
    return [
        *base_args,
        '--permission-mode',
        'auto',
        '--allowed-tools',
        'Bash',
        'Read',
        'Write',
        'Edit',
        'Glob',
        '--max-budget-usd',
        '3',
        '--no-session-persistence',
    ]


def _build_scoring_agent_settings(*, cli_value: str, max_budget_usd: str) -> tuple[dict, bool]:
    argv = shlex.split(cli_value, posix=os.name != 'nt')
    executable = Path(argv[0]).name.lower() if argv else 'claude'
    backend = 'claude-code'
    needs_prompt_files = False
    extra_args: list[str] = []

    if 'codex' in executable:
        backend = 'codex'
        needs_prompt_files = True
        extra_args = ['--sandbox', 'danger-full-access']
    elif 'opencode' in executable:
        backend = 'opencode'
    else:
        extra_args = [
            '--permission-mode',
            'auto',
            '--allowed-tools',
            'Bash',
            'Read',
            'Write',
            'Edit',
            'Glob',
            '--max-budget-usd',
            max_budget_usd,
            '--no-session-persistence',
        ]

    return (
        {
            'agent': {
                'backend': backend,
                'command': cli_value,
                'extra_args': extra_args,
            }
        },
        needs_prompt_files,
    )


def score_with_llm(
    questions: list[dict],
    answers_lookup: dict,
    workdir: Path | None = None,
    *,
    progress_callback: Callable[[dict], None] | None = None,
) -> list[dict]:
    """
    Score all questions using LLM in batches.
    Falls back to script scoring for failed batches.
    """
    batch_size = 10
    all_results = []
    total_batches = (len(questions) + batch_size - 1) // batch_size
    print(f"  Total batches: {total_batches} ({len(questions)} questions)", flush=True)
    if progress_callback:
        progress_callback(
            {
                'phase': 'score_tc02',
                'event': 'score_started',
                'total_batches': total_batches,
                'completed_batches': 0,
                'total_questions': len(questions),
                'scored_questions': 0,
            }
        )

    for i in range(0, len(questions), batch_size):
        batch_questions = questions[i:i + batch_size]
        batch_num = i // batch_size + 1

        print(f"  LLM scoring batch {batch_num}/{total_batches}...", flush=True)
        batch_start = time.time()
        if progress_callback:
            progress_callback(
                {
                    'phase': 'score_tc02',
                    'event': 'batch_started',
                    'batch_num': batch_num,
                    'total_batches': total_batches,
                    'completed_batches': batch_num - 1,
                    'total_questions': len(questions),
                    'scored_questions': i,
                    'heartbeat_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                }
            )

        # Prepare batch data with answers
        batch_data = []
        for q in batch_questions:
            qid = q['id']
            answer_item = answers_lookup.get(qid, {})
            batch_data.append({
                'id': qid,
                'question': q['question'],
                'difficulty': q.get('difficulty', 'medium'),
                'standard_answer': q.get('standard_answer', ''),
                'expected_keywords': q.get('expected_keywords', []),
                'answer': answer_item.get('answer', ''),
            })

        # Try LLM scoring
        llm_scores = run_llm_scoring(
            batch_data,
            workdir=workdir,
            progress_callback=progress_callback,
            batch_num=batch_num,
            total_batches=total_batches,
        )
        batch_elapsed = time.time() - batch_start

        if llm_scores:
            print(f"    LLM batch {batch_num} done in {batch_elapsed:.1f}s", flush=True)
        else:
            print(f"    LLM batch {batch_num} failed after {batch_elapsed:.1f}s, falling back to script scoring", flush=True)

        for q in batch_questions:
            qid = q['id']
            answer_item = answers_lookup.get(qid, {})
            answer_text = answer_item.get('answer', '')

            if llm_scores and qid in llm_scores:
                s = llm_scores[qid]
                difficulty = q.get('difficulty', 'medium')
                difficulty_max = {'easy': 0.3, 'medium': 0.6, 'hard': 0.69}
                max_points = difficulty_max.get(difficulty, 0.6)

                # Clamp scores to 0-1
                accuracy = max(0, min(s.get('accuracy', 0), 1))
                completeness = max(0, min(s.get('completeness', 0), 1))
                kw = max(0, min(s.get('keyword_coverage', 0), 1))
                reasoning = max(0, min(s.get('reasoning', 0), 1))

                if difficulty == 'easy':
                    composite = accuracy * 0.4 + completeness * 0.3 + kw * 0.3
                elif difficulty == 'medium':
                    composite = accuracy * 0.3 + completeness * 0.3 + kw * 0.3 + reasoning * 0.1
                else:
                    composite = accuracy * 0.25 + completeness * 0.25 + kw * 0.25 + reasoning * 0.25

                earned = composite * max_points

                all_results.append({
                    'id': qid,
                    'accuracy': round(accuracy, 4),
                    'completeness': round(completeness, 4),
                    'keyword_coverage': round(kw, 4),
                    'reasoning': round(reasoning, 4),
                    'composite': round(composite, 4),
                    'earned': round(earned, 4),
                    'max_points': max_points,
                    'method': 'llm',
                })
            else:
                # Fallback to script scoring
                script_result = score_question_script(answer_text, q)
                script_result['id'] = qid
                all_results.append(script_result)

        if progress_callback:
            progress_callback(
                {
                    'phase': 'score_tc02',
                    'event': 'batch_completed',
                    'batch_num': batch_num,
                    'total_batches': total_batches,
                    'completed_batches': batch_num,
                    'total_questions': len(questions),
                    'scored_questions': min(i + len(batch_questions), len(questions)),
                    'batch_method': 'llm' if llm_scores else 'script_fallback',
                    'heartbeat_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'elapsed_seconds': round(batch_elapsed, 1),
                }
            )

    return all_results


# ---------------------------------------------------------------------------
# Main Scoring Runner
# ---------------------------------------------------------------------------

def run_scoring(
    answers_file: Path,
    judge_file: Path,
    output_dir: Path,
    build_type: str | None = None,
    *,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict:
    """Run QA accuracy scoring and produce report."""
    with open(judge_file, 'r', encoding='utf-8') as f:
        judge_data = json.load(f)

    with open(answers_file, 'r', encoding='utf-8') as f:
        answers_data = json.load(f)

    # Build answer lookup by question id
    answers = {}
    for item in answers_data.get('results', []):
        answers[item['id']] = item

    questions = judge_data.get('questions', [])

    print(f"\n{'='*60}")
    print(f"TC-02 问答准确率评分报告")
    print(f"{'='*60}")
    print(f"  总题数: {len(questions)}")
    print(f"  使用 LLM 评分器（批量 10 题/组，共享 SEDIMENT_CLI 合约）")
    print(f"  LLM 评分失败时回退到脚本评分")

    # Score with LLM (with script fallback)
    scored_results = score_with_llm(
        questions,
        answers,
        workdir=output_dir,
        progress_callback=progress_callback,
    )

    # Build lookup by id
    results_by_id = {r['id']: r for r in scored_results}

    total_earned = 0.0
    total_max = 0.0
    details = []

    by_difficulty = {
        'easy': {'earned': 0, 'max': 0, 'count': 0},
        'medium': {'earned': 0, 'max': 0, 'count': 0},
        'hard': {'earned': 0, 'max': 0, 'count': 0},
    }

    for q in questions:
        qid = q['id']
        result = results_by_id.get(qid, score_question_script('', q))
        result['id'] = qid  # Ensure id is set

        total_earned += result['earned']
        difficulty_max = {'easy': 0.3, 'medium': 0.6, 'hard': 0.69}
        max_pts = difficulty_max.get(q['difficulty'], 0.6)
        total_max += max_pts

        diff = q['difficulty']
        by_difficulty[diff]['earned'] += result['earned']
        by_difficulty[diff]['max'] += max_pts
        by_difficulty[diff]['count'] += 1

        details.append({
            'id': qid,
            'question': q['question'][:50],
            'difficulty': diff,
            'earned': round(result['earned'], 4),
            'max_points': result.get('max_points', max_pts),
            'composite': round(result.get('composite', 0), 4),
            'method': result.get('method', 'unknown'),
            'sources': answers.get(qid, {}).get('sources', []),
        })

    # Max score is 60
    final_score = (total_earned / total_max * 60) if total_max > 0 else 0

    # Sort by score ascending (worst first)
    details.sort(key=lambda x: x['earned'])

    # Count methods
    llm_count = sum(1 for r in scored_results if r.get('method') == 'llm')
    script_count = sum(1 for r in scored_results if r.get('method') == 'script')

    result = {
        'total_earned': round(total_earned, 2),
        'total_max': round(total_max, 2),
        'final_score': round(final_score, 2),
        'max_score': 60,
        'total_questions': len(questions),
        'answered': sum(1 for d in details if d['composite'] > 0),
        'zero_score': sum(1 for d in details if d['earned'] == 0),
        'scoring_method': {
            'llm_scored': llm_count,
            'script_fallback': script_count,
        },
        'by_difficulty': {
            k: {mk: round(mv, 2) if isinstance(mv, float) else mv
                for mk, mv in v.items()}
            for k, v in by_difficulty.items()
        },
        'details': details,
    }

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = f'answers_scored_{build_type}.json' if build_type else 'answers_scored.json'
    with open(output_dir / output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"  已回答:   {result['answered']}")
    print(f"  零分:     {result['zero_score']}")
    print(f"  原始分:   {result['total_earned']:.2f}/{result['total_max']:.2f}")
    print(f"  最终得分: {result['final_score']:.1f}/60")
    print(f"  评分方式: LLM={llm_count}, 脚本={script_count}")
    print(f"\n按难度统计:")
    for diff, stats in by_difficulty.items():
        pct = stats['earned'] / stats['max'] * 100 if stats['max'] > 0 else 0
        print(f"  {diff}: {stats['earned']:.1f}/{stats['max']:.1f} ({pct:.1f}%) | {stats['count']}题")
    print(f"\n最低分题目 (Top 10):")
    for d in details[:10]:
        print(f"  Q{d['id']} [{d['difficulty']}]: {d['earned']:.3f}/{d['max_points']:.3f} | {d['question']}")

    if progress_callback:
        total_batches = (len(questions) + 9) // 10
        progress_callback(
            {
                'phase': 'score_tc02',
                'event': 'score_completed',
                'total_batches': total_batches,
                'completed_batches': total_batches,
                'total_questions': len(questions),
                'scored_questions': len(questions),
                'answered': result['answered'],
                'zero_score': result['zero_score'],
                'final_score': result['final_score'],
                'llm_scored': llm_count,
                'script_fallback': script_count,
            }
        )

    return result


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python score_tc02.py <answers.json> <问答.json> <output_dir>")
        sys.exit(1)

    answers_file = Path(sys.argv[1])
    judge_file = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])

    run_scoring(answers_file, judge_file, output_dir)
