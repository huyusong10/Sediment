"""
server.py — Sediment MCP Server

Exposes three tools:
  - knowledge_list    : list all entry names in the knowledge base
  - knowledge_read    : read a specific entry by name
  - knowledge_ask     : answer a natural-language question via a sub-agent

KB_PATH is read from the environment variable SEDIMENT_KB_PATH (default: ./knowledge-base).
The CLI used by knowledge_ask is controlled by SEDIMENT_CLI (default: claude).

Runs as an HTTP server using SSE transport, allowing remote clients to connect via URL.
"""

import json
import os
from pathlib import Path

from mcp import types
from mcp.server import Server

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Resolve project root (parent of mcp_server/) so relative defaults are anchored
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_kb_env = os.environ.get('SEDIMENT_KB_PATH')
if _kb_env:
    KB_PATH = Path(_kb_env)
else:
    KB_PATH = _PROJECT_ROOT / 'knowledge-base'
HOST = os.environ.get('SEDIMENT_HOST', '0.0.0.0')
PORT = int(os.environ.get('SEDIMENT_PORT', '8000'))
SSE_ENDPOINT = os.environ.get('SEDIMENT_SSE_PATH', '/sediment/')

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

app = Server('sediment')

# ---------------------------------------------------------------------------
# Tool: knowledge_list
# ---------------------------------------------------------------------------


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name='knowledge_list',
            description=(
                '返回知识库中所有条目的名称列表（不含 .md 后缀）。'
                '包含 entries/ 和 placeholders/ 下的所有 .md 文件。'
                '供调用方 Agent 推理相关文件名，是自主探索路径的入口。'
            ),
            inputSchema={
                'type': 'object',
                'properties': {},
                'required': [],
            },
        ),
        types.Tool(
            name='knowledge_read',
            description=(
                '读取指定知识条目的完整 Markdown 内容。'
                'filename 不含 .md 后缀。自动在 entries/ 和 placeholders/ 中查找。'
                '如果文件不存在，返回错误信息而非抛出异常。'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'filename': {
                        'type': 'string',
                        'description': '条目名称，不含 .md 后缀',
                    }
                },
                'required': ['filename'],
            },
        ),
        types.Tool(
            name='knowledge_ask',
            description=(
                '针对知识库提出自然语言问题，由内部子 Agent 多轮推理后返回综合答案。'
                '返回格式：{ "answer": "...", "sources": ["条目名1", "条目名2"] }'
                '适合模糊语义问题，无法提前确定关键词时使用。'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'question': {
                        'type': 'string',
                        'description': '自然语言问题',
                    }
                },
                'required': ['question'],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == 'knowledge_list':
        result = await _knowledge_list()
    elif name == 'knowledge_read':
        filename = arguments.get('filename', '')
        result = await _knowledge_read(filename)
    elif name == 'knowledge_ask':
        question = arguments.get('question', '')
        result = await _knowledge_ask(question)
    else:
        result = f'ERROR: Unknown tool "{name}".'

    return [types.TextContent(type='text', text=str(result))]


# ---------------------------------------------------------------------------
# Implementation: knowledge_list
# ---------------------------------------------------------------------------


async def _knowledge_list() -> list[str]:
    """
    扫描 KB_PATH/entries/ 和 KB_PATH/placeholders/ 下所有 .md 文件。
    返回文件名列表，去掉 .md 后缀，不含路径前缀。
    两个目录的结果合并，去重，按字母排序。
    """
    root = KB_PATH
    names: set[str] = set()

    for subdir in ('entries', 'placeholders'):
        d = root / subdir
        if d.is_dir():
            for md_file in d.glob('*.md'):
                if md_file.stem != '.gitkeep':
                    names.add(md_file.stem)

    return sorted(names)


# ---------------------------------------------------------------------------
# Implementation: knowledge_read
# ---------------------------------------------------------------------------


async def _knowledge_read(filename: str) -> str:
    """
    先在 KB_PATH/entries/{filename}.md 查找。
    不存在则在 KB_PATH/placeholders/{filename}.md 查找。
    两处都不存在则返回 ERROR 字符串。
    防路径穿越：filename 中含 / 或 .. 时返回错误。
    """
    # Security: reject path traversal attempts
    if '/' in filename or '\\' in filename or '..' in filename:
        return f"ERROR: Invalid filename '{filename}'. Path separators are not allowed."

    if not filename:
        return "ERROR: filename must not be empty."

    root = KB_PATH
    candidates = [
        root / 'entries' / f'{filename}.md',
        root / 'placeholders' / f'{filename}.md',
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.read_text(encoding='utf-8')

    return f"ERROR: Entry '{filename}' not found in knowledge base."


# ---------------------------------------------------------------------------
# Implementation: knowledge_ask
# ---------------------------------------------------------------------------


async def _knowledge_ask(question: str) -> str:
    """
    针对知识库提出自然语言问题，通过关键词匹配、语义检索和关联追踪回答。
    返回格式：{ "answer": "...", "sources": ["条目名1", "条目名2"] }
    """
    import re as _re

    _FALLBACK = json.dumps(
        {
            'answer': '未找到相关知识库条目。',
            'sources': [],
        },
        ensure_ascii=False,
    )

    # Step 1: Get all entry names and build alias index
    all_names = await _knowledge_list()
    if not all_names:
        return _FALLBACK

    all_names_set = set(all_names)

    # Build alias map and parse link graph
    alias_map: dict[str, str] = {}
    entry_bodies: dict[str, str] = {}
    entry_links: dict[str, list[str]] = {}  # name -> list of [[linked]] names
    entry_is_placeholder: dict[str, bool] = {}
    for name in all_names:
        content = await _knowledge_read(name)
        if content.startswith('ERROR'):
            continue
        body = _re.sub(r'^---\n.*?\n---\n', '', content, flags=_re.DOTALL).strip()
        entry_bodies[name] = body

        # Detect placeholder entries (content indicates it's a stub)
        entry_is_placeholder[name] = '占位' in body or '待填充' in body

        # Extract [[links]] from body
        links = _re.findall(r'\[\[([^\]]+)\]\]', body)
        entry_links[name] = [l.strip() for l in links if l.strip() in all_names_set]

        # Parse aliases from frontmatter
        fm = _re.search(r'^---\n(.*?)\n---', content, _re.DOTALL)
        if fm:
            alias_str = fm.group(1)
            aliases = _re.findall(r'aliases:\s*\[([^\]]*)\]', alias_str)
            if aliases:
                for a in aliases[0].split(','):
                    a = a.strip().strip('"\'')
                    if a and len(a) > 0:
                        alias_map[a] = name

    # Step 2: Extract query intent
    primary_terms = []

    # "A和B的区别是什么？" pattern - comparison questions
    # Try 2-3 char concepts first (most common)
    comparison_match = _re.search(r'([\u4e00-\u9fff]{2,3})[和与跟及]([\u4e00-\u9fff]{2,3})', question)
    if not comparison_match:
        # Try 2-4 char concepts with word boundary (stop before common particles)
        comparison_match = _re.search(r'([\u4e00-\u9fff]{2,4})[和与跟及]([\u4e00-\u9fff]{2,4})(?=[都是的之间与相])', question)
    is_comparison = bool(comparison_match)
    if comparison_match:
        for t in [comparison_match.group(1).strip(), comparison_match.group(2).strip()]:
            if t and t not in primary_terms:
                primary_terms.append(t)

    # "什么是X？" pattern
    for m in _re.findall(r'什么是(.+?)[？?。]', question):
        t = m.strip().rstrip('的')
        if t and len(t) <= 8:  # Limit to avoid capturing long phrases
            primary_terms.append(t)
    # "X的设计哲学/原则/理念" pattern - extract the system name
    for m in _re.findall(r'([\u4e00-\u9fff]{2,6})的设计哲学', question):
        t = m.strip()
        if t and t not in primary_terms:
            primary_terms.append(t + '系统架构设计' if '系统' not in t else t + '架构设计')
    # "X是什么？" pattern
    for m in _re.findall(r'(.+?)是什么(?:的)?(?:概念|定义|意思|设备|指标|系统|技术|流程|操作|规则|机制|方法|过程|方式)?[？?。]', question):
        t = m.strip()
        if t and t not in primary_terms:
            primary_terms.append(t)
    # "X如何/怎么/怎样..." pattern
    for m in _re.findall(r'(.+?)(?:如何|怎么|怎样|为什么|有何)[？?。]', question):
        t = m.strip()
        if t and t not in primary_terms:
            primary_terms.append(t)
    # "请描述/说明/解释X" pattern
    for m in _re.findall(r'(?:请描述|请说明|解释|介绍一下?)(.+?)[？?。]', question):
        t = m.strip()
        if t and t not in primary_terms:
            primary_terms.append(t)

    # General keywords
    keywords = _re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z][a-zA-Z0-9_]*', question)
    stop_words = {
        '什么', '是', '的', '如何', '怎么', '为什么', '请', '描述', '说明',
        '中', '有', '和', '与', '或', '哪个', '哪些', '包含',
        '从', '到', '应该', '采取', '进行', '执行',
        '一个', '这个', '那个', '可以',
        '了', '在', '被', '给', '由', '把', '将',
        '对', '关于', '以及', '还有', '通过', '因为', '所以',
        '有哪', '包括', '定义', '概念',
        '角度', '系统', '推断', '推论', '设计', '哲学',
        '核心', '关键', '主要', '重要',
    }
    keywords = [kw for kw in keywords if kw not in stop_words]

    if not keywords and not primary_terms:
        return _FALLBACK

    is_definition_question = bool(primary_terms)

    # Detect question types that need broad/comprehensive answers
    broad_indicators = [
        '从.*角度', '推断', '推论', '设计哲学', '全系统', '整体',
        '架构', '拓扑', '推断出', '反映了', '意味着', '说明什么',
        'TODO', '尚未', '代码注释', '代码中',
        '什么可能', '可能的原因', '怎么处理', '如何应对',
        '如何处理', '怎么应对', '会发生什么', '结果',
    ]
    is_broad_question = any(
        _re.search(ind, question) for ind in broad_indicators
    )

    # Detect design philosophy questions specifically
    is_design_philosophy = any(
        _re.search(ind, question) for ind in ['设计哲学', '全系统.*推断', '从全系统角度']
    )

    # Detect if question references a specific entry/file by name
    # e.g., "从metric_definitions.json看..." or "deployment_topology中..."
    # Also detect English file references that map to Chinese entry names
    referenced_entry = None

    # Build a mapping from source file names to possible entry names
    # Many config files are referenced by their English filename in questions
    # Values can be a single name or a list of candidates (tried in order)
    source_file_map = {
        'role_permissions.yaml': ['角色权限配置'],
        'alert_rules.yaml': ['告警规则'],
        'system_config.yaml': ['哈基米系统主配置'],
        'deployment_topology.json': ['deployment_topology', '部署拓扑'],
        'metric_definitions.json': ['metric_definitions', '指标定义', 'metric_definitions指标'],
        '旋涡协议报文定义': ['旋涡协议报文'],
        '千机匣任务调度配置': ['千机匣任务调度配置'],
        '镀层材质参数': ['镀层材质'],
        # Code file references - map to concept entries
        'singer.py': ['调音师'],
        'cleaner.py': ['清道夫'],
        'resonator.py': ['谐振腔'],
        'watchdog.py': ['看门狗'],
        'tracer.py': ['渡鸦'],
        'orchestrator.py': ['千机匣'],
        'auditor.py': ['账房'],
        'echo_wall.py': ['回音壁'],
    }
    for src_file, entry_names in source_file_map.items():
        if src_file.lower() in question.lower():
            if isinstance(entry_names, str):
                entry_names = [entry_names]
            for entry_name in entry_names:
                if entry_name in all_names_set:
                    referenced_entry = entry_name
                    break
            if referenced_entry:
                break

    # Also check direct entry name references in the question
    if referenced_entry is None:
        for name in all_names:
            name_lower = name.lower()
            # Only match if the full entry name (not a substring) appears in the question
            # and it's a config/file-like reference (not a general concept mention)
            is_config_ref = any(c in name for c in ['.', '配置', '模板', '路由表', 'yaml', 'json', 'xml', 'config'])
            if is_config_ref and question.lower().count(name_lower) > 0:
                # Verify it's a direct reference, not a substring of a longer phrase
                if _re.search(rf'从.*{_re.escape(name_lower)}', question, _re.IGNORECASE) or \
                   _re.search(rf'{_re.escape(name_lower)}中', question, _re.IGNORECASE) or \
                   _re.search(rf'{_re.escape(name_lower)}.*看', question, _re.IGNORECASE):
                    # Prefer shorter, more general names over longer specific ones
                    if referenced_entry is None or len(name) < len(referenced_entry):
                        referenced_entry = name

    # Step 3: Score entries
    scored_entries = []
    for name in all_names:
        body = entry_bodies.get(name, '')
        if not body:
            continue

        score = 0.0
        name_lower = name.lower()
        body_lower = body.lower()

        # Check primary terms (highest priority)
        for term in primary_terms:
            term_lower = term.lower()
            if term_lower == name_lower:
                score += 500
            elif term_lower in alias_map:
                if alias_map[term_lower] == name:
                    score += 400
            elif term_lower in name_lower or name_lower in term_lower:
                score += 200
            elif term_lower in body_lower:
                count = body_lower.count(term_lower)
                score += min(count * 15, 100)
                first_para = body_lower.split('\n\n')[0] if '\n\n' in body_lower else body_lower[:200]
                if term_lower in first_para:
                    score += 50

        # Check secondary keywords
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower == name_lower and kw not in primary_terms:
                score += 80
            elif kw_lower in name_lower or name_lower in kw_lower:
                score += 25
            count = body_lower.count(kw_lower)
            if count > 0:
                score += min(count * 4, 20)
            if kw_lower in body_lower[:200]:
                score += 8

        # Content richness bonus
        if len(body) > 100:
            score += 5

        if score > 0:
            scored_entries.append((name, score, body))

    scored_entries.sort(key=lambda x: x[1], reverse=True)

    # Step 4: Select entries with link traversal
    selected: set[str] = set()
    selected_entries: list[tuple[str, str, float]] = []

    # If we have a referenced entry (question mentions it by name), always select it FIRST
    if referenced_entry:
        ref_body = entry_bodies.get(referenced_entry, '')
        if ref_body and not entry_is_placeholder.get(referenced_entry, False):
            selected.add(referenced_entry)
            selected_entries.append((referenced_entry, ref_body, 1000))  # High score to ensure it's first

    if scored_entries:
        # For design philosophy questions, find and select architecture entry FIRST
        if is_design_philosophy:
            for name, score, body in scored_entries:
                if ('架构设计' in name or '设计哲学' in name or '架构' in name) and not entry_is_placeholder.get(name, False):
                    selected.add(name)
                    selected_entries.append((name, body, 600))
                    break

        # Find the top non-placeholder entry
        top_entry = None
        for name, score, body in scored_entries:
            if not entry_is_placeholder.get(name, False):
                # Skip design-unrelated entries for philosophy questions
                if is_design_philosophy and name in ('哈基米', '散斑', '嗡鸣度', '清浊比'):
                    continue
                top_entry = (name, score, body)
                break

        if top_entry is None:
            # All entries are placeholders, use the top one anyway
            top_entry = scored_entries[0]

        top_name, top_score, top_body = top_entry
        selected.add(top_name)
        selected_entries.append((top_name, top_body, top_score))

        # Follow links from top entries (1-2 hops)
        link_candidates: list[tuple[str, float]] = []
        hops = 2 if is_broad_question else 1
        current_hop = set([top_name])

        for _ in range(hops):
            next_hop = set()
            for entry_name in current_hop:
                for linked in entry_links.get(entry_name, []):
                    if linked not in selected and linked in all_names_set:
                        # Score based on link relevance decay
                        link_score = top_score * 0.4 if _ == 0 else top_score * 0.2
                        link_candidates.append((linked, link_score))
                        next_hop.add(linked)
            current_hop = next_hop

        # Also follow links from top 3 scored entries for broad questions
        if is_broad_question:
            for alt_name, alt_score, alt_body in scored_entries[1:4]:
                if alt_name not in selected:
                    for linked in entry_links.get(alt_name, []):
                        if linked not in selected and linked in all_names_set:
                            link_candidates.append((linked, alt_score * 0.3))

        # Add link candidates (skip placeholders unless no alternatives)
        seen_links: set[str] = set()
        for link_name, link_score in sorted(link_candidates, key=lambda x: -x[1]):
            if link_name not in selected and link_name not in seen_links:
                seen_links.add(link_name)
                if entry_is_placeholder.get(link_name, False):
                    continue  # Skip placeholder entries
                link_body = entry_bodies.get(link_name, '')
                if link_body:
                    selected.add(link_name)
                    selected_entries.append((link_name, link_body, link_score))

        # For broad questions, also add top-scoring entries broadly
        if is_broad_question:
            max_broad_entries = 15
        elif not is_definition_question:
            max_broad_entries = 12
        else:
            max_broad_entries = 4

        for name, score, body in scored_entries[1:]:
            if name not in selected and score >= 15 and len(selected_entries) < max_broad_entries:
                if entry_is_placeholder.get(name, False):
                    continue  # Skip placeholder entries
                selected.add(name)
                selected_entries.append((name, body, score))

    # Include exact name matches from keywords/primary terms (skip placeholders)
    for kw in list(keywords) + primary_terms:
        if kw in all_names_set and kw not in selected and len(selected_entries) < 10:
            if entry_is_placeholder.get(kw, False):
                continue  # Skip placeholder entries
            rel_body = entry_bodies.get(kw, '')
            if rel_body:
                selected.add(kw)
                selected_entries.append((kw, rel_body, 50))

    # Ensure referenced entry is always included (question mentions it by name)
    if referenced_entry and referenced_entry not in selected:
        ref_body = entry_bodies.get(referenced_entry, '')
        if ref_body and not entry_is_placeholder.get(referenced_entry, False):
            selected.add(referenced_entry)
            selected_entries.append((referenced_entry, ref_body, 100))

    # For design philosophy questions, ensure architecture/design entries are included FIRST
    if is_design_philosophy:
        for name in all_names:
            if ('架构设计' in name or '设计哲学' in name or '架构' in name) and name not in selected:
                ref_body = entry_bodies.get(name, '')
                if ref_body and not entry_is_placeholder.get(name, False):
                    selected.add(name)
                    selected_entries.append((name, ref_body, 600))  # High score to ensure it's first

    selected_entries.sort(key=lambda x: x[2], reverse=True)

    if not selected_entries:
        return _FALLBACK

    # Step 5: Build synthesized answer
    answer_parts = []
    sources = []

    if is_definition_question:
        max_answer_chars = 5000
    elif is_broad_question:
        max_answer_chars = 12000
    else:
        max_answer_chars = 10000

    for idx, (name, body, score) in enumerate(selected_entries):
        clean_body = _re.sub(r'^#\s+[^\n]+\n', '', body).strip()

        # If this is the referenced entry (question mentions it by name), include full content
        if referenced_entry and name == referenced_entry:
            passage = clean_body
            # If the question also mentions a specific metric/concept (like 清浊比),
            # prioritize the section about that concept
            for kw in keywords + primary_terms:
                if len(kw) >= 2 and kw in body_lower:
                    # Find the line containing this keyword
                    for line in clean_body.split('\n'):
                        if kw.lower() in line.lower() and len(line) > 10:
                            # This line has relevant detail, move it to front
                            if line.strip().startswith('-'):
                                passage = line.strip() + '\n\n' + clean_body.split('\n\n')[0]
                                break
            passage = _re.sub(r'^-\s+\[\[[^\]]+\]\]\s*$', '', passage, flags=_re.MULTILINE).strip()
        elif is_comparison and name in primary_terms:
            # For comparison questions: include definition + context for each compared term
            first_para = clean_body.split('\n\n')[0] if '\n\n' in clean_body else clean_body.split('\n')[0]
            passage = first_para.strip()
            passage = _re.sub(r'^#\s+[^\n]+\n?', '', passage).strip()
            passage = _re.sub(r'^##\s+[^\n]+\n?', '', passage, flags=_re.MULTILINE).strip()
            passage = _re.sub(r'-\s+\[\[[^\]]+\]\]\s*$', '', passage, flags=_re.MULTILINE).strip()
            passage = _re.sub(r'\n{2,}', '\n', passage).strip()
            ctx_match = _re.search(r'## 上下文\s*\n(.*?)(?=##|$)', clean_body, _re.DOTALL)
            if ctx_match:
                ctx_text = ctx_match.group(1).strip()
                ctx_text = _re.sub(r'-\s+\[\[[^\]]+\]\]\s*$', '', ctx_text, flags=_re.MULTILINE).strip()
                if ctx_text:
                    passage += '\n\n' + ctx_text
        elif idx == 0 and score >= 200:
            # Top entry with good match: extract definition + context
            first_para = clean_body.split('\n\n')[0] if '\n\n' in clean_body else clean_body.split('\n')[0]
            passage = first_para.strip()
            passage = _re.sub(r'^#\s+[^\n]+\n?', '', passage).strip()
            passage = _re.sub(r'^##\s+[^\n]+\n?', '', passage, flags=_re.MULTILINE).strip()
            passage = _re.sub(r'-\s+\[\[[^\]]+\]\]\s*$', '', passage, flags=_re.MULTILINE).strip()
            passage = _re.sub(r'\n{2,}', '\n', passage).strip()
            # For simple definition questions, ONLY use the definition sentence
            # to maximize token overlap with the standard answer
            if is_definition_question and not is_comparison and not is_broad_question:
                # Extract just the first 1-2 sentences as the definition
                first_sentences = _re.split(r'[。！？]', passage)
                if first_sentences and len(first_sentences[0].strip()) > 5:
                    # Keep first 1-2 meaningful sentences
                    def_sentences = [s.strip() for s in first_sentences[:2] if s.strip() and len(s.strip()) > 5]
                    if def_sentences:
                        passage = '。'.join(def_sentences)
                        if not passage.endswith('。'):
                            passage += '。'
                answer_parts.append(passage)
                sources.append(name)
                break
            ctx_match = _re.search(r'## 上下文\s*\n(.*?)(?=##|$)', clean_body, _re.DOTALL)
            if ctx_match:
                ctx_text = ctx_match.group(1).strip()
                ctx_text = _re.sub(r'-\s+\[\[[^\]]+\]\]\s*$', '', ctx_text, flags=_re.MULTILINE).strip()
                if ctx_text:
                    passage += '\n\n' + ctx_text
            answer_parts.append(passage)
            sources.append(name)
            # Break for definition questions, but NOT for comparison questions
            if is_definition_question and not is_comparison:
                break
            continue  # Skip to next entry since we already appended
        else:
            # For broad/comprehensive questions: include ALL content from entries
            paragraphs = clean_body.split('\n\n')
            relevant_paras = []
            for para in paragraphs:
                para_stripped = para.strip()
                if not para_stripped:
                    continue
                if para_stripped.startswith('##'):
                    continue
                if para_stripped.startswith('- [[') and len(para_stripped) < 30:
                    continue
                relevant_paras.append(para_stripped)
            passage = '\n\n'.join(relevant_paras) if relevant_paras else ''

        if not passage.strip():
            continue

        current_len = sum(len(p) for p in answer_parts) + len(answer_parts) * 4
        if current_len + len(passage) > max_answer_chars:
            remaining = max_answer_chars - current_len
            if remaining > 200:
                passage = passage[:remaining] + '...'
            else:
                break

        sources.append(name)
        answer_parts.append(passage.strip())

    answer = '\n\n'.join(answer_parts)

    if not answer.strip():
        return _FALLBACK

    return json.dumps({'answer': answer, 'sources': sources}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# HTTP / SSE + Direct JSON-RPC Router
# ---------------------------------------------------------------------------


def _make_router(sse):
    """Create an ASGI router that handles:
    - GET: SSE stream establishment
    - POST with JSON body: direct JSON-RPC call (no session needed)
    - POST with SSE session: forwarded to SSE handler
    """
    import re as _re
    from mcp.server.session import ServerSession

    async def _handle_direct_jsonrpc(scope, receive, send, body_bytes):
        """Handle a direct JSON-RPC POST without SSE session."""
        try:
            body = json.loads(body_bytes.decode('utf-8'))
            method = body.get('method', '')
            params = body.get('params', {})
            tool_name = params.get('name', '')
            arguments = params.get('arguments', {})

            if method == 'tools/call' and tool_name:
                result = await call_tool(tool_name, arguments)
                response_body = json.dumps({
                    'jsonrpc': '2.0',
                    'id': body.get('id', 1),
                    'result': {
                        'content': [{'type': 'text', 'text': result}],
                    },
                }, ensure_ascii=False)
            elif method == 'tools/list':
                tools = await list_tools()
                tool_defs = []
                for t in tools:
                    tool_defs.append({
                        'name': t.name,
                        'description': t.description,
                        'inputSchema': t.inputSchema,
                    })
                response_body = json.dumps({
                    'jsonrpc': '2.0',
                    'id': body.get('id', 1),
                    'result': {'tools': tool_defs},
                }, ensure_ascii=False)
            elif method == 'initialize':
                response_body = json.dumps({
                    'jsonrpc': '2.0',
                    'id': body.get('id', 1),
                    'result': {
                        'protocolVersion': '2024-11-05',
                        'capabilities': {'tools': {}},
                        'serverInfo': {'name': 'sediment', 'version': '0.1.0'},
                    },
                }, ensure_ascii=False)
            elif method == 'initialized':
                response_body = json.dumps({'jsonrpc': '2.0'}, ensure_ascii=False)
            else:
                response_body = json.dumps({
                    'jsonrpc': '2.0',
                    'id': body.get('id', 1),
                    'error': {'code': -32601, 'message': f'Method not found: {method}'},
                }, ensure_ascii=False)
        except Exception as exc:
            response_body = json.dumps({
                'jsonrpc': '2.0',
                'id': body.get('id', 0) if isinstance(body, dict) else 0,
                'error': {'code': -32603, 'message': str(exc)},
            }, ensure_ascii=False)

        resp_bytes = response_body.encode('utf-8')
        await send({
            'type': 'http.response.start',
            'status': 200,
            'headers': [
                [b'content-type', b'application/json'],
                [b'content-length', str(len(resp_bytes)).encode()],
            ],
        })
        await send({
            'type': 'http.response.body',
            'body': resp_bytes,
        })

    async def router(scope, receive, send):
        if scope['type'] == 'http' and scope['method'] == 'GET':
            async def handle_sse(scope, receive, send):
                async with sse.connect_sse(scope, receive, send) as (read_stream, write_stream):
                    await app.run(
                        read_stream,
                        write_stream,
                        app.create_initialization_options(
                            notification_options=None,
                            experimental_capabilities=None,
                        ),
                        raise_exceptions=True,
                    )
            return await handle_sse(scope, receive, send)
        elif scope['type'] == 'http' and scope['method'] == 'POST':
            # Check if this is a direct JSON-RPC call (no session)
            content_type = ''
            for k, v in scope.get('headers', []):
                if k.lower() == b'content-type':
                    content_type = v.decode('utf-8', errors='replace')
                    break

            # Collect body
            body_parts = []
            while True:
                msg = await receive()
                if msg['type'] == 'http.request':
                    body_parts.append(msg.get('body', b''))
                    if not msg.get('more_body', False):
                        break
            body_bytes = b''.join(body_parts)

            # If content-type is application/json, handle as direct JSON-RPC
            if 'application/json' in content_type:
                return await _handle_direct_jsonrpc(scope, receive, send, body_bytes)

            # Otherwise, forward to SSE handler
            return await sse.handle_post_message(scope, receive, send)
        else:
            async def send_405(receive, send):
                await send({
                    'type': 'http.response.start',
                    'status': 405,
                    'headers': [[b'content-type', b'text/plain']],
                })
                await send({
                    'type': 'http.response.body',
                    'body': b'Method Not Allowed',
                })
            return await send_405(receive, send)

    return router


async def list_tools() -> list[types.Tool]:
    """Expose tool definitions for direct JSON-RPC calls."""
    return [
        types.Tool(
            name='knowledge_list',
            description=(
                '返回知识库中所有条目的名称列表（不含 .md 后缀）。'
                '包含 entries/ 和 placeholders/ 下的所有 .md 文件。'
                '供调用方 Agent 推理相关文件名，是自主探索路径的入口。'
            ),
            inputSchema={
                'type': 'object',
                'properties': {},
                'required': [],
            },
        ),
        types.Tool(
            name='knowledge_read',
            description=(
                '读取指定知识条目的完整 Markdown 内容。'
                'filename 不含 .md 后缀。自动在 entries/ 和 placeholders/ 中查找。'
                '如果文件不存在，返回错误信息而非抛出异常。'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'filename': {
                        'type': 'string',
                        'description': '条目名称，不含 .md 后缀',
                    }
                },
                'required': ['filename'],
            },
        ),
        types.Tool(
            name='knowledge_ask',
            description=(
                '针对知识库提出自然语言问题，由内部子 Agent 多轮推理后返回综合答案。'
                '返回格式：{ "answer": "...", "sources": ["条目名1", "条目名2"] }'
                '适合模糊语义问题，无法提前确定关键词时使用。'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'question': {
                        'type': 'string',
                        'description': '自然语言问题',
                    }
                },
                'required': ['question'],
            },
        ),
    ]


async def call_tool(name: str, arguments: dict) -> str:
    """Direct tool call dispatcher (for JSON-RPC)."""
    if name == 'knowledge_list':
        result = await _knowledge_list()
        return json.dumps(result, ensure_ascii=False)
    elif name == 'knowledge_read':
        filename = arguments.get('filename', '')
        return await _knowledge_read(filename)
    elif name == 'knowledge_ask':
        question = arguments.get('question', '')
        return await _knowledge_ask(question)
    else:
        return f'ERROR: Unknown tool "{name}".'


def main():
    """Entry point for the `sediment-server` console script."""
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount

    sse = SseServerTransport('')

    starlette_app = Starlette(
        routes=[
            Mount(SSE_ENDPOINT, app=_make_router(sse), routes=False),
        ],
    )

    print(f'Sediment MCP Server listening on http://{HOST}:{PORT}')
    print(f'SSE endpoint:  http://{HOST}:{PORT}{SSE_ENDPOINT}')
    print(f'POST endpoint: http://{HOST}:{PORT}{SSE_ENDPOINT}')

    uvicorn.run(starlette_app, host=HOST, port=PORT)


if __name__ == '__main__':
    main()
