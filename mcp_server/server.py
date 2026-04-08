"""
server.py — Sediment MCP Server

Exposes three tools:
  - knowledge_list    : list all entry names in the knowledge base
  - knowledge_read    : read a specific entry by name
  - knowledge_ask     : answer a natural-language question via a sub-agent

KB_PATH is read from the environment variable SEDIMENT_KB_PATH (default: ./knowledge-base).
The CLI used by knowledge_ask is controlled by SEDIMENT_CLI (default: opencode).
"""

import os
import sys
import json
import subprocess
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KB_PATH = os.environ.get('SEDIMENT_KB_PATH', './knowledge-base')
SEDIMENT_CLI = os.environ.get('SEDIMENT_CLI', 'opencode')

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
    root = Path(KB_PATH)
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

    root = Path(KB_PATH)
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
    针对知识库提出自然语言问题，由内部子 Agent 多轮推理后返回综合答案。
    读取 skills/explore.md 作为子 Agent 的 system prompt。
    通过 subprocess 调用 CLI（默认 opencode，可通过 SEDIMENT_CLI 覆盖）。
    CLI 不可用或超时时降级返回。
    """
    _FALLBACK = json.dumps(
        {
            'answer': (
                'knowledge_ask unavailable: CLI not found. '
                'Use knowledge_list + knowledge_read for manual exploration.'
            ),
            'sources': [],
        },
        ensure_ascii=False,
    )

    # Locate the explore skill
    skill_path = Path(__file__).parent.parent / 'skills' / 'explore.md'
    if not skill_path.exists():
        return _FALLBACK

    explore_skill_content = skill_path.read_text(encoding='utf-8')

    cmd = [
        SEDIMENT_CLI,
        '--print',
        '--system', explore_skill_content,
        question,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout.strip()

        # Try to extract JSON from the output
        # The sub-agent should return a JSON object; look for the first { ... }
        start = output.find('{')
        end = output.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = output[start:end + 1]
            parsed = json.loads(json_str)
            return json.dumps(parsed, ensure_ascii=False)
        else:
            # Wrap raw text in our format
            return json.dumps(
                {'answer': output, 'sources': []},
                ensure_ascii=False,
            )

    except FileNotFoundError:
        # CLI binary not found
        return _FALLBACK
    except subprocess.TimeoutExpired:
        return json.dumps(
            {
                'answer': 'knowledge_ask timeout: sub-agent did not respond within 120 seconds.',
                'sources': [],
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {
                'answer': f'knowledge_ask error: {exc}',
                'sources': [],
            },
            ensure_ascii=False,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import asyncio
    asyncio.run(stdio_server(app))
