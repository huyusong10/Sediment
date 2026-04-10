"""
generate_report.py — Sediment 测试报告生成器

读取 testcase/results/ 下的评分结果，生成 HTML 格式的综合报告，包含：
- 分数变化趋势（多轮迭代对比）
- TC-01 概念覆盖率详情（低分概念、零分概念）
- TC-02 问答准确率详情（低分题目、难度分布）
- 各维度评分统计（accuracy, completeness, keyword_coverage, reasoning）

用法：
    python testcase/scripts/generate_report.py
    python testcase/scripts/generate_report.py --output testcase/results/report.html
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SCRIPTS_DIR.parent / 'results'
JUDGE_DIR = SCRIPTS_DIR.parent / 'judge'


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

def load_json(path: Path):
    """Load a JSON file, return None if not found or invalid."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def discover_results() -> list[dict]:
    """
    Discover all scoring results in the results directory.

    Returns a list of result dicts, each containing:
    - label: human-readable label (e.g. '2026-04-10 14:25')
    - tc01: concept coverage scoring data
    - tc02: qa accuracy scoring data
    - scorecard: combined scorecard data
    - concept_answers: raw concept answers (for showing wrong answers)
    - qa_answers: raw qa answers (for showing wrong answers)
    """
    results = []

    # Try to load the standard scorecard.json first
    scorecard = load_json(RESULTS_DIR / 'scorecard.json')
    concept_match = load_json(RESULTS_DIR / 'concept_match.json')
    answers_scored = load_json(RESULTS_DIR / 'answers_scored.json')

    if scorecard or concept_match or answers_scored:
        # Load raw answers for showing wrong answers
        concept_answers = {}
        qa_answers = {}

        # Try standard naming first
        for name in ['full', 'batched', 'test', 'v2', 'v3', 'v4', 'new']:
            ca = load_json(RESULTS_DIR / f'concept_answers_{name}.json')
            if ca and 'results' in ca:
                for item in ca['results']:
                    concept_answers[item.get('concept', '')] = item.get('answer', '')

            qa = load_json(RESULTS_DIR / f'qa_answers_{name}.json')
            if qa and 'results' in qa:
                for item in qa['results']:
                    qa_answers[item.get('id', '')] = item.get('answer', '')

        # Also check the latest concept_answers and qa_answers
        latest_ca = load_json(RESULTS_DIR / 'concept_answers.json')
        if latest_ca and 'results' in latest_ca:
            for item in latest_ca['results']:
                concept_answers[item.get('concept', '')] = item.get('answer', '')

        latest_qa = load_json(RESULTS_DIR / 'qa_answers.json')
        if latest_qa and 'results' in latest_qa:
            for item in latest_qa['results']:
                qa_answers[item.get('id', '')] = item.get('answer', '')

        result = {
            'label': _guess_label(scorecard),
            'tc01': concept_match,
            'tc02': answers_scored,
            'scorecard': scorecard,
            'concept_answers': concept_answers,
            'qa_answers': qa_answers,
        }
        results.append(result)

    # Also discover historical reports from the history directory
    history_dir = RESULTS_DIR / 'history'
    if history_dir.exists():
        for entry in sorted(history_dir.iterdir()):
            if entry.is_dir():
                sc = load_json(entry / 'scorecard.json')
                cm = load_json(entry / 'concept_match.json')
                as_ = load_json(entry / 'answers_scored.json')

                # Load answers from the historical snapshot
                ca = {}
                qa = {}
                for ca_file in entry.glob('concept_answers_*.json'):
                    data = load_json(ca_file)
                    if data and 'results' in data:
                        for item in data['results']:
                            ca[item.get('concept', '')] = item.get('answer', '')
                for qa_file in entry.glob('qa_answers_*.json'):
                    data = load_json(qa_file)
                    if data and 'results' in data:
                        for item in data['results']:
                            qa[item.get('id', '')] = item.get('answer', '')

                if sc or cm or as_:
                    results.insert(0, {  # Historical results come first
                        'label': entry.name,
                        'tc01': cm,
                        'tc02': as_,
                        'scorecard': sc,
                        'concept_answers': ca,
                        'qa_answers': qa,
                    })

    return results


def _guess_label(scorecard: dict | None) -> str:
    """Generate a human-readable label for a result set."""
    if scorecard and 'average_score' in scorecard:
        score = scorecard['average_score']
        return f"当前轮次 (平均分 {score:.1f})"
    return "当前轮次"


# ---------------------------------------------------------------------------
# HTML Generation
# ---------------------------------------------------------------------------

def generate_html(results: list[dict]) -> str:
    """Generate a comprehensive HTML report."""
    # Load judge data for reference
    concepts_judge = load_json(JUDGE_DIR / '概念.json') or {}
    qa_judge = load_json(JUDGE_DIR / '问答.json') or {}

    # Build question lookup
    qa_by_id = {}
    for q in qa_judge.get('questions', []):
        qa_by_id[q['id']] = q

    concepts_by_name = concepts_judge.get('terms', {})

    # Determine the latest result for "current" focus
    current = results[-1] if results else None

    html_parts = []
    html_parts.append(_html_header())

    if current and current['scorecard']:
        sc = current['scorecard']
        avg = sc.get('average_score', 0)
        passed = avg >= 90  # Pass threshold: 90
        html_parts.append(f"""
        <div class="header-card {'passed' if passed else 'failed'}">
            <h1>Sediment 测试报告</h1>
            <div class="score-display">
                <div class="score-circle" style="--score: {avg}%">
                    <span class="score-value">{avg:.1f}</span>
                    <span class="score-max">/100</span>
                </div>
                <div class="score-badge {'passed' if passed else 'failed'}">
                    {'✅ 通过' if passed else '❌ 未通过'}（标准 ≥ 90）
                </div>
            </div>
        </div>
        """)

    # Trend section if multiple results
    if len(results) > 1:
        html_parts.append(_trend_section(results))

    # Current results detail
    if current:
        html_parts.append(_tc01_section(current['tc01'], current.get('concept_answers', {}), concepts_by_name))
        html_parts.append(_tc02_section(current['tc02'], current.get('qa_answers', {}), qa_by_id))

        # Build comparison table if we have scorecard with builds
        if current['scorecard'] and 'builds' in current['scorecard']:
            html_parts.append(_build_comparison_section(current['scorecard']))

    html_parts.append(_html_footer())
    return '\n'.join(html_parts)


def _trend_section(results: list[dict]) -> str:
    """Generate trend comparison section."""
    rows = []
    for r in results:
        sc = r.get('scorecard', {})
        tc01 = r.get('tc01', {})
        tc02 = r.get('tc02', {})

        avg = sc.get('average_score', 0)
        tc01_score = tc01.get('final_score', 0) if tc01 else 0
        tc02_score = tc02.get('final_score', 0) if tc02 else 0

        # Build info from scorecard builds
        build_info = ''
        if 'builds' in sc:
            parts = []
            for btype, bdata in sc['builds'].items():
                label = '全量' if btype == 'full' else '分批'
                total = bdata.get('total', 0)
                parts.append(f'{label}: {total:.1f}')
            build_info = ' | '.join(parts)

        rows.append(f"""
        <tr>
            <td><strong>{r['label']}</strong></td>
            <td>{tc01_score:.1f}<span class="dim">/40</span></td>
            <td>{tc02_score:.1f}<span class="dim">/60</span></td>
            <td><strong>{avg:.1f}</strong></td>
            <td class="dim">{build_info}</td>
        </tr>
        """)

    return f"""
    <div class="section">
        <h2>分数趋势</h2>
        <table class="trend-table">
            <thead>
                <tr>
                    <th>轮次</th>
                    <th>TC-01 概念覆盖率</th>
                    <th>TC-02 问答准确率</th>
                    <th>平均分</th>
                    <th>详情</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """


def _tc01_section(tc01_data: dict, concept_answers: dict, concepts_by_name: dict) -> str:
    """Generate TC-01 concept coverage section."""
    if not tc01_data:
        return '<div class="section"><h2>TC-01 概念覆盖率</h2><p class="dim">暂无数据</p></div>'

    raw = tc01_data.get('raw_score', 0)
    final = tc01_data.get('final_score', 0)
    total = tc01_data.get('total_concepts', 0)
    answered = tc01_data.get('answered', 0)
    zero = tc01_data.get('zero_score', 0)
    full = tc01_data.get('full_score', 0)
    details = tc01_data.get('details', [])

    # Low score concepts (score < 0.7)
    low_concepts = [d for d in details if d['score'] < 0.7]

    rows = []
    for d in low_concepts[:20]:  # Top 20 worst
        concept = d['concept']
        score = d['score']
        definition = d.get('definition', '')
        answer = concept_answers.get(concept, '')
        related = concepts_by_name.get(concept, {}).get('related_terms', [])

        score_class = 'score-zero' if score == 0 else 'score-low' if score < 0.5 else 'score-mid'

        answer_display = _truncate(answer, 200) if answer else '<span class="dim">无回答</span>'

        rows.append(f"""
        <tr>
            <td><strong>{concept}</strong></td>
            <td><span class="score-tag {score_class}">{score:.2f}</span></td>
            <td class="dim">{definition[:60]}{'...' if len(definition) > 60 else ''}</td>
            <td class="answer-cell">{answer_display}</td>
        </tr>
        """)

    return f"""
    <div class="section">
        <h2>TC-01 概念覆盖率 <span class="dim">({final:.1f}/40, 原始分 {raw:.1f}/100)</span></h2>
        <div class="stats-row">
            <div class="stat-card">
                <span class="stat-value">{total}</span>
                <span class="stat-label">总概念数</span>
            </div>
            <div class="stat-card">
                <span class="stat-value">{answered}</span>
                <span class="stat-label">已回答</span>
            </div>
            <div class="stat-card">
                <span class="stat-value">{full}</span>
                <span class="stat-label">满分</span>
            </div>
            <div class="stat-card">
                <span class="stat-value">{zero}</span>
                <span class="stat-label">零分</span>
            </div>
        </div>

        <details>
            <summary>低分概念详情 (Top {len(low_concepts[:20])}, 分数 &lt; 0.7)</summary>
            <table class="detail-table">
                <thead>
                    <tr>
                        <th>概念</th>
                        <th>得分</th>
                        <th>标准定义</th>
                        <th>系统回答</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
        </details>
    </div>
    """


def _tc02_section(tc02_data: dict, qa_answers: dict, qa_by_id: dict) -> str:
    """Generate TC-02 QA accuracy section."""
    if not tc02_data:
        return '<div class="section"><h2>TC-02 问答准确率</h2><p class="dim">暂无数据</p></div>'

    total_earned = tc02_data.get('total_earned', 0)
    total_max = tc02_data.get('total_max', 0)
    final = tc02_data.get('final_score', 0)
    total_q = tc02_data.get('total_questions', 0)
    answered = tc02_data.get('answered', 0)
    zero = tc02_data.get('zero_score', 0)
    by_difficulty = tc02_data.get('by_difficulty', {})
    details = tc02_data.get('details', [])
    scoring_method = tc02_data.get('scoring_method', {})

    # Low score questions
    low_qs = [d for d in details if d['earned'] < d.get('max_points', 0.6) * 0.5]

    rows = []
    for d in low_qs[:20]:  # Top 20 worst
        qid = d['id']
        q_info = qa_by_id.get(qid, {})
        question = d.get('question', q_info.get('question', ''))
        difficulty = d.get('difficulty', 'medium')
        earned = d.get('earned', 0)
        max_pts = d.get('max_points', 0)
        answer = qa_answers.get(qid, '')
        standard = q_info.get('standard_answer', '')
        method = d.get('method', '')

        score_class = 'score-zero' if earned == 0 else 'score-low' if earned < max_pts * 0.5 else 'score-mid'
        diff_class = f'difficulty-{difficulty}'

        answer_display = _truncate(answer, 200) if answer else '<span class="dim">无回答</span>'
        standard_display = _truncate(standard, 150)

        rows.append(f"""
        <tr>
            <td><span class="diff-tag {diff_class}">{difficulty}</span> <strong>Q{qid}</strong></td>
            <td>{question[:60]}{'...' if len(question) > 60 else ''}</td>
            <td><span class="score-tag {score_class}">{earned:.2f}/{max_pts:.2f}</span></td>
            <td class="dim">{method or '-'}</td>
            <td class="answer-cell">
                <details>
                    <summary>查看</summary>
                    <div class="qa-comparison">
                        <div class="qa-std"><strong>标准答案:</strong> {standard_display}</div>
                        <div class="qa-ans"><strong>系统回答:</strong> {answer_display}</div>
                    </div>
                </details>
            </td>
        </tr>
        """)

    # Difficulty breakdown
    diff_rows = []
    for diff, stats in by_difficulty.items():
        earned = stats.get('earned', 0)
        max_val = stats.get('max', 0)
        count = stats.get('count', 0)
        pct = (earned / max_val * 100) if max_val > 0 else 0
        bar_width = min(pct, 100)
        diff_rows.append(f"""
        <tr>
            <td><span class="diff-tag difficulty-{diff}">{diff}</span></td>
            <td>{count} 题</td>
            <td>
                <div class="bar-container">
                    <div class="bar" style="width: {bar_width}%"></div>
                </div>
            </td>
            <td>{earned:.1f}<span class="dim">/{max_val:.1f}</span></td>
            <td>{pct:.1f}%</td>
        </tr>
        """)

    scoring_info = ''
    if scoring_method:
        llm = scoring_method.get('llm_scored', 0)
        script = scoring_method.get('script_fallback', 0)
        if llm or script:
            scoring_info = f'<p class="dim">评分方式: LLM={llm} 题, 脚本 fallback={script} 题</p>'

    return f"""
    <div class="section">
        <h2>TC-02 问答准确率 <span class="dim">({final:.1f}/60, 原始分 {total_earned:.1f}/{total_max:.1f})</span></h2>
        {scoring_info}
        <div class="stats-row">
            <div class="stat-card">
                <span class="stat-value">{total_q}</span>
                <span class="stat-label">总题数</span>
            </div>
            <div class="stat-card">
                <span class="stat-value">{answered}</span>
                <span class="stat-label">已回答</span>
            </div>
            <div class="stat-card">
                <span class="stat-value">{zero}</span>
                <span class="stat-label">零分</span>
            </div>
        </div>

        <h3>难度分布</h3>
        <table class="detail-table">
            <thead>
                <tr>
                    <th>难度</th>
                    <th>题数</th>
                    <th>得分率</th>
                    <th>得分</th>
                    <th>百分比</th>
                </tr>
            </thead>
            <tbody>
                {''.join(diff_rows)}
            </tbody>
        </table>

        <details>
            <summary>低分题目详情 (Top {len(low_qs[:20])}, 得分 &lt; 50%)</summary>
            <table class="detail-table">
                <thead>
                    <tr>
                        <th>题目</th>
                        <th>问题</th>
                        <th>得分</th>
                        <th>评分方式</th>
                        <th>回答对比</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
        </details>
    </div>
    """


def _build_comparison_section(scorecard: dict) -> str:
    """Generate build comparison section."""
    builds = scorecard.get('builds', {})
    if len(builds) < 2:
        return ''

    rows = []
    for btype, bdata in builds.items():
        label = '全量构建' if btype == 'full' else '分批构建'
        tc01 = bdata.get('tc01', 0)
        tc02 = bdata.get('tc02', 0)
        total = bdata.get('total', 0)
        error = bdata.get('error')

        rows.append(f"""
        <tr>
            <td><strong>{label}</strong></td>
            <td>{tc01:.1f}<span class="dim">/40</span></td>
            <td>{tc02:.1f}<span class="dim">/60</span></td>
            <td><strong>{total:.1f}</strong></td>
            <td class="dim">{error or '-'}</td>
        </tr>
        """)

    return f"""
    <div class="section">
        <h2>构建方式对比</h2>
        <table class="detail-table">
            <thead>
                <tr>
                    <th>构建方式</th>
                    <th>TC-01 (40分)</th>
                    <th>TC-02 (60分)</th>
                    <th>总分</th>
                    <th>错误</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

def _html_header() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sediment 测试报告</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
                         'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            background: #f5f5f5;
            color: #1a1a1a;
            line-height: 1.6;
            padding: 2rem;
        }
        .container { max-width: 1200px; margin: 0 auto; }

        /* Header card */
        .header-card {
            background: white;
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            text-align: center;
        }
        .header-card.passed { border-left: 4px solid #22c55e; }
        .header-card.failed { border-left: 4px solid #ef4444; }
        .header-card h1 { font-size: 1.5rem; margin-bottom: 1rem; }

        .score-display {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 1.5rem;
        }
        .score-circle {
            width: 100px;
            height: 100px;
            border-radius: 50%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            border: 6px solid;
            border-color: color-mix(in srgb, currentColor 80%, transparent);
        }
        .passed .score-circle { color: #22c55e; }
        .failed .score-circle { color: #ef4444; }
        .score-value { font-size: 2rem; line-height: 1; }
        .score-max { font-size: 0.85rem; font-weight: 400; opacity: 0.6; }
        .score-badge {
            font-size: 1.1rem;
            font-weight: 600;
            padding: 0.5rem 1rem;
            border-radius: 8px;
        }
        .score-badge.passed { background: #dcfce7; color: #166534; }
        .score-badge.failed { background: #fef2f2; color: #991b1b; }

        /* Section */
        .section {
            background: white;
            border-radius: 12px;
            padding: 1.5rem 2rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .section h2 {
            font-size: 1.2rem;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #eee;
        }
        .section h3 {
            font-size: 1rem;
            margin: 1rem 0 0.5rem;
            color: #555;
        }

        /* Stats row */
        .stats-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        .stat-card {
            background: #f8f8f8;
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
        }
        .stat-value { font-size: 1.8rem; font-weight: 700; display: block; }
        .stat-label { font-size: 0.8rem; color: #666; display: block; margin-top: 0.25rem; }

        /* Score tags */
        .score-tag {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.85rem;
            font-weight: 600;
        }
        .score-zero { background: #fee2e2; color: #991b1b; }
        .score-low { background: #fef3c7; color: #92400e; }
        .score-mid { background: #dbeafe; color: #1e40af; }

        /* Difficulty tags */
        .diff-tag {
            display: inline-block;
            padding: 1px 6px;
            border-radius: 3px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-right: 4px;
        }
        .difficulty-easy { background: #dcfce7; color: #166534; }
        .difficulty-medium { background: #dbeafe; color: #1e40af; }
        .difficulty-hard { background: #fef3c7; color: #92400e; }

        /* Tables */
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }
        th {
            text-align: left;
            padding: 0.5rem 0.75rem;
            background: #f8f8f8;
            font-weight: 600;
            color: #555;
            border-bottom: 2px solid #eee;
        }
        td {
            padding: 0.5rem 0.75rem;
            border-bottom: 1px solid #f0f0f0;
            vertical-align: top;
        }
        tr:hover { background: #fafafa; }

        .trend-table { font-size: 0.9rem; }
        .detail-table { font-size: 0.85rem; }

        .answer-cell {
            max-width: 300px;
            font-size: 0.85rem;
            color: #444;
        }

        /* Bar chart */
        .bar-container {
            background: #eee;
            border-radius: 4px;
            height: 20px;
            width: 150px;
            overflow: hidden;
        }
        .bar {
            height: 100%;
            background: linear-gradient(90deg, #3b82f6, #22c55e);
            border-radius: 4px;
            transition: width 0.3s;
        }

        /* Utilities */
        .dim { color: #888; font-size: 0.85rem; }

        /* Details */
        details { margin-top: 0.5rem; }
        details summary {
            cursor: pointer;
            padding: 0.5rem;
            background: #f8f8f8;
            border-radius: 6px;
            font-weight: 500;
            user-select: none;
        }
        details summary:hover { background: #f0f0f0; }
        details[open] summary { border-radius: 6px 6px 0 0; }

        /* QA comparison */
        .qa-comparison {
            padding: 0.75rem;
            background: #fafafa;
            border-radius: 6px;
            margin-top: 0.25rem;
            font-size: 0.85rem;
        }
        .qa-std { margin-bottom: 0.5rem; padding-bottom: 0.5rem; border-bottom: 1px dashed #ddd; }
        .qa-std strong { color: #166534; }
        .qa-ans strong { color: #1e40af; }

        /* Footer */
        .footer {
            text-align: center;
            padding: 2rem;
            color: #888;
            font-size: 0.85rem;
        }
    </style>
</head>
<body>
<div class="container">
"""


def _html_footer() -> str:
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    return f"""
    <div class="footer">
        <p>报告生成时间: {now}</p>
        <p>Sediment 测试方案 — 目标分数 ≥ 90/100</p>
    </div>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int) -> str:
    """Truncate text and escape HTML."""
    if not text:
        return ''
    # Escape HTML
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    if len(text) > max_len:
        return text[:max_len] + '...'
    return text


# ---------------------------------------------------------------------------
# Archive Management
# ---------------------------------------------------------------------------

def archive_current_results() -> Path | None:
    """
    Move current results to history directory with a timestamp label.
    Returns the history entry path, or None if nothing to archive.
    """
    # Check if there's anything to archive
    has_data = False
    for f in ['scorecard.json', 'concept_match.json', 'answers_scored.json']:
        if (RESULTS_DIR / f).exists():
            has_data = True
            break

    if not has_data:
        return None

    history_dir = RESULTS_DIR / 'history'
    history_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamped entry
    ts = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    entry = history_dir / ts
    entry.mkdir(parents=True, exist_ok=True)

    # Copy relevant files
    import shutil
    for f in RESULTS_DIR.iterdir():
        if f.is_file() and f.name not in ('scorecard.md',):
            shutil.copy2(f, entry / f.name)

    return entry


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_report_from_results(results_dir: Path, all_results: dict):
    """
    Generate HTML report directly from run_all_scores.py results.
    This is called by run_all_scores.py after scoring is complete.
    """
    global RESULTS_DIR, JUDGE_DIR
    RESULTS_DIR = results_dir
    JUDGE_DIR = RESULTS_DIR.parent / 'judge'

    # Archive current results to history
    archive_current_results()

    # Discover all results (including historical)
    results = discover_results()

    if not results:
        return

    # Generate HTML
    html = generate_html(results)

    # Write output
    output_path = RESULTS_DIR / 'report.html'
    output_path.write_text(html, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Sediment HTML Report Generator')
    parser.add_argument('--output', type=str, default=None, help='Output HTML file path')
    parser.add_argument('--no-archive', action='store_true', help='Do not archive current results to history')
    args = parser.parse_args()

    # Archive current results to history before generating new report
    if not args.no_archive:
        archived = archive_current_results()
        if archived:
            print(f"[report] Archived current results to history: {archived.name}")

    # Discover all results (including historical)
    results = discover_results()

    if not results:
        print("[report] No scoring results found in results directory.")
        print("[report] Run `python testcase/scripts/run_all_scores.py` first.")
        sys.exit(1)

    print(f"[report] Found {len(results)} result set(s)")

    # Generate HTML
    html = generate_html(results)

    # Write output
    output_path = Path(args.output) if args.output else RESULTS_DIR / 'report.html'
    output_path.write_text(html, encoding='utf-8')
    print(f"[report] Report written to: {output_path}")


if __name__ == '__main__':
    main()
