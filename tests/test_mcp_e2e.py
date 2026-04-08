#!/usr/bin/env python3
"""
End-to-end tests for Sediment MCP Server (Task 5.1).
Tests knowledge_list and knowledge_read tools via JSON-RPC over stdin.
"""

import json
import subprocess
import sys
import time
import os

KB_PATH = "knowledge-base"
PYTHON = sys.executable


def json_rpc_call(method, params=None, msg_id=1):
    """Create a JSON-RPC request."""
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": method,
        "params": params or {},
    }


def tool_call(name, arguments=None, msg_id=1):
    """Create a tools/call request."""
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments or {},
        },
    }


def run_mcp_test(messages):
    """
    Send JSON-RPC messages to MCP server and return parsed responses.
    messages is a list of dicts (JSON-RPC messages).
    """
    input_text = "".join(json.dumps(msg) + "\n" for msg in messages)

    proc = subprocess.Popen(
        [PYTHON, "mcp_server/server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "SEDIMENT_KB_PATH": KB_PATH},
    )

    stdout, stderr = proc.communicate(input=input_text, timeout=15)

    responses = []
    for line in stdout.strip().split("\n"):
        if line.strip():
            try:
                responses.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return responses


def test_knowledge_list():
    """Test 1: knowledge_list() returns expected entries."""
    print("Test 1: knowledge_list()")

    messages = [
        json_rpc_call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1"},
            },
            1,
        ),
        tool_call("knowledge_list", {}, 2),
    ]

    responses = run_mcp_test(messages)

    call_response = None
    for resp in responses:
        if resp.get("id") == 2:
            call_response = resp
            break

    if call_response is None:
        print(f"  FAIL: No response for tools/call. Responses: {responses}")
        return False

    if "error" in call_response:
        print(f"  FAIL: Error in response: {call_response['error']}")
        return False

    result = call_response["result"]
    content = result.get("content", [])
    structured = result.get("structuredContent", {})

    # Try structuredContent first (FastMCP wraps list results here)
    if structured and "result" in structured:
        entries = structured["result"]
    elif content:
        # Fallback: parse from text content
        entries_text = content[0].get("text", "")
        try:
            entries = json.loads(entries_text)
        except json.JSONDecodeError:
            # If it's just a raw string (not JSON), treat as single entry
            entries = [entries_text] if entries_text else []
    else:
        print(f"  FAIL: Empty content in response")
        return False

    expected = {"示例-原子知识条目规范", "示例-候选链接规则", "示例-占位文件说明"}
    found = set(entries)
    if expected.issubset(found):
        print(f"  PASS: Found {len(entries)} entries including all expected ones")
        return True
    else:
        print(f"  FAIL: Expected {expected}, found {found}")
        return False


def test_knowledge_read_existing():
    """Test 2: knowledge_read returns correct content for existing entry."""
    print("Test 2: knowledge_read('示例-原子知识条目规范')")

    messages = [
        json_rpc_call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1"},
            },
            1,
        ),
        tool_call("knowledge_read", {"filename": "示例-原子知识条目规范"}, 2),
    ]

    responses = run_mcp_test(messages)

    call_response = None
    for resp in responses:
        if resp.get("id") == 2:
            call_response = resp
            break

    if call_response is None:
        print(f"  FAIL: No response")
        return False

    if "error" in call_response:
        print(f"  FAIL: Error: {call_response['error']}")
        return False

    content = call_response["result"].get("content", [])
    if not content:
        print(f"  FAIL: Empty content")
        return False

    text = content[0].get("text", "")
    if "原子知识条目规范" in text and "上下文" in text:
        print(f"  PASS: Content matches expected")
        return True
    else:
        print(f"  FAIL: Content doesn't match: {text[:200]}")
        return False


def test_knowledge_read_nonexistent():
    """Test 3: knowledge_read returns ERROR for nonexistent entry."""
    print("Test 3: knowledge_read('不存在')")

    messages = [
        json_rpc_call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1"},
            },
            1,
        ),
        tool_call("knowledge_read", {"filename": "不存在"}, 2),
    ]

    responses = run_mcp_test(messages)

    call_response = None
    for resp in responses:
        if resp.get("id") == 2:
            call_response = resp
            break

    if call_response is None:
        print(f"  FAIL: No response")
        return False

    if "error" in call_response:
        print(f"  FAIL: Unexpected error: {call_response['error']}")
        return False

    content = call_response["result"].get("content", [])
    if not content:
        print(f"  FAIL: Empty content")
        return False

    text = content[0].get("text", "")
    if "ERROR" in text and "不存在" in text:
        print(f"  PASS: Returns ERROR message as expected")
        return True
    else:
        print(f"  FAIL: Expected ERROR message, got: {text[:200]}")
        return False


def test_knowledge_list_realtime():
    """Test 4: knowledge_list reflects new files (no caching)."""
    print("Test 4: knowledge_list reflects new files (real-time)")

    test_file = f"{KB_PATH}/entries/测试-实时性.md"
    with open(test_file, "w") as f:
        f.write("# 测试-实时性\n\n这是一个测试条目。\n")

    try:
        messages = [
            json_rpc_call(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0.1"},
                },
                1,
            ),
            tool_call("knowledge_list", {}, 2),
        ]

        responses = run_mcp_test(messages)

        call_response = None
        for resp in responses:
            if resp.get("id") == 2:
                call_response = resp
                break

        if call_response is None:
            print(f"  FAIL: No response")
            return False

        content = call_response["result"].get("content", [])
        structured = call_response["result"].get("structuredContent", {})

        if structured and "result" in structured:
            entries = structured["result"]
        elif content:
            entries_text = content[0].get("text", "")
            try:
                entries = json.loads(entries_text)
            except json.JSONDecodeError:
                entries = [entries_text] if entries_text else []
        else:
            print(f"  FAIL: Empty content")
            return False

        if "测试-实时性" in entries:
            print(f"  PASS: New file '测试-实时性' appears in list")
            return True
        else:
            print(f"  FAIL: New file not found. Entries: {entries}")
            return False
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def main():
    print("=" * 50)
    print("Sediment MCP Server — End-to-End Tests (Task 5.1)")
    print("=" * 50)
    print()

    results = []
    results.append(("knowledge_list", test_knowledge_list()))
    results.append(("knowledge_read existing", test_knowledge_read_existing()))
    results.append(("knowledge_read nonexistent", test_knowledge_read_nonexistent()))
    results.append(("knowledge_list realtime", test_knowledge_list_realtime()))

    print()
    print("=" * 50)
    print("Results:")
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("All 4 tests passed!")
        sys.exit(0)
    else:
        print("Some tests failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
