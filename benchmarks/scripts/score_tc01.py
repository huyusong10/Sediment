"""
score_tc01.py — TC-01 概念覆盖率评分脚本（40 分）

读取概念问答结果，通过关键词覆盖率、语义匹配、同义词引用和否定检测评估。
每个概念 0-1 分，总分 100 分后乘以 0.4 得到最终得分。

改进点：
- 精确子串匹配：移除 50% 字符重叠率判断，改为连续子串匹配
- 同义词加分：利用 related_terms 字段，回答提及相关概念时额外加分
- 否定检测：回答包含否定词+概念名时判低分
"""

import json
import re
import sys
from pathlib import Path
from typing import Callable


def extract_key_phrases(text: str) -> list[str]:
    """
    从文本中提取关键短语。
    按标点分割为有意义的短句/词组，保留 2 字以上片段。
    """
    chunks = re.split(r'[，。、；：,.;!?！？\n\r（）()]', text)
    keywords = [c.strip() for c in chunks if len(c.strip()) >= 2]
    # Also extract English words
    english_words = re.findall(r'[a-zA-Z][a-zA-Z0-9_]*', text)
    return keywords + english_words


def _phrase_match_score(phrase: str, answer: str) -> float:
    """
    检查短语是否在答案中出现。
    - 2-4 字符：精确子串匹配
    - >4 字符：检查是否以连续子串形式出现（而非字符集重叠）
    """
    phrase_lower = phrase.lower()
    ans_lower = answer.lower()

    # Short phrases: exact substring match
    if len(phrase_lower) <= 4:
        return 1.0 if phrase_lower in ans_lower else 0.0

    # Long phrases: check if the phrase appears as a continuous substring
    # or if a significant contiguous portion (>= 70%) appears
    if phrase_lower in ans_lower:
        return 1.0

    # Check if any contiguous sub-phrase of length >= 70% of original appears
    min_sub_len = max(int(len(phrase_lower) * 0.7), 3)
    for i in range(len(phrase_lower) - min_sub_len + 1):
        sub = phrase_lower[i:i + min_sub_len]
        if sub in ans_lower:
            return 0.8  # Partial match for long phrases

    return 0.0


def _check_negation(answer: str, concept_name: str) -> bool:
    """
    检测回答是否包含否定表述。
    如果回答中说"概念 不是/不存在/没有/并非"，返回 True。
    """
    negation_patterns = [
        rf'{concept_name}.*?不[是是].*?[的的存有]',
        rf'不[是是].*?{concept_name}',
        rf'{concept_name}.*?(不存在|没有|并非|不属于|不是)',
        rf'(不存在|没有|并非|不属于|不是).*?{concept_name}',
    ]
    for pattern in negation_patterns:
        if re.search(pattern, answer):
            return True
    return False


def score_concept(answer_text: str, concept_name: str, concept_def: dict,
                  all_terms: dict | None = None) -> float:
    """
    评分单个概念问答，返回 0-1 分。
    评分维度：
    1. keyword_coverage (40%): 标准定义中的关键词是否出现在回答中
    2. semantic_match (30%): 回答是否包含概念名并提供定义
    3. no_contradiction (30%): 回答不含明显错误或矛盾
    +  同义词加分 (额外 +0.1，总分不超过 1.0)
    """
    if not answer_text or answer_text.startswith('ERROR'):
        return 0.0

    answer_lower = answer_text.lower()

    # Negation check: if answer negates the concept, penalize heavily
    if _check_negation(answer_text, concept_name):
        return 0.0

    # 1. Keyword coverage: extract key phrases from concept definition
    definition = concept_def.get('definition', '')
    if definition:
        key_phrases = extract_key_phrases(definition)
    else:
        key_phrases = []

    # Always include concept name as a keyword
    if concept_name not in key_phrases:
        key_phrases.insert(0, concept_name)

    if not key_phrases:
        key_phrases = [concept_name]

    matched_phrases = 0
    for phrase in key_phrases:
        matched_phrases += _phrase_match_score(phrase, answer_text)
    keyword_coverage = matched_phrases / len(key_phrases) if key_phrases else 0

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

    # Weighted base score
    score = keyword_coverage * 0.4 + semantic_match * 0.3 + no_contradiction * 0.3

    # Synonym bonus: if answer mentions related concepts with their key features
    synonym_bonus = 0.0
    if all_terms and concept_name in all_terms:
        related = all_terms[concept_name].get('related_terms', [])
        for related_concept in related[:3]:  # Check up to 3 related concepts
            if related_concept in all_terms:
                related_def = all_terms[related_concept].get('definition', '')
                if related_def:
                    # Check if any meaningful phrase from the related concept's definition appears
                    related_phrases = extract_key_phrases(related_def)
                    related_matches = sum(
                        1 for p in related_phrases if _phrase_match_score(p, answer_text) > 0
                    )
                    if related_matches >= 2:  # At least 2 phrases from a related concept
                        synonym_bonus = max(synonym_bonus, 0.05)
                    if related_matches >= 4:
                        synonym_bonus = max(synonym_bonus, 0.1)

    score = min(score + synonym_bonus, 1.0)
    return score


def run_scoring(
    answers_file: Path,
    judge_file: Path,
    output_dir: Path,
    build_type: str | None = None,
    *,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict:
    """Run concept coverage scoring and produce report."""
    with open(judge_file, 'r', encoding='utf-8') as f:
        judge_data = json.load(f)

    with open(answers_file, 'r', encoding='utf-8') as f:
        answers_data = json.load(f)

    answers = {item['concept']: item for item in answers_data.get('results', [])}

    all_terms = judge_data.get('terms', {})
    total_score = 0.0
    details = []
    total_concepts = len(judge_data['terms'])

    if progress_callback:
        progress_callback(
            {
                'phase': 'score_tc01',
                'event': 'score_started',
                'total_questions': total_concepts,
            }
        )

    for concept_name, concept_def in judge_data['terms'].items():
        answer_item = answers.get(concept_name, {})
        answer_text = answer_item.get('answer', '')

        score = score_concept(answer_text, concept_name, concept_def, all_terms)
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
        'total_concepts': total_concepts,
        'answered': sum(1 for d in details if d['has_answer']),
        'zero_score': sum(1 for d in details if d['score'] == 0),
        'full_score': sum(1 for d in details if d['score'] >= 0.99),
        'details': details,
    }

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = f'concept_match_{build_type}.json' if build_type else 'concept_match.json'
    with open(output_dir / output_file, 'w', encoding='utf-8') as f:
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

    if progress_callback:
        progress_callback(
            {
                'phase': 'score_tc01',
                'event': 'score_completed',
                'total_questions': total_concepts,
                'answered': result['answered'],
                'zero_score': result['zero_score'],
                'final_score': result['final_score'],
            }
        )

    return result


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python score_tc01.py <answers.json> <概念.json> <output_dir>")
        sys.exit(1)

    answers_file = Path(sys.argv[1])
    judge_file = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])

    run_scoring(answers_file, judge_file, output_dir)
