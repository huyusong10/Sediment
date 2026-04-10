"""
score_tc02.py — TC-02 问答准确率评分脚本（60 分）

读取 answers.json 中的问答结果，通过多维度评估每题质量：
- accuracy: 回答是否准确传达了标准答案的核心意思
- completeness: 是否覆盖了标准答案的主要要点
- keyword_coverage: 是否包含预期关键词
- reasoning: 回答是否展现了合理的推理链条（medium/hard 题额外关注）

每题得分 = 综合评分 × 该题满分值
"""

import json
import sys
from pathlib import Path


def score_question(answer_text: str, question: dict) -> dict:
    """
    评分单个问答，返回各维度分数和总分。
    """
    if not answer_text or answer_text.startswith('ERROR'):
        return {
            'accuracy': 0, 'completeness': 0, 'keyword_coverage': 0,
            'reasoning': 0, 'composite': 0, 'earned': 0,
        }

    difficulty = question.get('difficulty', 'medium')
    standard_answer = question.get('standard_answer', '')
    expected_keywords = question.get('expected_keywords', [])

    answer_lower = answer_text.lower()
    standard_lower = standard_answer.lower()

    # 1. Keyword coverage: how many expected keywords appear in answer
    kw_matched = 0
    for kw in expected_keywords:
        if kw.lower() in answer_lower:
            kw_matched += 1
    keyword_coverage = kw_matched / len(expected_keywords) if expected_keywords else 0

    # 2. Accuracy: token-overlap between answer and standard answer
    # Use Chinese character bigrams + English words for more robust matching
    import re
    def extract_tokens(text):
        """Extract Chinese char bigrams and English words."""
        chars = re.findall(r'[\u4e00-\u9fff]', text)
        bigrams = set()
        for i in range(len(chars) - 1):
            bigrams.add(chars[i] + chars[i + 1])
        words = set(re.findall(r'[a-zA-Z][a-zA-Z0-9]*', text.lower()))
        return bigrams | words

    standard_tokens = extract_tokens(standard_answer)
    answer_tokens = extract_tokens(answer_text)
    if standard_tokens:
        overlap = len(standard_tokens & answer_tokens)
        accuracy = overlap / len(standard_tokens)
    else:
        accuracy = 0
    # Boost if at least half the key content is covered
    if accuracy > 0.5:
        accuracy = min(accuracy * 1.2, 1.0)

    # 3. Completeness: check coverage of standard answer's meaningful chunks
    # Split by punctuation and check how many chunks are partially covered
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

    # 4. Reasoning depth: for medium/hard, check if answer has explanatory depth
    reasoning = 0.0
    if difficulty in ('medium', 'hard'):
        # Indicators of reasoning depth
        reasoning_markers = [
            '因为', '所以', '因此', '导致', '原因', '机制', '过程',
            '当', '如果', '则', '从而', '进而', '意味着', '说明',
            '分为', '包括', '涉及', '需要', '通常',
        ]
        marker_count = sum(1 for m in reasoning_markers if m in answer_text)
        # Also consider answer length as a proxy for depth
        length_score = min(len(answer_text) / 200, 1.0)
        reasoning = (min(marker_count / 3, 1.0) * 0.5 + length_score * 0.5)

    # Compute composite score based on difficulty weights
    if difficulty == 'easy':
        composite = accuracy * 0.4 + completeness * 0.3 + keyword_coverage * 0.3
    elif difficulty == 'medium':
        composite = accuracy * 0.3 + completeness * 0.3 + keyword_coverage * 0.3 + reasoning * 0.1
    else:  # hard
        composite = accuracy * 0.25 + completeness * 0.25 + keyword_coverage * 0.25 + reasoning * 0.25

    # Max points for this question based on difficulty
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
    }


def run_scoring(answers_file: Path, judge_file: Path, output_dir: Path) -> dict:
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
    total_earned = 0.0
    total_max = 0.0
    details = []

    by_difficulty = {'easy': {'earned': 0, 'max': 0, 'count': 0},
                     'medium': {'earned': 0, 'max': 0, 'count': 0},
                     'hard': {'earned': 0, 'max': 0, 'count': 0}}

    for q in questions:
        qid = q['id']
        answer_item = answers.get(qid, {})
        answer_text = answer_item.get('answer', '')

        result = score_question(answer_text, q)
        total_earned += result['earned']
        difficulty_max = {'easy': 0.3, 'medium': 0.6, 'hard': 0.69}
        total_max += difficulty_max.get(q['difficulty'], 0.6)

        diff = q['difficulty']
        by_difficulty[diff]['earned'] += result['earned']
        by_difficulty[diff]['max'] += difficulty_max.get(diff, 0.6)
        by_difficulty[diff]['count'] += 1

        details.append({
            'id': qid,
            'question': q['question'][:50],
            'difficulty': diff,
            'earned': result['earned'],
            'max_points': result['max_points'],
            'composite': result['composite'],
            'sources': answer_item.get('sources', []),
        })

    # Max score is 60
    final_score = (total_earned / total_max * 60) if total_max > 0 else 0

    # Sort by score ascending (worst first)
    details.sort(key=lambda x: x['earned'])

    result = {
        'total_earned': round(total_earned, 2),
        'total_max': round(total_max, 2),
        'final_score': round(final_score, 2),
        'max_score': 60,
        'total_questions': len(questions),
        'answered': sum(1 for d in details if d['composite'] > 0),
        'zero_score': sum(1 for d in details if d['earned'] == 0),
        'by_difficulty': {k: {mk: round(mv, 2) if isinstance(mv, float) else mv
                               for mk, mv in v.items()}
                          for k, v in by_difficulty.items()},
        'details': details,
    }

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / 'answers_scored.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"TC-02 问答准确率评分报告")
    print(f"{'='*60}")
    print(f"  总题数:   {result['total_questions']}")
    print(f"  已回答:   {result['answered']}")
    print(f"  零分:     {result['zero_score']}")
    print(f"  原始分:   {result['total_earned']:.2f}/{result['total_max']:.2f}")
    print(f"  最终得分: {result['final_score']:.1f}/60")
    print(f"\n按难度统计:")
    for diff, stats in by_difficulty.items():
        pct = stats['earned'] / stats['max'] * 100 if stats['max'] > 0 else 0
        print(f"  {diff}: {stats['earned']:.1f}/{stats['max']:.1f} ({pct:.1f}%) | {stats['count']}题")
    print(f"\n最低分题目 (Top 10):")
    for d in details[:10]:
        print(f"  Q{d['id']} [{d['difficulty']}]: {d['earned']:.3f}/{d['max_points']:.3f} | {d['question']}")

    return result


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python score_tc02.py <answers.json> <问答.json> <output_dir>")
        sys.exit(1)

    answers_file = Path(sys.argv[1])
    judge_file = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])

    run_scoring(answers_file, judge_file, output_dir)
