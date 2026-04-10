"""
score_tc01.py — TC-01 概念覆盖率评分脚本（40 分）

读取 answers.json 中的概念问答结果，通过关键词覆盖率和语义相似度评估
每个概念 0-1 分，总分 100 分后乘以 0.4 得到最终得分。
"""

import json
import re
import sys
from pathlib import Path


def extract_chinese_keywords(text: str) -> list[str]:
    """
    从中文文本中提取有意义的关键词。
    按标点分割为短句，每个短句作为一个匹配单元。
    匹配时只要短句中超过一半的字符出现在答案中就算匹配成功。
    """
    import re
    # Split by common Chinese punctuation
    chunks = re.split(r'[，。、；：,.;!?！？\n\r（）()]', text)
    keywords = [c.strip() for c in chunks if len(c.strip()) >= 2]
    # Extract English words
    english_words = re.findall(r'[a-zA-Z][a-zA-Z0-9_]*', text)
    return keywords + english_words


def _keyword_match_score(keyword: str, answer: str) -> float:
    """
    检查关键词是否在答案中出现。
    对长关键词（>4字），使用字符重叠率判断：超过50%重叠即算匹配。
    对短关键词（<=4字），使用精确子串匹配。
    """
    kw_lower = keyword.lower()
    ans_lower = answer.lower()

    # Short keywords: exact substring match
    if len(kw_lower) <= 4:
        return 1.0 if kw_lower in ans_lower else 0.0

    # Long keywords: character-level overlap
    kw_chars = set(kw_lower)
    if not kw_chars:
        return 0.0
    ans_chars = set(ans_lower)
    overlap = len(kw_chars & ans_chars) / len(kw_chars)
    return 1.0 if overlap >= 0.5 else 0.0


def score_concept(answer_text: str, concept_name: str, concept_def: dict) -> float:
    """
    评分单个概念问答，返回 0-1 分。
    评分维度：
    1. keyword_coverage (40%): 标准答案/定义中的关键词是否出现在回答中
    2. semantic_match (30%): 回答是否包含概念名并提供定义
    3. no_contradiction (30%): 回答不含明显错误或矛盾
    """
    if not answer_text or answer_text.startswith('ERROR'):
        return 0.0

    answer_lower = answer_text.lower()

    # 1. Keyword coverage: extract keywords from concept definition
    definition = concept_def.get('definition', '')
    if definition:
        # Extract meaningful Chinese keywords
        standard_keywords = extract_chinese_keywords(definition)
    else:
        standard_keywords = []

    if not standard_keywords:
        # Fallback: use concept name itself
        standard_keywords = [concept_name]

    matched_keywords = 0
    for kw in standard_keywords:
        matched_keywords += _keyword_match_score(kw, answer_text)
    keyword_coverage = matched_keywords / len(standard_keywords) if standard_keywords else 0

    # 2. Concept name must appear in answer
    concept_in_answer = concept_name.lower() in answer_lower
    # Check if the answer provides a definition (contains "是" or similar)
    has_definition = any(marker in answer_text for marker in ['是', '指', '用于', '表示', '衡量', '一种'])

    semantic_match = 0.0
    if concept_in_answer and has_definition:
        semantic_match = 1.0
    elif concept_in_answer:
        semantic_match = 0.5
    elif has_definition:
        semantic_match = 0.3

    # 3. Check for obvious contradictions or errors
    error_indicators = ['未找到相关知识', '没有找到', '不清楚', '无法确定', '知识库中不存在']
    has_error = any(indicator in answer_text for indicator in error_indicators)
    no_contradiction = 0.0 if has_error else 1.0

    # Weighted score
    score = keyword_coverage * 0.4 + semantic_match * 0.3 + no_contradiction * 0.3
    return min(score, 1.0)


def run_scoring(answers_file: Path, judge_file: Path, output_dir: Path) -> dict:
    """Run concept coverage scoring and produce report."""
    with open(judge_file, 'r', encoding='utf-8') as f:
        judge_data = json.load(f)

    with open(answers_file, 'r', encoding='utf-8') as f:
        answers_data = json.load(f)

    answers = {item['concept']: item for item in answers_data.get('results', [])}

    total_score = 0.0
    details = []

    for concept_name, concept_def in judge_data['terms'].items():
        answer_item = answers.get(concept_name, {})
        answer_text = answer_item.get('answer', '')

        score = score_concept(answer_text, concept_name, concept_def)
        total_score += score

        details.append({
            'concept': concept_name,
            'definition': concept_def.get('definition', ''),
            'score': round(score, 4),
            'has_answer': bool(answer_text),
            'sources': answer_item.get('sources', []),
        })

    raw_score = total_score  # out of 100
    final_score = raw_score * 0.4  # out of 40

    # Sort by score ascending (worst first)
    details.sort(key=lambda x: x['score'])

    result = {
        'raw_score': round(raw_score, 2),
        'final_score': round(final_score, 2),
        'max_score': 40,
        'total_concepts': len(judge_data['terms']),
        'answered': sum(1 for d in details if d['has_answer']),
        'zero_score': sum(1 for d in details if d['score'] == 0),
        'full_score': sum(1 for d in details if d['score'] >= 0.99),
        'details': details,
    }

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / 'concept_match.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"TC-01 概念覆盖率评分报告")
    print(f"{'='*60}")
    print(f"  总概念数: {result['total_concepts']}")
    print(f"  已回答:   {result['answered']}")
    print(f"  零分:     {result['zero_score']}")
    print(f"  满分:     {result['full_score']}")
    print(f"  原始分:   {result['raw_score']:.1f}/100")
    print(f"  最终得分: {result['final_score']:.1f}/40")
    print(f"\n最低分概念 (Top 10):")
    for d in details[:10]:
        print(f"  {d['concept']}: {d['score']:.3f} | 定义: {d['definition'][:40]}...")

    return result


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python score_tc01.py <answers.json> <概念.json> <output_dir>")
        sys.exit(1)

    answers_file = Path(sys.argv[1])
    judge_file = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])

    run_scoring(answers_file, judge_file, output_dir)
