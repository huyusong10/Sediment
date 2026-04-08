"""
Sediment MCP Server — exposes knowledge base tools to AI agents.

Tools:
  - knowledge_list:  list all entry names
  - knowledge_read:  read a single entry's content
  - knowledge_ask:   natural language query (requires CLI)
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# Add project root to path for importing tidy_utils
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from mcp.server import FastMCP

KB_PATH = os.environ.get("SEDIMENT_KB_PATH", "./knowledge-base")
CLI_CMD = os.environ.get("SEDIMENT_CLI", "opencode")

app = FastMCP("sediment")


def _entry_exists(filename: str) -> tuple[Path | None, str]:
    """
    Look up a filename (without .md) in entries/ then placeholders/.
    Returns (path, subdir) or (None, '').
    """
    for subdir in ("entries", "placeholders"):
        candidate = Path(KB_PATH) / subdir / f"{filename}.md"
        if candidate.exists():
            return candidate, subdir
    return None, ""


@app.tool()
def knowledge_list() -> list[str]:
    """
    返回知识库中所有条目的名称列表（不含 .md 后缀）。
    包含 entries/ 和 placeholders/ 下的所有 .md 文件。
    供调用方 Agent 推理相关文件名，是自主探索路径的入口。
    """
    result = set()
    for subdir in ("entries", "placeholders"):
        dir_path = Path(KB_PATH) / subdir
        if not dir_path.exists():
            continue
        for f in dir_path.glob("*.md"):
            result.add(f.stem)
    return sorted(result)


@app.tool()
def knowledge_read(filename: str) -> str:
    """
    读取指定知识条目的完整 Markdown 内容。
    filename 不含 .md 后缀。自动在 entries/ 和 placeholders/ 中查找。
    如果文件不存在，返回错误信息而非抛出异常。
    """
    # Path traversal guard
    if "/" in filename or "\\" in filename or ".." in filename:
        return f"ERROR: Invalid filename '{filename}'. Path separators are not allowed."

    path, _ = _entry_exists(filename)
    if path is None:
        return f"ERROR: Entry '{filename}' not found in knowledge base."

    return path.read_text(encoding="utf-8")


@app.tool()
def knowledge_ask(question: str) -> str:
    """
    针对知识库提出自然语言问题，由内部子 Agent 多轮推理后返回综合答案。
    返回格式：{ "answer": "...", "sources": ["条目名1", "条目名2"] }
    适合模糊语义问题，无法提前确定关键词时使用。
    """
    # Try to load the explore skill as system prompt
    explore_skill_path = project_root / "skills" / "explore.md"
    if not explore_skill_path.exists():
        return json.dumps(
            {
                "answer": "knowledge_ask unavailable: explore.md skill file not found. Use knowledge_list + knowledge_read for manual exploration.",
                "sources": [],
            }
        )

    explore_skill_content = explore_skill_path.read_text(encoding="utf-8")

    # Check if CLI command is available
    cli_path = subprocess.run(["which", CLI_CMD], capture_output=True, text=True)
    if cli_path.returncode != 0:
        return json.dumps(
            {
                "answer": "knowledge_ask unavailable: CLI not found. Use knowledge_list + knowledge_read for manual exploration.",
                "sources": [],
            }
        )

    try:
        cmd = [
            CLI_CMD,
            "--print",
            "--system",
            explore_skill_content,
            question,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        output = result.stdout.strip()

        # Try to parse JSON from output
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict) and "answer" in parsed:
                return json.dumps(parsed)
        except json.JSONDecodeError:
            pass

        # If not valid JSON, wrap the raw output
        return json.dumps(
            {
                "answer": output,
                "sources": [],
            }
        )

    except subprocess.TimeoutExpired:
        return json.dumps(
            {
                "answer": "knowledge_ask unavailable: request timed out. Use knowledge_list + knowledge_read for manual exploration.",
                "sources": [],
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "answer": f"knowledge_ask unavailable: {str(e)}. Use knowledge_list + knowledge_read for manual exploration.",
                "sources": [],
            }
        )


if __name__ == "__main__":
    app.run(transport="stdio")
