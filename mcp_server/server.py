"""
server.py — Sediment MCP Server

Exposes three tools:
  - knowledge_list    : list all entry names in the knowledge base
  - knowledge_read    : read a specific entry by name
  - knowledge_ask     : answer a natural-language question via the internal explore runtime

KB_PATH is read from the environment variable SEDIMENT_KB_PATH (default: ./knowledge-base).
The CLI used by knowledge_ask is controlled by SEDIMENT_CLI (default: claude).

Runs as an HTTP server using SSE transport, allowing remote clients to connect via URL.
"""

import json
import os
from pathlib import Path

from mcp import types
from mcp.server import Server

from mcp_server.retrieval import answer_question

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
async def _app_list_tools() -> list[types.Tool]:
    return _tool_definitions()


def _tool_definitions() -> list[types.Tool]:
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
                '针对知识库提出自然语言问题，由内部 explore runtime 返回综合答案。'
                '返回格式至少包含 answer 和 sources，并附带 confidence、'
                'exploration_summary、gaps、contradictions。'
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
async def _app_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    result = await _dispatch_tool(name, arguments)
    return [types.TextContent(type='text', text=str(result))]


async def _dispatch_tool(name: str, arguments: dict):
    if name == 'knowledge_list':
        return await _knowledge_list()
    if name == 'knowledge_read':
        return await _knowledge_read(arguments.get('filename', ''))
    if name == 'knowledge_ask':
        return await _knowledge_ask(arguments.get('question', ''))
    return f'ERROR: Unknown tool "{name}".'


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
    针对知识库提出自然语言问题，通过 explore runtime 回答。
    返回 JSON，至少包含 answer 与 sources。
    """
    result = answer_question(question, KB_PATH, _PROJECT_ROOT)
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# HTTP / SSE + Direct JSON-RPC Router
# ---------------------------------------------------------------------------


def _make_router(sse):
    """Create an ASGI router that handles:
    - GET: SSE stream establishment
    - POST with JSON body: direct JSON-RPC call (no session needed)
    - POST with SSE session: forwarded to SSE handler
    """
    async def _handle_direct_jsonrpc(scope, receive, send, body_bytes):
        """Handle a direct JSON-RPC POST without SSE session."""
        try:
            body = json.loads(body_bytes.decode('utf-8'))
            method = body.get('method', '')
            params = body.get('params', {})
            tool_name = params.get('name', '')
            arguments = params.get('arguments', {})

            if method == 'tools/call' and tool_name:
                result = await _call_tool_for_rpc(tool_name, arguments)
                response_body = json.dumps({
                    'jsonrpc': '2.0',
                    'id': body.get('id', 1),
                    'result': {
                        'content': [{'type': 'text', 'text': result}],
                    },
                }, ensure_ascii=False)
            elif method == 'tools/list':
                tools = await _list_tools_for_rpc()
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
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
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


async def _list_tools_for_rpc() -> list[types.Tool]:
    return _tool_definitions()


async def _call_tool_for_rpc(name: str, arguments: dict) -> str:
    """Direct tool call dispatcher (for JSON-RPC)."""
    result = await _dispatch_tool(name, arguments)
    if name == 'knowledge_list':
        return json.dumps(result, ensure_ascii=False)
    return str(result)


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
