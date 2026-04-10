"""
isolated_build.py — Sediment 隔离构建脚本

封装项目隔离、KB 构建、MCP Server 启动的完整流程。
所有操作均在隔离目录内执行，确保不影响源码目录。

用法：
    # 完整构建并启动测试
    python isolated_build.py --build-type full
    python isolated_build.py --build-type batched

    # 仅创建隔离目录（不构建）
    python isolated_build.py --dry-run

    # 作为模块导入
    from isolated_build import IsolatedBuilder
    async with IsolatedBuilder() as builder:
        await builder.build_full()
        server = builder.start_mcp_server()
"""

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TESTCASE_DIR = PROJECT_ROOT / 'testcase'
MATERIAL_DIR = TESTCASE_DIR / 'material'

MCP_HOST = '127.0.0.1'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str):
    print(f"[isolated_build] {msg}", flush=True)


def chunk_list(lst: list, n: int) -> list[list]:
    """Split list into n roughly equal chunks."""
    k, m = divmod(len(lst), n)
    return [lst[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n)]


def get_material_files() -> list[Path]:
    """Get all material files, sorted for deterministic batching."""
    files = []
    for f in MATERIAL_DIR.rglob('*'):
        if f.is_file() and f.name != '.DS_Store':
            files.append(f)
    files.sort(key=lambda p: str(p))
    return files


# ---------------------------------------------------------------------------
# Material Extraction
# ---------------------------------------------------------------------------

def extract_material_text(file_path: Path) -> str:
    """Extract text content from a material file based on its extension."""
    ext = file_path.suffix.lower()

    if ext == '.md':
        return file_path.read_text(encoding='utf-8')

    if ext == '.txt':
        return file_path.read_text(encoding='utf-8')

    if ext == '.py':
        return _extract_python_docs(file_path)

    if ext in ('.cpp', '.h'):
        return _extract_cpp_docs(file_path)

    if ext == '.xml':
        return file_path.read_text(encoding='utf-8')

    if ext == '.yaml':
        return file_path.read_text(encoding='utf-8')

    if ext == '.json':
        return _extract_json_docs(file_path)

    if ext == '.puml':
        return file_path.read_text(encoding='utf-8')

    if ext == '.docx':
        try:
            from docx import Document
            doc = Document(file_path)
            return '\n'.join(p.text for p in doc.paragraphs)
        except ImportError:
            return f"[DOCX file: {file_path.name} - python-docx not installed]"

    if ext == '.pptx':
        try:
            from pptx import Presentation
            prs = Presentation(file_path)
            texts = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        texts.append(shape.text_frame.text)
            return '\n'.join(texts)
        except ImportError:
            return f"[PPTX file: {file_path.name} - python-pptx not installed]"

    return f"[Unsupported format: {ext}]"


def _extract_python_docs(file_path: Path) -> str:
    """Extract docstrings, comments, and signatures from Python files."""
    import ast

    source = file_path.read_text(encoding='utf-8')

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    parts = []

    if (tree.body and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)):
        parts.append(f"# 文件: {file_path.name}")
        parts.append(tree.body[0].value.value)
        parts.append("")

    comment_lines = []
    for i, line in enumerate(source.split('\n'), 1):
        stripped = line.strip()
        if stripped.startswith('#') and len(stripped) > 2:
            comment_lines.append(stripped.lstrip('# ').strip())

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = '类' if isinstance(node, ast.ClassDef) else '函数'
            sig = f"{kind}: {node.name}"
            docstring = ast.get_docstring(node) or ''

            if docstring or comment_lines:
                parts.append(f"## {sig}")
                if docstring:
                    parts.append(docstring)
                parts.append("")

    if comment_lines:
        parts.append("## 代码注释")
        parts.extend(comment_lines)

    result = '\n'.join(parts)

    if len(result) < 200:
        if len(source) > 8000:
            result = source[:4000] + "\n...[中间部分省略]...\n" + source[-4000:]
        else:
            result = source

    return result


def _extract_cpp_docs(file_path: Path) -> str:
    """Extract comments and signatures from C++ files."""
    source = file_path.read_text(encoding='utf-8')

    block_comments = re.findall(r'/\*(.*?)\*/', source, re.DOTALL)
    line_comments = re.findall(r'//\s*(.+)', source)
    signatures = re.findall(r'(?:class|struct|namespace|enum)\s+(\w+)', source)
    func_sigs = re.findall(r'(\w+)\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?(?:\{|;)', source)

    parts = [f"# 文件: {file_path.name}"]

    if block_comments:
        parts.append("## 块注释")
        parts.extend(c.strip() for c in block_comments if c.strip())

    if line_comments:
        parts.append("## 行注释")
        parts.extend(line_comments)

    if signatures:
        parts.append("## 类型定义")
        parts.extend(f"- {s}" for s in signatures)

    if func_sigs:
        parts.append("## 函数")
        parts.extend(f"- {f}" for f in func_sigs)

    result = '\n'.join(parts)

    if len(result) < 200:
        if len(source) > 8000:
            result = source[:4000] + "\n...[中间部分省略]...\n" + source[-4000:]
        else:
            result = source

    return result


def _extract_json_docs(file_path: Path) -> str:
    """Extract meaningful domain knowledge from JSON files."""
    source = file_path.read_text(encoding='utf-8')

    try:
        data = json.loads(source)
    except json.JSONDecodeError:
        return source

    def extract_keys(obj, prefix=''):
        parts = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    parts.append(f"{full_key}: (object)")
                    parts.extend(extract_keys(value, full_key))
                elif isinstance(value, list):
                    if value and isinstance(value[0], dict):
                        parts.append(f"{full_key}: (array of {len(value)} objects)")
                        parts.extend(extract_keys(value[0], f"{full_key}[0]"))
                    else:
                        sample = str(value[:5])
                        parts.append(f"{full_key}: {sample}")
                elif isinstance(value, (str, int, float, bool)):
                    parts.append(f"{full_key}: {value}")
                else:
                    parts.append(f"{full_key}: {type(value).__name__}")
        return parts

    lines = [f"# 文件: {file_path.name}"]

    if isinstance(data, dict):
        if 'metrics' in data and isinstance(data['metrics'], list):
            lines.append(f"\n## 概述")
            lines.append(f"文件描述: {data.get('description', '')}")
            lines.append(f"版本: {data.get('version', '')}")
            lines.append(f"维护者: {data.get('maintainer', '')}")
            lines.append(f"\n## 指标定义详情")
            lines.append(f"该文件定义了系统中所有关键监控指标的元数据。")
            for metric in data['metrics']:
                name = metric.get('name', '未知')
                code = metric.get('code', '')
                desc = metric.get('description', '')
                unit = metric.get('unit', '')
                lines.append(f"\n### {name} ({code})")
                lines.append(f"- 描述: {desc}")
                lines.append(f"- 单位: {unit}")
        elif 'nodes' in data and isinstance(data['nodes'], list):
            lines.append(f"\n## 部署拓扑")
            lines.append(f"文件描述: {data.get('description', '')}")
            for node in data['nodes']:
                nid = node.get('id', '')
                role = node.get('role', '')
                zone = node.get('zone', '')
                lines.append(f"- {nid}: 角色={role}, 区域={zone}")
        else:
            lines.append("## 数据结构")
            for key, value in data.items():
                if isinstance(value, dict):
                    lines.append(f"\n### {key}")
                    for line in extract_keys(value, key):
                        lines.append(f"- {line}")
                elif isinstance(value, list):
                    lines.append(f"\n### {key} ({len(value)} items)")
    elif isinstance(data, list):
        lines.append(f"## 数组 ({len(data)} items)")

    result = '\n'.join(lines)

    if len(result) < 200:
        if len(source) > 8000:
            result = source[:4000] + "\n...[中间部分省略]...\n" + source[-4000:]
        else:
            result = source

    return result


# ---------------------------------------------------------------------------
# Ingest Prompt Builder
# ---------------------------------------------------------------------------

def build_ingest_prompt(materials: list[Path], isolated_dir: Path) -> str:
    """Build the ingest prompt for Claude."""
    parts = []
    parts.append("""你是一个知识摄入 Agent (Sediment Ingest)。
目标：将给定文档提炼为原子知识条目，存入知识库。

知识库路径：knowledge-base/
- 正式条目存入：knowledge-base/entries/
- 占位文件存入：knowledge-base/placeholders/

══════════════════════════════════════════════
核心规则（最重要，优先遵守）
══════════════════════════════════════════════

1. 每个领域概念/术语/设备/指标/角色/流程 都必须有独立条目
2. 条目的第一行（核心命题）必须是对该概念的完整定义，格式为："XX是/指/用于……"
3. 核心命题必须包含该概念的所有关键特征、属性、数值阈值、关联指标
4. 条目中禁止出现代码片段、XML/JSON/YAML原始数据、图表ASCII艺术
5. 文件名就是概念的标准名称，使用领域中最常见的叫法
6. **定义段中禁止使用任何 Markdown 格式标记（如 **加粗**、*斜体* 等），保持纯文本**
7. **定义段应当精炼简洁，2-3句话即可，不要包含长列表、数值明细或流程步骤**
8. **数值参数、流程步骤、配置明细等详细信息应当放在"## 上下文"部分，不要塞进定义段**

══════════════════════════════════════════════
条目结构（严格遵守）
══════════════════════════════════════════════

---
aliases: [别名1, 别名2]
tags: [概念类型]
status: formal
---
# 概念标准名称

[定义：一句话说明"这是什么" + "它做什么/有什么特征" + "与什么相关概念有关联"。必须包含该概念的所有关键术语、数值参数、阈值。]

## 上下文
[适用场景、前提条件、触发条件、运行时行为、异常处理机制]

## 关联
[[相关概念1]] [[相关概念2]] [[相关概念3]]

## 来源
[[来源文件名]]

══════════════════════════════════════════════
别名规则
══════════════════════════════════════════════
aliases 字段必填，包含：
- 该概念在文档中的其他叫法/缩写
- 同义词或相近概念
- 英文对照（如有）

══════════════════════════════════════════════
内容要求（关键！）
══════════════════════════════════════════════

每个条目必须尽可能包含以下信息（如文档中有提到）：
- 数值参数：阈值、范围、默认值、单位、异常值
- 触发条件：什么情况下会触发/启动/激活
- 关联行为：与其他概念的交互关系、因果链
- 异常/故障：失败模式、错误码、应急措施
- 流程步骤：如果是流程类概念，需包含步骤/阶段/顺序
- 角色职责：如果是角色类概念，需包含职责/权限/操作

对于流程/操作类概念，条目需要包含：
- 前置条件（什么情况下执行）
- 执行步骤/阶段
- 结果/产物
- 异常处理（失败时怎么办）
- 关联的其他概念

══════════════════════════════════════════════
定义段写作规范（关键！）
══════════════════════════════════════════════

条目的定义段（frontmatter 和标题之后的第一段）是最重要的部分。写作时必须遵守以下模式：

**设备类**：XX是用于[功能]的[设备类型]，是系统主要的[作用]来源。
**指标类**：XX是衡量[对象]的[指标类型]。XX数值越高/越低，表示[含义]。
**角色类**：XX是负责[职责]的[角色类型]，拥有[权限]。
**现象类**：XX是[原因]导致的[现象类型]，可能导致[后果]。需要[应对方式]来应对。
**系统类**：XX是[功能描述]的[系统类型]，负责[职责列举]和[其他职责]。
**流程类**：XX是[触发时机/条件]的[流程类型]。包括[步骤列举]等操作，确保[目标]。
**物质/资源类**：XX是系统的[本质属性]，也是系统的[重要性]。所有运作都围绕XX的[活动]展开。
**容器类**：XX是[功能]的[容器类型]，是系统的[组成地位]，负责[职责]。
**副产物类**：XX是[原因]后形成的[性质]副产物。它会[危害]，甚至可能导致[严重后果]。

**定义段禁止事项**：
- 禁止使用 ** 或 * 等 Markdown 格式标记
- 禁止在定义段中包含数值列表、配置参数、流程步骤（这些放在上下文部分）
- 禁止使用括号补充说明（直接写入正文）
- 定义段控制在 2-4 句话

══════════════════════════════════════════════
处理流程
══════════════════════════════════════════════
1. 通读文档，识别所有领域概念
2. 对每个概念，提取其定义、特征、关联、参数、阈值、触发条件
3. 逐个生成 .md 文件到 entries/
4. 对文档中提到但无法在文档内解释的概念，在 placeholders/ 创建占位文件

重要：
- 不要判断命题是否已在知识库中，直接写入。去重在 tidy 阶段处理
- 不要读取已有条目。保持摄入成本恒定
- 宁可拆得太细，不要太粗
- 每个条目必须能独立理解，不依赖其他条目

请依次处理以下文档，为每份文档中出现的所有领域概念创建知识条目：
""")

    for f in materials:
        content = extract_material_text(f)
        if len(content) > 8000:
            content = content[:4000] + "\n...[中间部分省略]...\n" + content[-4000:]
        parts.append(f"\n{'='*60}\n文件: {f.relative_to(MATERIAL_DIR)}\n{'='*60}\n{content}\n")

    return '\n'.join(parts)


def build_tidy_prompt(kb_dir: Path) -> str:
    """Build the tidy prompt for Claude."""
    entry_count = len(list((kb_dir / 'entries').glob('*.md')))
    placeholder_count = len(list((kb_dir / 'placeholders').glob('*.md')))

    return f"""你是一个知识整理 Agent (Sediment Tidy)。
目标：提升知识库的内部一致性和条目质量。知识库路径：{kb_dir}

当前知识库中有 {entry_count} 个条目和 {placeholder_count} 个占位文件。

请执行以下整理操作：

1. 确认候选链接：
   - 扫描 entries/ 下所有 .md 文件中的 [[链接]]
   - 对每个链接目标，如果 entries/ 和 placeholders/ 中都不存在对应文件，创建占位文件
   - 占位文件内容：# 概念名\\n\\n> 状态：占位（待填充）\\n\\n该概念被多个条目引用但尚未形成正式定义。

2. 合并重复条目：
   - 检查 entries/ 下是否有描述同一概念或多个高度相似的条目
   - 如果存在重复，保留内容更丰富、定义更清晰的那份
   - 删除内容较少的重复文件
   - 注意：文件名不同但含义相同的条目也要合并

3. 补充孤立节点：
   - 检查 entries/ 下是否有条目不包含任何 [[链接]] 也没有被其他条目链接
   - 如果有，为其补充适当的 [[关联]] 链接

4. 质量检查：
   - 确保每个条目的第一行是对该概念的完整定义
   - 确保每个条目都有 aliases 字段
   - 确保关联链接数量合理（1-8个）

完成后请汇报整理结果，包括：新增占位数、合并条目数、补充链接数。
"""


# ---------------------------------------------------------------------------
# Ingest & Tidy Execution
# ---------------------------------------------------------------------------

async def run_ingest(isolated_dir: Path, materials: list[Path]) -> bool:
    """Run ingest using claude -p with retry logic."""
    kb_entries = isolated_dir / 'knowledge-base' / 'entries'
    kb_entries.mkdir(parents=True, exist_ok=True)

    MAX_RETRIES = 2

    for attempt in range(1, MAX_RETRIES + 1):
        prompt = build_ingest_prompt(materials, isolated_dir)

        cmd = [
            'claude', '-p',
            '--permission-mode', 'auto',
            '--allowed-tools', 'Write', 'Edit', 'Bash', 'Read', 'Glob',
            '--max-budget-usd', '10',
            '--no-session-persistence',
            prompt,
        ]

        env = os.environ.copy()
        env['SEDIMENT_KB_PATH'] = str(isolated_dir / 'knowledge-base')
        env['CLAUDE_CODE'] = '1'

        log(f"Running ingest for {len(materials)} files (attempt {attempt}/{MAX_RETRIES})...")
        start = time.time()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(isolated_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            elapsed = time.time() - start
            entry_count = len(list(kb_entries.glob('*.md')))
            log(f"Ingest complete in {elapsed:.1f}s. Created {entry_count} entries.")

            if proc.returncode != 0:
                log(f"Warning: claude exited with code {proc.returncode}")
                log(f"stderr: {stderr.decode()[:500]}")
                if attempt < MAX_RETRIES:
                    log("Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                    continue

            return entry_count > 0

        except Exception as e:
            log(f"Ingest attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                log("Retrying in 5 seconds...")
                await asyncio.sleep(5)
                continue
            return False

    return False


async def run_tidy(isolated_dir: Path) -> bool:
    """Run tidy using claude -p with retry logic."""
    kb_dir = isolated_dir / 'knowledge-base'
    if not kb_dir.exists():
        return False

    entry_count = len(list((kb_dir / 'entries').glob('*.md')))
    placeholder_count = len(list((kb_dir / 'placeholders').glob('*.md')))
    log(f"Running tidy. Current: {entry_count} entries, {placeholder_count} placeholders.")

    MAX_RETRIES = 2

    for attempt in range(1, MAX_RETRIES + 1):
        prompt = build_tidy_prompt(kb_dir)

        cmd = [
            'claude', '-p',
            '--permission-mode', 'auto',
            '--allowed-tools', 'Write', 'Edit', 'Bash', 'Read', 'Glob',
            '--max-budget-usd', '5',
            '--no-session-persistence',
            prompt,
        ]

        env = os.environ.copy()
        env['SEDIMENT_KB_PATH'] = str(kb_dir)

        log(f"Tidy attempt {attempt}/{MAX_RETRIES}...")
        start = time.time()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(isolated_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            elapsed = time.time() - start
            new_entry_count = len(list((kb_dir / 'entries').glob('*.md')))
            new_placeholder_count = len(list((kb_dir / 'placeholders').glob('*.md')))
            log(f"Tidy complete in {elapsed:.1f}s. Now: {new_entry_count} entries, {new_placeholder_count} placeholders.")

            if proc.returncode != 0:
                log(f"Warning: tidy exited with code {proc.returncode}")
                if attempt < MAX_RETRIES:
                    log("Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                    continue

            return True

        except Exception as e:
            log(f"Tidy attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                log("Retrying in 5 seconds...")
                await asyncio.sleep(5)
                continue
            return False

    return False


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

class MCPServer:
    """Manages the MCP server process, running inside the isolated directory."""

    def __init__(self, kb_path: Path, port: int, isolated_dir: Path):
        self.kb_path = kb_path
        self.port = port
        self.isolated_dir = isolated_dir
        self.process = None
        self.base_url = f'http://{MCP_HOST}:{port}'
        self.sse_url = f'{self.base_url}/sediment/'

    async def start(self):
        """Start the MCP server."""
        # Kill any existing process on the target port
        try:
            proc = await asyncio.create_subprocess_exec(
                'lsof', '-ti', f':{self.port}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if stdout:
                for pid in stdout.decode().strip().split('\n'):
                    pid = pid.strip()
                    if pid:
                        log(f"Killing existing process on port {self.port}: PID {pid}")
                        await asyncio.create_subprocess_exec('kill', '-9', pid)
                        await asyncio.sleep(0.5)
        except Exception:
            pass

        env = os.environ.copy()
        env['SEDIMENT_KB_PATH'] = str(self.kb_path)
        env['SEDIMENT_PORT'] = str(self.port)
        env['SEDIMENT_HOST'] = MCP_HOST
        # Ensure Python can find mcp_server module from the isolated directory
        env['PYTHONPATH'] = str(self.isolated_dir)

        venv_python = self.isolated_dir / '.venv' / 'bin' / 'python'
        if venv_python.exists():
            cmd = [
                str(venv_python), '-m', 'mcp_server.server',
            ]
        else:
            # Use 'uv run' directly with the uv binary
            cmd = [
                'uv', 'run', 'python', '-m', 'mcp_server.server',
            ]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.isolated_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for server to be ready
        import httpx
        for i in range(120):
            await asyncio.sleep(0.5)
            try:
                async with httpx.AsyncClient(timeout=2) as client:
                    resp = await client.post(
                        self.sse_url,
                        json={
                            'jsonrpc': '2.0',
                            'id': 1,
                            'method': 'tools/list',
                        },
                        headers={'Content-Type': 'application/json'},
                    )
                    if resp.status_code == 200:
                        log(f"MCP server ready on port {self.port}")
                        return True
            except Exception:
                continue

        log("MCP server failed to start")
        return False

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call an MCP tool via direct JSON-RPC."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    self.sse_url,
                    json={
                        'jsonrpc': '2.0',
                        'id': random.randint(1, 10000),
                        'method': 'tools/call',
                        'params': {
                            'name': tool_name,
                            'arguments': arguments,
                        },
                    },
                    headers={'Content-Type': 'application/json'},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get('result', {})
                    content = result.get('content', [])
                    if content:
                        return content[0].get('text', '')
                    return json.dumps(result, ensure_ascii=False)
                return f"HTTP {resp.status_code}"
        except Exception as e:
            return f"ERROR: {e}"

    async def stop(self):
        """Stop the MCP server."""
        if self.process:
            try:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    self.process.kill()
            except ProcessLookupError:
                pass  # Process already exited
            log(f"MCP server on port {self.port} stopped")


# ---------------------------------------------------------------------------
# IsolatedBuilder: Main orchestrator
# ---------------------------------------------------------------------------

class IsolatedBuilder:
    """
    Manages the full lifecycle: create isolated copy → build KB → start MCP → cleanup.

    Usage as context manager:
        async with IsolatedBuilder(build_type='full') as builder:
            server = builder.mcp_server
            # use server for testing...
    """

    def __init__(self, build_type: str = 'full', port: int = 18800):
        self.build_type = build_type
        self.port = port
        self.isolated_dir: Path | None = None
        self.kb_dir: Path | None = None
        self.mcp_server: MCPServer | None = None

    async def __aenter__(self):
        await self.create_isolated_copy()
        await self.build()
        return self

    async def __aexit__(self, *args):
        await self.cleanup()

    async def create_isolated_copy(self) -> Path:
        """Create an isolated copy of the project."""
        self.isolated_dir = Path(tempfile.mkdtemp(prefix=f'sediment-{self.build_type}-'))
        log(f"Isolated dir: {self.isolated_dir}")

        shutil.copytree(
            PROJECT_ROOT, self.isolated_dir, dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                '.git', '__pycache__', '*.pyc',
                'testcase/results', '.claude', 'node_modules',
            ),
        )

        # Ensure KB directories exist
        self.kb_dir = self.isolated_dir / 'knowledge-base'
        self.kb_dir.mkdir(exist_ok=True)
        (self.kb_dir / 'entries').mkdir(exist_ok=True)
        (self.kb_dir / 'placeholders').mkdir(exist_ok=True)

        return self.isolated_dir

    async def build(self):
        """Execute the build pipeline based on build_type."""
        if self.build_type == 'full':
            await self.build_full()
        elif self.build_type == 'batched':
            await self.build_batched()
        else:
            raise ValueError(f"Unknown build_type: {self.build_type}")

    async def build_full(self):
        """Full build: ingest all files in a single claude -p call, tidy once at end."""
        materials = get_material_files()
        log(f"\n--- Ingest all {len(materials)} files ---")
        success = await run_ingest(self.isolated_dir, materials)
        if not success:
            log("Full ingest failed")

        await run_tidy(self.isolated_dir)

    async def build_batched(self):
        """Batched build: ingest 1/5 at a time, tidy after each."""
        materials = get_material_files()
        batches = chunk_list(materials, 5)
        for i, batch in enumerate(batches):
            log(f"\n--- Batch {i + 1}/5 ---")
            success = await run_ingest(self.isolated_dir, batch)
            if success:
                await run_tidy(self.isolated_dir)
            await asyncio.sleep(1)

    def start_mcp_server(self, port: int | None = None) -> MCPServer:
        """Start the MCP server. Returns the server instance."""
        if port is None:
            port = self.port
        self.mcp_server = MCPServer(self.kb_dir, port, self.isolated_dir)
        return self.mcp_server

    async def cleanup(self):
        """Stop MCP server, clean up background processes, remove isolated directory."""
        # Kill any lingering claude subprocesses spawned in this isolated dir
        try:
            pkill_proc = await asyncio.create_subprocess_exec(
                'pkill', '-f', str(self.isolated_dir),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await pkill_proc.wait()
        except Exception:
            pass

        if self.mcp_server:
            await self.mcp_server.stop()
            self.mcp_server = None
        if self.isolated_dir and self.isolated_dir.exists():
            try:
                shutil.rmtree(self.isolated_dir, ignore_errors=True)
                log(f"Cleaned up: {self.isolated_dir}")
            except Exception as e:
                log(f"Cleanup warning: {e}")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description='Sediment Isolated Build')
    parser.add_argument(
        '--build-type', choices=['full', 'batched'], default='full',
        help='Build type: full (single ingest + tidy) or batched (5-batch with tidy each)',
    )
    parser.add_argument('--port', type=int, default=18800, help='MCP server port')
    parser.add_argument('--dry-run', action='store_true', help='Only create isolated copy, skip build')
    parser.add_argument('--no-cleanup', action='store_true', help='Keep isolated directory after build (for debugging)')
    args = parser.parse_args()

    log(f"Build type: {args.build_type}")
    log(f"Project root: {PROJECT_ROOT}")
    log(f"Material files: {len(get_material_files())}")

    builder = IsolatedBuilder(build_type=args.build_type, port=args.port)

    try:
        await builder.create_isolated_copy()

        if not args.dry_run:
            await builder.build()

            # Report KB status
            entry_count = len(list((builder.kb_dir / 'entries').glob('*.md')))
            placeholder_count = len(list((builder.kb_dir / 'placeholders').glob('*.md')))
            log(f"\nBuild complete: {entry_count} entries, {placeholder_count} placeholders")
            log(f"KB path: {builder.kb_dir}")

            # Optionally start MCP server for quick testing
            log("\nTo test with the MCP server, run:")
            log(f"  export SEDIMENT_KB_PATH={builder.kb_dir}")
            log(f"  cd {builder.isolated_dir}")
            log(f"  python -m mcp_server.server --port {args.port}")
        else:
            log(f"\nDry run complete. Isolated dir: {builder.isolated_dir}")

        if args.no_cleanup:
            log(f"\nIsolated directory preserved: {builder.isolated_dir}")
            log("Remember to clean up manually: rm -rf " + str(builder.isolated_dir))
            # Don't cleanup
            builder.isolated_dir = None
    finally:
        if not args.no_cleanup:
            await builder.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
