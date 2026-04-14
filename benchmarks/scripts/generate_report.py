"""
generate_report.py — Sediment 测试报告生成器

读取 testcase/results/ 下的评分结果，生成 HTML 格式的综合报告，包含：
- 分数变化趋势（多轮迭代对比）
- TC-01 概念覆盖率详情（低分概念、零分概念）
- TC-02 问答准确率详情（低分题目、难度分布）
- 各维度评分统计（accuracy, completeness, keyword_coverage, reasoning）

用法：
    python benchmarks/scripts/generate_report.py
    python benchmarks/scripts/generate_report.py --output testcase/results/reports/report.html
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from harness_contract import load_benchmark_paths

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PATHS = load_benchmark_paths()
SCRIPTS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = PATHS.results_dir
BUILDS_DIR = PATHS.builds_dir
REPORTS_DIR = PATHS.reports_dir
JUDGE_DIR = PATHS.judge_dir
PASS_THRESHOLD = 90


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


def load_build_diagnostics(build_dir: Path, build_type: str) -> dict | None:
    return load_json(build_dir / f'kb_diagnostics_{build_type}.json')


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
    scorecard = load_json(REPORTS_DIR / 'scorecard.json')
    # Legacy: load shared scoring files (last build wins — only used if no per-build files exist)
    concept_match = load_json(RESULTS_DIR / 'concept_match.json')
    answers_scored = load_json(RESULTS_DIR / 'answers_scored.json')

    if scorecard and scorecard.get('builds'):
        # Create a separate result entry for each build type
        for build_type in ['full', 'batched']:
            if build_type not in scorecard['builds']:
                continue
            bdata = scorecard['builds'][build_type]
            if bdata.get('error'):
                continue

            build_dir = BUILDS_DIR / build_type
            build_tc01 = load_json(build_dir / f'concept_match_{build_type}.json') or concept_match
            build_tc02 = load_json(build_dir / f'answers_scored_{build_type}.json') or answers_scored

            concept_answers = {}
            qa_answers = {}
            ca_file = load_json(build_dir / f'concept_answers_{build_type}.json')
            if ca_file and 'results' in ca_file:
                for item in ca_file['results']:
                    concept_answers[item.get('concept', '')] = item.get('answer', '')
            qa_file = load_json(build_dir / f'qa_answers_{build_type}.json')
            if qa_file and 'results' in qa_file:
                for item in qa_file['results']:
                    qa_answers[item.get('id', '')] = item.get('answer', '')
            kb_diagnostics = load_build_diagnostics(build_dir, build_type)

            label = '全量构建' if build_type == 'full' else '分批构建'
            total = bdata.get('total', 0)
            results.append({
                'label': f'{label} (得分 {total:.1f})',
                'tc01': build_tc01,
                'tc02': build_tc02,
                'scorecard': scorecard,
                'concept_answers': concept_answers,
                'qa_answers': qa_answers,
                'kb_diagnostics': kb_diagnostics,
            })
    elif BUILDS_DIR.exists():
        for build_type in ['full', 'batched']:
            build_dir = BUILDS_DIR / build_type
            if not build_dir.exists():
                continue
            build_tc01 = load_json(build_dir / f'concept_match_{build_type}.json')
            build_tc02 = load_json(build_dir / f'answers_scored_{build_type}.json')
            if build_tc01 is None and build_tc02 is None:
                continue

            concept_answers = {}
            qa_answers = {}
            ca_file = load_json(build_dir / f'concept_answers_{build_type}.json')
            if ca_file and 'results' in ca_file:
                for item in ca_file['results']:
                    concept_answers[item.get('concept', '')] = item.get('answer', '')
            qa_file = load_json(build_dir / f'qa_answers_{build_type}.json')
            if qa_file and 'results' in qa_file:
                for item in qa_file['results']:
                    qa_answers[item.get('id', '')] = item.get('answer', '')
            kb_diagnostics = load_build_diagnostics(build_dir, build_type)

            label = '全量构建' if build_type == 'full' else '分批构建'
            total = 0.0
            if build_tc01 and build_tc02:
                total = round(build_tc01.get('final_score', 0) + build_tc02.get('final_score', 0), 1)
            results.append({
                'label': f'{label} (得分 {total:.1f})',
                'tc01': build_tc01,
                'tc02': build_tc02,
                'scorecard': None,
                'concept_answers': concept_answers,
                'qa_answers': qa_answers,
                'kb_diagnostics': kb_diagnostics,
            })
    elif concept_match or answers_scored:
        # Fallback: no scorecard, only shared scoring files
        concept_answers = {}
        qa_answers = {}
        latest_ca = load_json(RESULTS_DIR / 'concept_answers.json')
        if latest_ca and 'results' in latest_ca:
            for item in latest_ca['results']:
                concept_answers[item.get('concept', '')] = item.get('answer', '')
        latest_qa = load_json(RESULTS_DIR / 'qa_answers.json')
        if latest_qa and 'results' in latest_qa:
            for item in latest_qa['results']:
                qa_answers[item.get('id', '')] = item.get('answer', '')

        results.append({
            'label': '当前轮次',
            'tc01': concept_match,
            'tc02': answers_scored,
            'scorecard': None,
            'concept_answers': concept_answers,
            'qa_answers': qa_answers,
            'kb_diagnostics': None,
        })

    # Also discover historical reports from the history directory
    history_dir = RESULTS_DIR / 'history'
    if history_dir.exists():
        for entry in sorted(history_dir.iterdir()):
            if entry.is_dir():
                history_reports_dir = entry / 'reports'
                history_builds_dir = entry / 'builds'
                sc = load_json(history_reports_dir / 'scorecard.json') or load_json(entry / 'scorecard.json')
                cm = load_json(entry / 'concept_match.json')
                as_ = load_json(entry / 'answers_scored.json')

                # Also check for per-build historical scoring files
                cm_full = load_json((history_builds_dir / 'full') / 'concept_match_full.json') or load_json(entry / 'concept_match_full.json') or cm
                cm_batched = load_json((history_builds_dir / 'batched') / 'concept_match_batched.json') or load_json(entry / 'concept_match_batched.json') or cm
                as_full = load_json((history_builds_dir / 'full') / 'answers_scored_full.json') or load_json(entry / 'answers_scored_full.json') or as_
                as_batched = load_json((history_builds_dir / 'batched') / 'answers_scored_batched.json') or load_json(entry / 'answers_scored_batched.json') or as_

                # Load answers from the historical snapshot
                ca = {}
                qa = {}
                for ca_file in list(entry.glob('concept_answers_*.json')) + list(history_builds_dir.glob('*/concept_answers_*.json')):
                    data = load_json(ca_file)
                    if data and 'results' in data:
                        for item in data['results']:
                            ca[item.get('concept', '')] = item.get('answer', '')
                for qa_file in list(entry.glob('qa_answers_*.json')) + list(history_builds_dir.glob('*/qa_answers_*.json')):
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
                        'kb_diagnostics': None,
                    })

    return results


def _guess_label(scorecard: dict | None) -> str:
    """Generate a human-readable label for a result set."""
    if scorecard and 'average_score' in scorecard:
        score = scorecard['average_score']
        return f"当前轮次 (平均分 {score:.1f})"
    return "当前轮次"


# ---------------------------------------------------------------------------
# HTML Generation — Per-Build Report
# ---------------------------------------------------------------------------

def generate_html_for_build(build_type: str, tc01_data: dict, tc02_data: dict,
                            scorecard: dict, concept_answers: dict, qa_answers: dict,
                            kb_diagnostics: dict | None,
                            qa_judge: dict, concepts_judge: dict, timestamp: str) -> str:
    """Generate a complete HTML report for a single build type."""
    qa_by_id = {}
    for q in qa_judge.get('questions', []):
        qa_by_id[q['id']] = q
    concepts_by_name = concepts_judge.get('terms', {})

    label = '全量构建' if build_type == 'full' else '分批构建'
    avg = scorecard.get('average_score', 0)
    build_info = scorecard.get('builds', {}).get(build_type, {})
    build_score = build_info.get('total', 0)
    passed = build_score >= PASS_THRESHOLD

    started = build_info.get('started_at', '')
    finished = build_info.get('finished_at', '')
    duration = build_info.get('duration_seconds', 0)

    html = [_html_header()]

    # Header
    html.append(f"""
    <div class="header-card {'passed' if passed else 'failed'}">
        <h1>Sediment 测试报告 — {label}</h1>
        <div class="meta-row">
            <span>生成时间: {timestamp}</span>
        </div>
        {f'<div class="meta-row"><span>构建开始: {started}</span></div>' if started else ''}
        {f'<div class="meta-row"><span>构建结束: {finished}</span></div>' if finished else ''}
        {f'<div class="meta-row"><span>耗时: {duration:.0f} 秒</span></div>' if duration else ''}
        <div class="score-display">
            <div class="score-circle" style="color: {'#22c55e' if passed else '#ef4444'}">
                <span class="score-value">{build_score:.1f}</span>
                <span class="score-max">/100</span>
            </div>
            <div class="score-badge {'passed' if passed else 'failed'}">
                {'通过' if passed else '未通过'}（标准 ≥ {PASS_THRESHOLD}）
            </div>
        </div>
        <div class="score-breakdown">
            <div class="bd-card">
                <div class="bd-label">TC-01 概念覆盖率</div>
                <div class="bd-value">{build_info.get('tc01', 0):.1f}<span class="bd-max">/40</span></div>
            </div>
            <div class="bd-card">
                <div class="bd-label">TC-02 问答准确率</div>
                <div class="bd-value">{build_info.get('tc02', 0):.1f}<span class="bd-max">/60</span></div>
            </div>
        </div>
    </div>
    """)

    html.append(_kb_diagnostics_section(kb_diagnostics, build_info))

    # TC-01 Full
    html.append(_tc01_full_section(tc01_data, concept_answers, concepts_by_name))

    # TC-02 Full
    html.append(_tc02_full_section(tc02_data, qa_answers, qa_by_id))

    html.append(_html_footer())
    return '\n'.join(html)


def _tc01_full_section(tc01_data: dict, concept_answers: dict, concepts_by_name: dict) -> str:
    """Generate full TC-01 section with ALL concepts sorted by score ascending."""
    if not tc01_data:
        return _empty_section('TC-01 概念覆盖率')

    raw = tc01_data.get('raw_score', 0)
    final = tc01_data.get('final_score', 0)
    total = tc01_data.get('total_concepts', 0)
    answered = tc01_data.get('answered', 0)
    zero = tc01_data.get('zero_score', 0)
    full = tc01_data.get('full_score', 0)
    details = tc01_data.get('details', [])

    rows = []
    for d in details:  # Already sorted by score ascending from scorer
        concept = d['concept']
        score = d['score']
        definition = d.get('definition', '')
        answer = concept_answers.get(concept, '')
        score_class = _score_class(score, 1.0)
        has_answer = d.get('has_answer', False)

        rows.append(f"""
        <tr>
            <td class="concept-name"><strong>{_esc(concept)}</strong></td>
            <td class="score-cell"><span class="score-tag {score_class}">{score:.2f}</span></td>
            <td class="def-cell"><details><summary>{_truncate_html(definition, 80)}</summary>{_esc(definition)}</details></td>
            <td class="ans-cell"><details><summary>{_truncate_html(answer, 100) if answer else '<span class=\"dim\">无回答</span>'}</summary>{_esc(answer)}</details></td>
        </tr>
        """)

    return f"""
    <div class="section">
        <h2>TC-01 概念覆盖率 <span class="dim">({final:.1f}/40, 原始分 {raw:.1f}/100)</span></h2>
        <div class="stats-row">
            <div class="stat-card"><span class="stat-value">{total}</span><span class="stat-label">总概念数</span></div>
            <div class="stat-card"><span class="stat-value">{answered}</span><span class="stat-label">已回答</span></div>
            <div class="stat-card"><span class="stat-value">{full}</span><span class="stat-label">满分</span></div>
            <div class="stat-card"><span class="stat-value">{zero}</span><span class="stat-label">零分</span></div>
        </div>
        <table class="full-table">
            <thead>
                <tr>
                    <th class="col-concept">概念</th>
                    <th class="col-score">得分</th>
                    <th class="col-def">标准定义</th>
                    <th class="col-ans">系统回答</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """


def _kb_diagnostics_section(kb_diagnostics: dict | None, build_info: dict) -> str:
    if not kb_diagnostics:
        return _empty_section('KB 诊断')

    placeholder_summary = kb_diagnostics.get('placeholder_ref_summary', {})
    top_placeholders = kb_diagnostics.get('top_placeholders', [])
    orphan_entries = kb_diagnostics.get('orphan_entries', [])
    dangling_links = kb_diagnostics.get('dangling_links', [])
    isolated_dir = build_info.get('isolated_dir', '')

    placeholder_rows = ''.join(
        f"<tr><td>{_esc(item.get('placeholder', ''))}</td><td>{item.get('ref_count', 0)}</td></tr>"
        for item in top_placeholders[:10]
    ) or '<tr><td colspan="2" class="dim">无高价值占位符</td></tr>'

    orphan_rows = ''.join(
        f"<tr><td>{_esc(item)}</td></tr>" for item in orphan_entries[:10]
    ) or '<tr><td class="dim">无孤立条目</td></tr>'

    dangling_rows = ''.join(
        f"<tr><td>{_esc(item.get('link', ''))}</td><td>{_esc(item.get('source_file', ''))}</td></tr>"
        for item in dangling_links[:10]
    ) or '<tr><td colspan="2" class="dim">无悬空链接</td></tr>'

    return f"""
    <div class="section">
        <h2>KB 诊断</h2>
        <div class="stats-row">
            <div class="stat-card"><span class="stat-value">{kb_diagnostics.get('entry_count', 0)}</span><span class="stat-label">正式条目</span></div>
            <div class="stat-card"><span class="stat-value">{kb_diagnostics.get('placeholder_count', 0)}</span><span class="stat-label">占位条目</span></div>
            <div class="stat-card"><span class="stat-value">{kb_diagnostics.get('avg_entry_size', 0)}</span><span class="stat-label">平均条目大小</span></div>
            <div class="stat-card"><span class="stat-value">{kb_diagnostics.get('orphan_entry_count', 0)}</span><span class="stat-label">孤立条目</span></div>
            <div class="stat-card"><span class="stat-value">{kb_diagnostics.get('dangling_link_count', 0)}</span><span class="stat-label">悬空链接</span></div>
            <div class="stat-card"><span class="stat-value">{placeholder_summary.get('high', 0)}</span><span class="stat-label">高引用占位符</span></div>
        </div>
        {f'<p class="dim">临时隔离目录：{_esc(isolated_dir)}</p>' if isolated_dir else ''}
        <h3>高引用占位符</h3>
        <table class="detail-table">
            <thead><tr><th>占位符</th><th>引用次数</th></tr></thead>
            <tbody>{placeholder_rows}</tbody>
        </table>
        <h3>孤立条目</h3>
        <table class="detail-table">
            <thead><tr><th>条目</th></tr></thead>
            <tbody>{orphan_rows}</tbody>
        </table>
        <h3>悬空链接</h3>
        <table class="detail-table">
            <thead><tr><th>链接</th><th>来源文件</th></tr></thead>
            <tbody>{dangling_rows}</tbody>
        </table>
    </div>
    """


def _tc02_full_section(tc02_data: dict, qa_answers: dict, qa_by_id: dict) -> str:
    """Generate full TC-02 section with ALL questions sorted by score ascending."""
    if not tc02_data:
        return _empty_section('TC-02 问答准确率')

    total_earned = tc02_data.get('total_earned', 0)
    total_max = tc02_data.get('total_max', 0)
    final = tc02_data.get('final_score', 0)
    total_q = tc02_data.get('total_questions', 0)
    answered = tc02_data.get('answered', 0)
    zero = tc02_data.get('zero_score', 0)
    by_difficulty = tc02_data.get('by_difficulty', {})
    details = tc02_data.get('details', [])
    scoring_method = tc02_data.get('scoring_method', {})

    # Difficulty breakdown
    diff_rows = []
    for diff in ['easy', 'medium', 'hard']:
        stats = by_difficulty.get(diff, {})
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

    # Full question table
    rows = []
    for d in details:  # Already sorted by score ascending
        qid = d['id']
        question = d.get('question', '')
        difficulty = d.get('difficulty', 'medium')
        earned = d.get('earned', 0)
        max_pts = d.get('max_points', 0)
        answer = qa_answers.get(qid, '')
        standard = d.get('standard_answer', qa_by_id.get(qid, {}).get('standard_answer', ''))
        method = d.get('method', '')
        score_class = _score_class(earned, max_pts)
        diff_class = f'difficulty-{difficulty}'

        rows.append(f"""
        <tr>
            <td class="q-id"><span class="diff-tag {diff_class}">{difficulty}</span> <strong>Q{qid}</strong></td>
            <td class="q-question">{_esc(question)}</td>
            <td class="q-score"><span class="score-tag {score_class}">{earned:.2f}/{max_pts:.2f}</span></td>
            <td class="q-method dim">{method or '-'}</td>
            <td class="q-answers">
                <details><summary>标准答案</summary><div class="qa-box std">{_esc(standard)}</div></details>
                <details><summary>系统回答</summary><div class="qa-box ans">{_esc(answer) if answer else '<span class=\"dim\">无回答</span>'}</div></details>
            </td>
        </tr>
        """)

    return f"""
    <div class="section">
        <h2>TC-02 问答准确率 <span class="dim">({final:.1f}/60, 原始分 {total_earned:.1f}/{total_max:.1f})</span></h2>
        {scoring_info}
        <div class="stats-row">
            <div class="stat-card"><span class="stat-value">{total_q}</span><span class="stat-label">总题数</span></div>
            <div class="stat-card"><span class="stat-value">{answered}</span><span class="stat-label">已回答</span></div>
            <div class="stat-card"><span class="stat-value">{zero}</span><span class="stat-label">零分</span></div>
        </div>

        <h3>难度分布</h3>
        <table class="detail-table">
            <thead>
                <tr><th>难度</th><th>题数</th><th>得分率</th><th>得分</th><th>百分比</th></tr>
            </thead>
            <tbody>{''.join(diff_rows)}</tbody>
        </table>

        <h3>全部题目详情（按得分升序）</h3>
        <table class="full-table">
            <thead>
                <tr>
                    <th class="col-qid">题目</th>
                    <th class="col-qquestion">问题</th>
                    <th class="col-qscore">得分</th>
                    <th class="col-qmethod">评分方式</th>
                    <th class="col-qanswers">回答对比</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """


# ---------------------------------------------------------------------------
# Summary Report (all builds)
# ---------------------------------------------------------------------------

def generate_summary_html(all_results: dict, scorecard: dict, timestamp: str,
                          qa_judge: dict, concepts_judge: dict) -> str:
    """Generate a summary HTML comparing all builds."""
    qa_by_id = {q['id']: q for q in qa_judge.get('questions', [])}
    concepts_by_name = concepts_judge.get('terms', {})
    builds = scorecard.get('builds', {})
    avg = scorecard.get('average_score', 0)
    passed = avg >= PASS_THRESHOLD

    html = [_html_header()]
    html.append(f"""
    <div class="header-card {'passed' if passed else 'failed'}">
        <h1>Sediment 测试报告 — 总览</h1>
        <div class="meta-row"><span>生成时间: {timestamp}</span></div>
        <div class="score-display">
            <div class="score-circle" style="color: {'#22c55e' if passed else '#ef4444'}">
                <span class="score-value">{avg:.1f}</span>
                <span class="score-max">/100</span>
            </div>
            <div class="score-badge {'passed' if passed else 'failed'}">
                {'通过' if passed else '未通过'}（标准 ≥ {PASS_THRESHOLD}）
            </div>
        </div>
    </div>
    """)

    # Build comparison table
    if len(builds) >= 2:
        rows = []
        for btype, bdata in builds.items():
            label = '全量构建' if btype == 'full' else '分批构建'
            tc01 = bdata.get('tc01', 0)
            tc02 = bdata.get('tc02', 0)
            total = bdata.get('total', 0)
            dur = bdata.get('duration_seconds', 0)
            started = bdata.get('started_at', '')
            error = bdata.get('error')
            rows.append(f"""
            <tr>
                <td><strong>{label}</strong>{f'<br><span class="dim">{started}</span>' if started else ''}</td>
                <td>{tc01:.1f}<span class="dim">/40</span></td>
                <td>{tc02:.1f}<span class="dim">/60</span></td>
                <td><strong>{total:.1f}</strong></td>
                <td>{dur:.0f}s</td>
                <td class="dim">{_esc(error) if error else '-'}</td>
            </tr>
            """)

        html.append(f"""
        <div class="section">
            <h2>构建方式对比</h2>
            <table class="detail-table">
                <thead>
                    <tr><th>构建</th><th>TC-01 (40分)</th><th>TC-02 (60分)</th><th>总分</th><th>耗时</th><th>错误</th></tr>
                </thead>
                <tbody>{''.join(rows)}</tbody>
            </table>
        </div>
        """)

    diag_rows = []
    for btype in builds:
        build_dir = BUILDS_DIR / btype
        diag = load_build_diagnostics(build_dir, btype) or {}
        if not diag:
            continue
        label = '全量构建' if btype == 'full' else '分批构建'
        diag_rows.append(f"""
        <tr>
            <td><strong>{label}</strong></td>
            <td>{diag.get('entry_count', 0)}</td>
            <td>{diag.get('placeholder_count', 0)}</td>
            <td>{diag.get('avg_entry_size', 0)}</td>
            <td>{diag.get('orphan_entry_count', 0)}</td>
            <td>{diag.get('dangling_link_count', 0)}</td>
        </tr>
        """)
    if diag_rows:
        html.append(f"""
        <div class="section">
            <h2>KB 诊断对比</h2>
            <table class="detail-table">
                <thead>
                    <tr><th>构建</th><th>正式条目</th><th>占位条目</th><th>平均条目大小</th><th>孤立条目</th><th>悬空链接</th></tr>
                </thead>
                <tbody>{''.join(diag_rows)}</tbody>
            </table>
        </div>
        """)

    # Links to per-build reports
    for btype in builds:
        label = '全量构建' if btype == 'full' else '分批构建'
        report_name = f'report_{btype}.html'
        html.append(f'<div class="section"><h2><a href="{report_name}" class="report-link">{label} 详细报告</a></h2></div>')

    html.append(_html_footer())
    return '\n'.join(html)


# ---------------------------------------------------------------------------
# Report Generation Entry Point
# ---------------------------------------------------------------------------

def generate_report_from_results(results_dir: Path, all_results: dict) -> list[str]:
    """
    Generate HTML reports for each build type + a summary report.
    Returns list of generated file paths.
    """
    global RESULTS_DIR, BUILDS_DIR, REPORTS_DIR, JUDGE_DIR
    RESULTS_DIR = results_dir
    BUILDS_DIR = RESULTS_DIR / 'builds'
    REPORTS_DIR = RESULTS_DIR / 'reports'
    JUDGE_DIR = RESULTS_DIR.parent / 'judge'

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ts_file = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Load judge data
    concepts_judge = load_json(JUDGE_DIR / '概念.json') or {}
    qa_judge = load_json(JUDGE_DIR / '问答.json') or {}

    # Read scorecard for combined info
    scorecard = load_json(REPORTS_DIR / 'scorecard.json') or {}

    generated_files = []

    # Generate per-build reports
    for build_type in ['full', 'batched']:
        if build_type not in all_results:
            continue
        build_result = all_results[build_type]
        if build_result.get('error'):
            continue

        build_dir = BUILDS_DIR / build_type
        tc01_file = build_dir / f'concept_match_{build_type}.json'
        tc02_file = build_dir / f'answers_scored_{build_type}.json'
        tc01_data = load_json(tc01_file) or load_json(RESULTS_DIR / 'concept_match.json')
        tc02_data = load_json(tc02_file) or load_json(RESULTS_DIR / 'answers_scored.json')

        concept_answers = {}
        ca_file = build_dir / f'concept_answers_{build_type}.json'
        ca = load_json(ca_file)
        if ca and 'results' in ca:
            for item in ca['results']:
                concept_answers[item.get('concept', '')] = item.get('answer', '')

        qa_answers = {}
        qa_file = build_dir / f'qa_answers_{build_type}.json'
        qa = load_json(qa_file)
        if qa and 'results' in qa:
            for item in qa['results']:
                qa_answers[item.get('id', '')] = item.get('answer', '')
        kb_diagnostics = load_build_diagnostics(build_dir, build_type)

        html = generate_html_for_build(
            build_type, tc01_data, tc02_data, scorecard,
            concept_answers, qa_answers, kb_diagnostics, qa_judge, concepts_judge, timestamp
        )
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / f'report_{ts_file}_{build_type}.html'
        report_path.write_text(html, encoding='utf-8')
        generated_files.append(str(report_path))

    # Generate summary report
    if all_results:
        html = generate_summary_html(all_results, scorecard, timestamp, qa_judge, concepts_judge)
        summary_path = REPORTS_DIR / f'report_{ts_file}_summary.html'
        summary_path.write_text(html, encoding='utf-8')
        generated_files.append(str(summary_path))

    return generated_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_class(earned: float, max_pts: float) -> str:
    """Return CSS class based on score ratio."""
    if max_pts <= 0:
        return 'score-zero'
    ratio = earned / max_pts
    if ratio == 0:
        return 'score-zero'
    if ratio < 0.3:
        return 'score-critical'
    if ratio < 0.6:
        return 'score-low'
    if ratio < 0.8:
        return 'score-mid'
    if ratio < 1.0:
        return 'score-good'
    return 'score-perfect'


def _esc(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def _truncate_html(text: str, max_len: int) -> str:
    """Truncate text with HTML escaping."""
    if not text:
        return ''
    escaped = _esc(text)
    if len(text) > max_len:
        return escaped[:max_len] + '...'
    return escaped


def _empty_section(title: str) -> str:
    return f'<div class="section"><h2>{title}</h2><p class="dim">暂无数据</p></div>'


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
            padding: 1.5rem;
        }
        .container { max-width: 1400px; margin: 0 auto; }

        /* Header card */
        .header-card {
            background: white;
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            text-align: center;
        }
        .header-card.passed { border-top: 4px solid #22c55e; }
        .header-card.failed { border-top: 4px solid #ef4444; }
        .header-card h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
        .meta-row { font-size: 0.85rem; color: #888; margin-bottom: 0.25rem; }

        .score-display {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 1.5rem;
            margin-top: 1rem;
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
        }
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

        .score-breakdown {
            display: flex;
            justify-content: center;
            gap: 2rem;
            margin-top: 1.5rem;
        }
        .bd-card {
            background: #f8f8f8;
            border-radius: 8px;
            padding: 1rem 2rem;
            text-align: center;
        }
        .bd-label { font-size: 0.8rem; color: #666; margin-bottom: 0.25rem; }
        .bd-value { font-size: 1.5rem; font-weight: 700; }
        .bd-max { font-size: 0.85rem; color: #888; font-weight: 400; }

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
            margin: 1.5rem 0 0.5rem;
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
        .score-zero     { background: #fee2e2; color: #991b1b; }
        .score-critical { background: #fecaca; color: #b91c1c; }
        .score-low      { background: #fef3c7; color: #92400e; }
        .score-mid      { background: #dbeafe; color: #1e40af; }
        .score-good     { background: #dcfce7; color: #166534; }
        .score-perfect  { background: #d1fae5; color: #065f46; border: 1px solid #065f46; }

        /* Difficulty tags */
        .diff-tag {
            display: inline-block;
            padding: 1px 6px;
            border-radius: 3px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .difficulty-easy   { background: #dcfce7; color: #166534; }
        .difficulty-medium { background: #dbeafe; color: #1e40af; }
        .difficulty-hard   { background: #fef3c7; color: #92400e; }

        /* Tables */
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }
        th {
            text-align: left;
            padding: 0.5rem 0.75rem;
            background: #f8f8f8;
            font-weight: 600;
            color: #555;
            border-bottom: 2px solid #eee;
            position: sticky;
            top: 0;
            z-index: 1;
        }
        td {
            padding: 0.5rem 0.75rem;
            border-bottom: 1px solid #f0f0f0;
            vertical-align: top;
        }
        tr:nth-child(even) { background: #fafafa; }
        tr:hover { background: #f0f0f0; }

        /* Full detail table column widths */
        .full-table { table-layout: fixed; }
        .col-concept  { width: 12%; }
        .col-score    { width: 8%; }
        .col-def      { width: 35%; }
        .col-ans      { width: 45%; }
        .col-qid      { width: 8%; }
        .col-qquestion{ width: 30%; }
        .col-qscore   { width: 10%; }
        .col-qmethod  { width: 10%; }
        .col-qanswers { width: 42%; }

        .detail-table { font-size: 0.85rem; }
        .trend-table  { font-size: 0.9rem; }

        /* Concept name column */
        .concept-name { font-size: 0.9rem; }
        /* Definition / Answer cells */
        .def-cell, .ans-cell { font-size: 0.82rem; color: #444; }
        .def-cell details, .ans-cell details { cursor: pointer; }
        .def-cell summary, .ans-cell summary { list-style: none; }
        .def-cell summary::-webkit-details-marker, .ans-cell summary::-webkit-details-marker { display: none; }

        /* QA cells */
        .q-id { white-space: nowrap; }
        .q-question { max-width: 300px; }
        .q-score { white-space: nowrap; }
        .q-method { font-size: 0.8rem; color: #888; }
        .q-answers details { margin-bottom: 0.25rem; cursor: pointer; }
        .q-answers summary { list-style: none; }
        .q-answers summary::-webkit-details-marker { display: none; }
        .qa-box {
            padding: 0.5rem;
            background: #f8f8f8;
            border-radius: 4px;
            font-size: 0.82rem;
            margin-top: 0.25rem;
            max-height: 200px;
            overflow-y: auto;
        }
        .qa-box.std { border-left: 3px solid #166534; }
        .qa-box.ans { border-left: 3px solid #1e40af; }

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
        }

        /* Details */
        details { margin-top: 0.25rem; }
        details summary {
            padding: 0.25rem 0.5rem;
            background: #f8f8f8;
            border-radius: 4px;
            font-weight: 500;
            user-select: none;
            font-size: 0.82rem;
        }
        details summary:hover { background: #f0f0f0; }

        /* Report links */
        .report-link {
            color: #1e40af;
            text-decoration: none;
            font-size: 1.1rem;
        }
        .report-link:hover { text-decoration: underline; }

        /* Utilities */
        .dim { color: #888; font-size: 0.85rem; }

        /* Footer */
        .footer {
            text-align: center;
            padding: 2rem;
            color: #888;
            font-size: 0.85rem;
        }

        /* Responsive */
        @media (max-width: 768px) {
            body { padding: 0.5rem; }
            .section { padding: 1rem; }
            .score-breakdown { flex-direction: column; align-items: center; }
            .stats-row { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
<div class="container">
"""


def _html_footer() -> str:
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return f"""
    <div class="footer">
        <p>报告生成时间: {now}</p>
        <p>Sediment 测试方案</p>
    </div>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Archive Management
# ---------------------------------------------------------------------------

def archive_current_results() -> Path | None:
    """
    Move current results to history directory with a timestamp label.
    Returns the history entry path, or None if nothing to archive.
    """
    has_data = (
        REPORTS_DIR.exists() and any(REPORTS_DIR.iterdir())
    ) or (
        BUILDS_DIR.exists() and any(BUILDS_DIR.iterdir())
    )

    if not has_data:
        return None

    history_dir = RESULTS_DIR / 'history'
    history_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    entry = history_dir / ts
    entry.mkdir(parents=True, exist_ok=True)

    import shutil
    for dirname in ('reports', 'builds'):
        src = RESULTS_DIR / dirname
        if src.exists():
            shutil.copytree(src, entry / dirname, dirs_exist_ok=True)

    return entry


# ---------------------------------------------------------------------------
# Main (standalone CLI)
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Sediment HTML Report Generator')
    parser.add_argument('--output', type=str, default=None, help='Output HTML file path')
    parser.add_argument('--no-archive', action='store_true', help='Do not archive current results to history')
    args = parser.parse_args()

    if not args.no_archive:
        archived = archive_current_results()
        if archived:
            print(f"[report] Archived current results to history: {archived.name}")

    results = discover_results()
    if not results:
        print("[report] No scoring results found in results directory.")
        print("[report] Run `python benchmarks/scripts/run_all_scores.py` first.")
        sys.exit(1)

    print(f"[report] Found {len(results)} result set(s)")
    html = generate_html(results)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else REPORTS_DIR / 'report.html'
    output_path.write_text(html, encoding='utf-8')
    print(f"[report] Report written to: {output_path}")


# Legacy generate_html for backward compatibility (standalone CLI usage)
def generate_html(results: list[dict]) -> str:
    """Generate a comprehensive HTML report from legacy discover_results() output."""
    concepts_judge = load_json(JUDGE_DIR / '概念.json') or {}
    qa_judge = load_json(JUDGE_DIR / '问答.json') or {}
    qa_by_id = {q['id']: q for q in qa_judge.get('questions', [])}
    concepts_by_name = concepts_judge.get('terms', {})
    current = results[-1] if results else None

    html = [_html_header()]
    if current and current['scorecard']:
        sc = current['scorecard']
        avg = sc.get('average_score', 0)
        passed = avg >= PASS_THRESHOLD
        html.append(f"""
        <div class="header-card {'passed' if passed else 'failed'}">
            <h1>Sediment 测试报告</h1>
            <div class="score-display">
                <div class="score-circle" style="color: {'#22c55e' if passed else '#ef4444'}">
                    <span class="score-value">{avg:.1f}</span>
                    <span class="score-max">/100</span>
                </div>
                <div class="score-badge {'passed' if passed else 'failed'}">
                    {'通过' if passed else '未通过'}（标准 ≥ {PASS_THRESHOLD}）
                </div>
            </div>
        </div>
        """)

    if len(results) > 1:
        html.append(_trend_section(results))

    if current:
        html.append(_tc01_full_section(current['tc01'], current.get('concept_answers', {}), concepts_by_name))
        html.append(_tc02_full_section(current['tc02'], current.get('qa_answers', {}), qa_by_id))
        if current['scorecard'] and 'builds' in current['scorecard']:
            html.append(_build_comparison_section(current['scorecard']))

    html.append(_html_footer())
    return '\n'.join(html)


def _trend_section(results: list[dict]) -> str:
    rows = []
    for r in results:
        sc = r.get('scorecard', {})
        tc01 = r.get('tc01', {})
        tc02 = r.get('tc02', {})
        avg = sc.get('average_score', 0)
        tc01_score = tc01.get('final_score', 0) if tc01 else 0
        tc02_score = tc02.get('final_score', 0) if tc02 else 0
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
            <thead><tr><th>轮次</th><th>TC-01 概念覆盖率</th><th>TC-02 问答准确率</th><th>平均分</th><th>详情</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    </div>
    """


def _build_comparison_section(scorecard: dict) -> str:
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
            <thead><tr><th>构建方式</th><th>TC-01 (40分)</th><th>TC-02 (60分)</th><th>总分</th><th>错误</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    </div>
    """


if __name__ == '__main__':
    main()
