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
import re
import subprocess
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from mcp import types
from mcp.server import Server

from mcp_server.i18n import tr
from mcp_server.kb import resolve_kb_document_path
from mcp_server.llm_cli import build_cli_command
from skills.explore.scripts.kb_query import inventory, prepare_explore_context, validate_answer

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

DEFAULT_CONTRACT = {
    'shortlist_limit': 8,
    'neighbor_depth': 2,
    'max_context_entries': 12,
    'max_snippets_per_entry': 2,
    'snippet_char_limit': 320,
    'cli_timeout_seconds': 150,
}

_EXPLORE_JSON_SCHEMA = json.dumps(
    {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'answer': {'type': 'string'},
            'sources': {'type': 'array', 'items': {'type': 'string'}},
            'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']},
            'exploration_summary': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'entries_scanned': {'type': 'integer'},
                    'entries_read': {'type': 'integer'},
                    'links_followed': {'type': 'integer'},
                    'mode': {'type': 'string'},
                },
                'required': ['entries_scanned', 'entries_read', 'links_followed', 'mode'],
            },
            'gaps': {'type': 'array', 'items': {'type': 'string'}},
            'contradictions': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {
                        'entries': {'type': 'array', 'items': {'type': 'string'}},
                        'conflict': {'type': 'string'},
                        'analysis': {'type': 'string'},
                    },
                    'required': ['entries', 'conflict', 'analysis'],
                },
            },
        },
        'required': [
            'answer',
            'sources',
            'confidence',
            'exploration_summary',
            'gaps',
            'contradictions',
        ],
    },
    ensure_ascii=False,
)

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
            description=tr('tool.knowledge_list.description'),
            inputSchema={
                'type': 'object',
                'properties': {},
                'required': [],
            },
        ),
        types.Tool(
            name='knowledge_read',
            description=tr('tool.knowledge_read.description'),
            inputSchema={
                'type': 'object',
                'properties': {
                    'filename': {
                        'type': 'string',
                        'description': tr('tool.knowledge_read.filename'),
                    }
                },
                'required': ['filename'],
            },
        ),
        types.Tool(
            name='knowledge_ask',
            description=tr('tool.knowledge_ask.description'),
            inputSchema={
                'type': 'object',
                'properties': {
                    'question': {
                        'type': 'string',
                        'description': tr('tool.knowledge_ask.question'),
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
    返回 KB 中所有知识文档名称，包含 entries / placeholders / indexes。
    """
    data = inventory(KB_PATH)
    names = set(data["entries"]) | set(data["placeholders"]) | set(data.get("indexes", []))
    return sorted(names)


# ---------------------------------------------------------------------------
# Implementation: knowledge_read
# ---------------------------------------------------------------------------


async def _knowledge_read(filename: str) -> str:
    """
    先查 formal / placeholder entries，再查 root index 与 indexes/。
    防路径穿越：filename 中含 / 或 .. 时返回错误。
    """
    # Security: reject path traversal attempts
    if '/' in filename or '\\' in filename or '..' in filename:
        return f"ERROR: Invalid filename '{filename}'. Path separators are not allowed."

    if not filename:
        return "ERROR: filename must not be empty."

    candidate = resolve_kb_document_path(KB_PATH, filename)
    if candidate is not None:
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


def answer_question(question: str, kb_path: Path, project_root: Path) -> dict[str, Any]:
    question = question.strip()
    if not question:
        return _error_payload('Question must not be empty.')

    inventory_data = inventory(kb_path)
    if not inventory_data['entries']:
        return {
            'answer': (
                'Knowledge base has no formal entries yet, '
                'so explore cannot answer reliably.'
            ),
            'sources': [],
            'confidence': 'low',
            'exploration_summary': {
                'entries_scanned': 0,
                'entries_read': 0,
                'links_followed': 0,
                'mode': 'no-evidence',
            },
            'gaps': ['No formal entries are available in the knowledge base.'],
            'contradictions': [],
        }

    try:
        skill_body, runtime_contract, skill_label = _load_explore_skill(project_root)
        context = prepare_explore_context(
            question,
            inventory_data=inventory_data,
            shortlist_limit=runtime_contract['shortlist_limit'],
            neighbor_depth=runtime_contract['neighbor_depth'],
            max_context_entries=runtime_contract['max_context_entries'],
            max_snippets_per_entry=runtime_contract['max_snippets_per_entry'],
            snippet_char_limit=runtime_contract['snippet_char_limit'],
        )

        if not context['expanded_candidates']:
            return {
                'answer': (
                    'No sufficiently relevant knowledge entries were found '
                    'for this question.'
                ),
                'sources': [],
                'confidence': 'low',
                'exploration_summary': {
                    'entries_scanned': len(inventory_data['entries']),
                    'entries_read': 0,
                    'links_followed': 0,
                    'mode': 'no-match',
                },
                'gaps': [
                    'The current KB does not expose an obvious formal entry '
                    'for this question.'
                ],
                'contradictions': [],
            }

        payload = {
            'question': question,
            'runtime_contract': runtime_contract,
            'context': context,
        }
        return _run_validated_explore(
            question=question,
            skill_body=skill_body,
            runtime_contract=runtime_contract,
            context=context,
            payload=payload,
            project_root=project_root,
            skill_label=skill_label,
            inventory_data=inventory_data,
        )
    except RuntimeError as exc:
        return _error_payload(str(exc))


def _load_explore_skill(project_root: Path) -> tuple[str, dict[str, Any], str]:
    local_skill_path = project_root / 'skills' / 'explore' / 'SKILL.md'
    if local_skill_path.exists():
        content = local_skill_path.read_text(encoding='utf-8')
        skill_label = str(local_skill_path)
    else:
        try:
            resource = resources.files('skills.explore').joinpath('SKILL.md')
            content = resource.read_text(encoding='utf-8')
            skill_label = 'package:skills.explore/SKILL.md'
        except (FileNotFoundError, ModuleNotFoundError) as exc:
            raise RuntimeError('Explore skill not found in package resources.') from exc

    frontmatter, body = _split_frontmatter(content)
    runtime_contract = dict(DEFAULT_CONTRACT)
    extra_contract = frontmatter.get('runtime_contract') or {}
    if isinstance(extra_contract, dict):
        runtime_contract.update(
            {
                key: value
                for key, value in extra_contract.items()
                if key in DEFAULT_CONTRACT and isinstance(value, type(DEFAULT_CONTRACT[key]))
            }
        )
    return body.strip(), runtime_contract, skill_label


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r'^---\n(.*?)\n---\n?', text, re.DOTALL)
    if not match:
        return {}, text
    frontmatter = yaml.safe_load(match.group(1)) or {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return frontmatter, text[match.end():]


def _build_explore_prompt(
    question: str,
    skill_body: str,
    runtime_contract: dict[str, Any],
    context: dict[str, Any],
    retry_reason: str | None = None,
) -> str:
    payload = {
        'question': question,
        'runtime_contract': runtime_contract,
        'prepared_context': context,
    }

    preamble = [
        'You are the internal Sediment explore runtime.',
        'Treat the prepared KB context as the default starting path derived from root-first '
        'index routing. If your runtime supports white-box KB search, you may inspect '
        'additional KB indexes or entry files to verify or deepen the answer. Do not read '
        'raw materials outside the KB. Do not invent sources. Placeholder entries are weak '
        'evidence and must not be the only basis of an answer.',
        'Return JSON only. No prose before or after the JSON object.',
    ]
    if retry_reason:
        preamble.append(
            'Previous response was invalid. Fix it and return one valid JSON object only. '
            f'Failure reason: {retry_reason}'
        )

    return '\n\n'.join(
        [
            *preamble,
            skill_body,
            '## Prepared Context',
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    )


def _run_validated_explore(
    *,
    question: str,
    skill_body: str,
    runtime_contract: dict[str, Any],
    context: dict[str, Any],
    payload: dict[str, Any],
    project_root: Path,
    skill_label: str,
    inventory_data: dict[str, Any],
) -> dict[str, Any]:
    retry_reason = None

    for _ in range(2):
        prompt = _build_explore_prompt(
            question,
            skill_body,
            runtime_contract,
            context,
            retry_reason=retry_reason,
        )
        raw_output = _run_explore_cli(
            prompt=prompt,
            skill_body=skill_body,
            project_root=project_root,
            skill_label=skill_label,
            payload=payload,
            timeout_seconds=runtime_contract['cli_timeout_seconds'],
        )

        try:
            parsed_output = _parse_cli_json(raw_output)
        except RuntimeError:
            retry_reason = 'response was not a valid JSON object'
            continue

        validation = validate_answer(parsed_output, inventory_data=inventory_data)
        if validation['valid']:
            return validation['normalized']

        retry_reason = '; '.join(validation['errors'])

    raise RuntimeError(f'Explore runtime returned invalid JSON: {retry_reason}')


def _run_explore_cli(
    *,
    prompt: str,
    skill_body: str,
    project_root: Path,
    skill_label: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> str:
    cli_value = os.environ.get('SEDIMENT_CLI', 'claude').strip()
    if not cli_value:
        raise RuntimeError('SEDIMENT_CLI is empty; configure a CLI for explore runtime.')

    with tempfile.TemporaryDirectory(prefix='sediment-explore-') as temp_dir:
        temp_root = Path(temp_dir)
        prompt_file = temp_root / 'prompt.txt'
        payload_file = temp_root / 'payload.json'
        skill_file = temp_root / 'skill.md'
        prompt_file.write_text(prompt, encoding='utf-8')
        payload_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        skill_file.write_text(skill_body, encoding='utf-8')

        env = os.environ.copy()
        env.update(
            {
                'SEDIMENT_EXPLORE_PROMPT_FILE': str(prompt_file),
                'SEDIMENT_EXPLORE_PAYLOAD_FILE': str(payload_file),
                'SEDIMENT_EXPLORE_SKILL_FILE': str(skill_file),
                'SEDIMENT_EXPLORE_SKILL_LABEL': skill_label,
            }
        )

        command, stdin_data = _build_cli_command(
            cli_value=cli_value,
            prompt=prompt,
            prompt_file=prompt_file,
            payload_file=payload_file,
            skill_file=skill_file,
        )
        try:
            result = subprocess.run(
                command,
                input=stdin_data,
                text=True,
                capture_output=True,
                cwd=str(project_root),
                env=env,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f'Explore runtime CLI is unavailable: {exc.filename or cli_value}'
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f'Explore runtime timed out after {timeout_seconds} seconds.'
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            detail = stderr or stdout or f'exit code {result.returncode}'
            raise RuntimeError(f'Explore runtime CLI failed: {detail}')

        output = result.stdout.strip() or result.stderr.strip()
        if not output:
            raise RuntimeError('Explore runtime CLI returned no output.')
        return output


def _build_cli_command(
    *,
    cli_value: str,
    prompt: str,
    prompt_file: Path,
    payload_file: Path,
    skill_file: Path,
) -> tuple[list[str], str | None]:
    return build_cli_command(
        cli_value,
        prompt,
        prompt_file=prompt_file,
        payload_file=payload_file,
        skill_file=skill_file,
        extra_args=['--json-schema', _EXPLORE_JSON_SCHEMA],
    )


def _parse_cli_json(raw_output: str) -> dict[str, Any]:
    candidates = [raw_output.strip()]

    fenced = re.search(r'```json\s*(\{.*?\})\s*```', raw_output, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())

    start = raw_output.find('{')
    end = raw_output.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidates.append(raw_output[start:end + 1].strip())

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload

    raise RuntimeError('Explore runtime did not return a valid JSON object.')


def _error_payload(message: str) -> dict[str, Any]:
    return {
        'answer': message,
        'sources': [],
        'confidence': 'low',
        'exploration_summary': {
            'entries_scanned': 0,
            'entries_read': 0,
            'links_followed': 0,
            'mode': 'error',
        },
        'gaps': [message],
        'contradictions': [],
        'error': message,
    }


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
        body: dict[str, Any] | None = None
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
