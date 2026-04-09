# Sediment — Build Plan

> 本文档是给执行 Agent 的施工计划。设计原则和背景见 `tacit_knowledge_system_v3.md`。
> 按 Phase 顺序执行，每个 Task 完成后做验收检查再继续。

---

## 项目结构总览

```
sediment/
├── README.md
├── mcp_server/
│   ├── server.py              # MCP Server 主程序
│   └── requirements.txt
├── scripts/
│   ├── tidy_utils.py          # 整理辅助函数（无状态）
│   └── health_check.py        # 巡检脚本
├── skills/
│   ├── ingest.md              # UC1 摄入 Skill
│   ├── tidy.md                # UC2 整理 Skill
│   └── explore.md             # 知识库探索协议 Skill
└── knowledge-base/            # 知识库（示例结构）
    ├── entries/
    │   └── .gitkeep
    ├── placeholders/
    │   └── .gitkeep
    └── sources/
        └── source_map.json
```

---

## Phase 1：项目脚手架

### Task 1.1 — 初始化仓库

创建以下文件和目录结构：

```
sediment/
├── README.md                  （见下方内容要求）
├── mcp_server/
│   └── requirements.txt       （见下方内容要求）
├── scripts/
├── skills/
└── knowledge-base/
    ├── entries/.gitkeep
    ├── placeholders/.gitkeep
    └── sources/source_map.json （初始内容：空对象 {}）
```

**README.md 内容要求**：
- 项目名：Sediment
- 一句话描述：Tacit knowledge extraction system for AI Agents — turns complex unstructured documents into a structured, human-reviewable knowledge base.
- 包含以下章节：What it does / Quick Start / Components / License (MIT)
- Quick Start 暂时写 placeholder，后续 Phase 完成后补充

**requirements.txt 内容**：
```
mcp>=1.0.0
```

**验收**：`ls -R sediment/` 输出结构与上方一致，source_map.json 内容为 `{}`

---

### Task 1.2 — 创建知识库示例条目

在 `knowledge-base/entries/` 下创建 3 个示例 .md 文件，用于后续测试：

**文件 1：`knowledge-base/entries/示例-原子知识条目规范.md`**
```markdown
# 示例-原子知识条目规范

每个知识条目只包含一个可独立表述的命题。宁可拆太细，不要在一个文件里包含多个命题。

## 上下文
适用于所有摄入和整理操作。

## 来源
[[Sediment设计文档]]

## 关联
[[示例-占位文件说明]] [[示例-候选链接规则]]
```

**文件 2：`knowledge-base/placeholders/示例-占位文件说明.md`**
```markdown
# 示例-占位文件说明

> 状态：占位（待填充）
> 出现于：[[示例-原子知识条目规范]]

该概念在文档中被引用，但尚未形成正式定义。
建议在下次整理时执行归纳推理。
```

**文件 3：`knowledge-base/entries/示例-候选链接规则.md`**
```markdown
# 示例-候选链接规则

摄入时，所有专有名词和领域概念标记为 [[候选链接]]。
通用词汇（系统、用户、数据等）不标记。

## 关联
[[示例-原子知识条目规范]]
```

**验收**：3 个文件存在，内容格式正确，链接结构形成一个小网络

---

## Phase 2：Python 辅助脚本

### Task 2.1 — 实现 tidy_utils.py

文件路径：`scripts/tidy_utils.py`

实现以下四个函数，**全部无状态，每次实时从文件系统计算**：

```python
def find_dangling_links(kb_path: str) -> list[dict]:
    """
    扫描 entries/ 和 placeholders/ 下所有 .md 文件中的 [[链接]]。
    返回目标文件不存在的链接列表。
    
    返回格式：
    [
        {
            "link": "概念名",
            "source_file": "entries/某条目.md",
            "context": "包含该链接的那一行文本"
        },
        ...
    ]
    
    实现要点：
    - 用正则 r'\[\[([^\]]+)\]\]' 提取所有链接目标
    - 链接目标对应文件：在 entries/{name}.md 或 placeholders/{name}.md 中查找
    - 两个位置都不存在则为 dangling link
    - 去重：同一个 link 在多个文件中出现，每次出现单独记录
    """

def count_placeholder_refs(kb_path: str) -> list[dict]:
    """
    统计 placeholders/ 下每个占位文件被引用的次数。
    被引用 = 在 entries/ 或 placeholders/ 的任意 .md 文件中出现 [[文件名]]。
    
    返回格式（按引用次数降序排列）：
    [
        {
            "placeholder": "概念名",
            "ref_count": 7,
            "referenced_by": ["entries/条目A.md", "entries/条目B.md", ...]
        },
        ...
    ]
    """

def find_orphan_entries(kb_path: str) -> list[str]:
    """
    检测 entries/ 下没有任何入链（被别人引用）且没有出链（引用别人）的条目。
    
    返回格式：
    ["entries/孤立条目A.md", "entries/孤立条目B.md", ...]
    
    实现要点：
    - 出链：该文件内容中包含 [[任何链接]]
    - 入链：其他文件内容中包含 [[该文件名]]
    - 两者都没有才算孤立
    """

def collect_ref_contexts(kb_path: str, placeholder_name: str) -> list[str]:
    """
    收集指定占位概念在所有条目中被引用的上下文片段。
    用于归纳推理时给 LLM 提供材料。
    
    参数：placeholder_name 是概念名，不含路径和 .md 后缀
    
    返回格式：
    [
        "来源：entries/条目A.md\n上下文：...包含[[概念名]]的前后3行...",
        "来源：entries/条目B.md\n上下文：...包含[[概念名]]的前后3行...",
        ...
    ]
    """
```

**验收**：
```bash
cd sediment
python -c "
from scripts.tidy_utils import *
kb = 'knowledge-base'
print('dangling:', find_dangling_links(kb))
print('placeholder refs:', count_placeholder_refs(kb))
print('orphans:', find_orphan_entries(kb))
print('contexts:', collect_ref_contexts(kb, '示例-占位文件说明'))
"
```
输出应当：dangling links 为空（所有链接目标存在），placeholder refs 显示示例-占位文件说明被引用1次，orphans 为空，contexts 返回至少1条片段。

---

### Task 2.2 — 实现 health_check.py

文件路径：`scripts/health_check.py`

**调用方式**：`python scripts/health_check.py <kb_path>`

**实现要求**：
- 调用 tidy_utils 中的函数计算所有指标
- 输出格式严格如下（纯文本，写入 stdout）：

```
Sediment Knowledge Base — Health Report
========================================
Generated: 2024-01-15 10:30:00

SUMMARY
-------
Total entries:       12  (formal: 10, placeholders: 2)

PLACEHOLDER REFS
----------------
High (>=5):    0
Medium (2-4):  1
  - 示例-占位文件说明 (1 refs)
Low (1):       1

ORPHAN ENTRIES
--------------
Count: 0

DANGLING LINKS
--------------
Count: 0

RECOMMENDATION
--------------
Knowledge base looks healthy. Consider ingesting more documents.
```

RECOMMENDATION 规则：
- 有高引用占位文件（>=5次）→ "Run tidy with induction mode. Focus on N high-ref placeholders."
- 有孤立节点 → "Run tidy to add missing links for N orphan entries."
- 有悬空链接 → "Run tidy to resolve N dangling links."
- 都没有 → "Knowledge base looks healthy. Consider ingesting more documents."
- 多个问题同时存在时，全部列出

**验收**：
```bash
python scripts/health_check.py knowledge-base
```
输出符合上述格式，数字与示例文件的实际状态一致。

---

## Phase 3：MCP Server

### Task 3.1 — 实现 MCP Server 框架

文件路径：`mcp_server/server.py`

使用 Python `mcp` 库实现，暴露三个工具。

**服务器基础结构**：

```python
import os
import sys
import json
import subprocess
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# KB_PATH 从环境变量读取，默认值为 ./knowledge-base
KB_PATH = os.environ.get("SEDIMENT_KB_PATH", "./knowledge-base")

app = Server("sediment")

# 在此实现三个工具（见 Task 3.2 - 3.4）

if __name__ == "__main__":
    import asyncio
    asyncio.run(stdio_server(app))
```

**验收**：`python mcp_server/server.py` 启动不报错，进程保持运行

---

### Task 3.2 — 实现 knowledge_list 工具

在 `mcp_server/server.py` 中添加：

```python
@app.tool()
async def knowledge_list() -> list[str]:
    """
    返回知识库中所有条目的名称列表（不含 .md 后缀）。
    包含 entries/ 和 placeholders/ 下的所有 .md 文件。
    供调用方 Agent 推理相关文件名，是自主探索路径的入口。
    """
```

实现要点：
- 扫描 `{KB_PATH}/entries/` 和 `{KB_PATH}/placeholders/` 下所有 `.md` 文件
- 返回文件名列表，去掉 `.md` 后缀，不含路径前缀
- 两个目录的结果合并，去重，按字母排序

**验收**：通过 MCP 调用 knowledge_list，返回包含 3 个示例条目名称的列表

---

### Task 3.3 — 实现 knowledge_read 工具

```python
@app.tool()
async def knowledge_read(filename: str) -> str:
    """
    读取指定知识条目的完整 Markdown 内容。
    filename 不含 .md 后缀。自动在 entries/ 和 placeholders/ 中查找。
    如果文件不存在，返回错误信息而非抛出异常。
    """
```

实现要点：
- 先在 `{KB_PATH}/entries/{filename}.md` 查找
- 不存在则在 `{KB_PATH}/placeholders/{filename}.md` 查找
- 两处都不存在则返回：`"ERROR: Entry '{filename}' not found in knowledge base."`
- 文件名中不允许包含路径分隔符（防止路径穿越），检测到则返回错误

**验收**：
- `knowledge_read("示例-原子知识条目规范")` 返回正确的 Markdown 内容
- `knowledge_read("不存在的条目")` 返回 ERROR 信息而非崩溃

---

### Task 3.4 — 实现 knowledge_ask 工具

```python
@app.tool()
async def knowledge_ask(question: str) -> str:
    """
    针对知识库提出自然语言问题，由内部子 Agent 多轮推理后返回综合答案。
    返回格式：{ "answer": "...", "sources": ["条目名1", "条目名2"] }
    适合模糊语义问题，无法提前确定关键词时使用。
    """
```

实现要点：

1. 读取 `skills/explore.md` 的内容作为子 Agent 的 system prompt
2. 通过 subprocess 调用 CLI：
   ```python
   cmd = [
       "claude",  # 或从环境变量 SEDIMENT_CLI 读取
       "--print",   # 非交互模式，输出结果后退出
       "--system", explore_skill_content,
       question
   ]
   result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
   ```
3. 解析输出，提取 answer 和 sources
4. 如果 CLI 不可用或超时，降级返回：
   ```json
   {
     "answer": "knowledge_ask unavailable: CLI not found. Use knowledge_list + knowledge_read for manual exploration.",
     "sources": []
   }
   ```

注意：CLI 命令名通过环境变量 `SEDIMENT_CLI` 配置，默认为 `claude`。

**验收**：
- 环境中有 CLI 时：`knowledge_ask("示例条目规范是什么")` 返回包含 answer 和 sources 的 JSON
- 环境中无 CLI 时：返回降级响应，不崩溃

---

## Phase 4：Skills 文件

### Task 4.1 — 编写 ingest.md（摄入 Skill）

文件路径：`skills/ingest.md`

**内容要求**（直接可用作 system prompt）：

```markdown
# Sediment Ingest Skill

You are a knowledge ingestion agent for Sediment.

## Goal
Extract atomic knowledge entries from the given document and write them into the knowledge base.

## Knowledge Base Path
Set by environment variable SEDIMENT_KB_PATH (default: ./knowledge-base)
- Formal entries: entries/
- Placeholder entries: placeholders/
- Source map: sources/source_map.json

## Atomization Rules
- One proposition = one file. When in doubt, split rather than merge.
- File name = the proposition title. Use natural language that an agent would naturally think of when reasoning about this topic.
- Core proposition: 1-3 sentences max, 150 characters max. No meta-phrases like "This document introduces...".
- Mark all domain-specific nouns and concepts as [[candidate links]].
- Do NOT mark generic words (system, user, data, process...) as links.
- If a concept appears but is not explained in the document, create a placeholder file for it.

## Entry Structure
~~~markdown
# [filename]

[core proposition, 1-3 sentences]

## Context (optional)
[when and where this knowledge applies]

## Source
[[source document name]]

## Related
[[concept A]] [[concept B]]
~~~

## Placeholder Structure
~~~markdown
# [concept name]

> Status: placeholder (unfilled)
> Appears in: [[source entry]]

This concept is referenced but not yet defined.
~~~

## Processing Steps
1. Read the document thoroughly
2. Identify all independently expressible propositions
3. For each proposition, create a .md file in entries/
4. For each unexplained concept referenced, create a .md file in placeholders/
5. Update sources/source_map.json: append { "document_path": ["entry1", "entry2", ...] }

## Important
- Do not judge whether a proposition is already in the knowledge base. Just write it. Deduplication happens during tidy.
- Do not read existing entries during ingestion. Keep ingestion cost constant.
- Prefer over-splitting to under-splitting.
```

**验收**：文件存在，内容完整，格式为可直接用作 system prompt 的 Markdown

---

### Task 4.2 — 编写 tidy.md（整理 Skill）

文件路径：`skills/tidy.md`

```markdown
# Sediment Tidy Skill

You are a knowledge tidy agent for Sediment.

## Goal
Improve the internal consistency of the knowledge base. Do NOT ingest new documents.

## Available Tools
Run Python functions from scripts/tidy_utils.py:
- python -c "from scripts.tidy_utils import find_dangling_links; import json; print(json.dumps(find_dangling_links('knowledge-base')))"
- python -c "from scripts.tidy_utils import count_placeholder_refs; import json; print(json.dumps(count_placeholder_refs('knowledge-base')))"
- python -c "from scripts.tidy_utils import find_orphan_entries; import json; print(json.dumps(find_orphan_entries('knowledge-base')))"
- python -c "from scripts.tidy_utils import collect_ref_contexts; import json; print(json.dumps(collect_ref_contexts('knowledge-base', 'CONCEPT_NAME')))"

## Sub-actions (select as needed)

### 1. Resolve Dangling Links
Run find_dangling_links(). For each dangling link:
- If the concept is clearly just an unexplained reference → create a placeholder file
- Present a list of all created placeholders to the user for review

### 2. Inductive Reasoning (Detective Mode)
Run count_placeholder_refs(). For placeholders with ref_count >= 3:
- Run collect_ref_contexts() to gather all usage contexts
- Reason about what this concept means in this codebase/organization
- Draft a formal entry and mark it with: `> Status: draft — pending human review`
- Present the draft to the user for confirmation before writing

### 3. Merge Duplicates
Read all entries in entries/ and identify semantically similar ones.
- Present merge candidates with explanation of why they seem redundant
- Wait for user confirmation before merging
- When merging: keep the clearer version, combine Source and Related sections

### 4. Fix Orphan Nodes
Run find_orphan_entries(). For each orphan:
- Suggest 1-3 existing entries it should link to, with brief reasoning
- Wait for user confirmation before writing changes

## Important
- Never write files without user confirmation for tidy actions.
- Each suggestion must include: what to change, why, and what the result will look like.
- Run health_check.py at the end to show the before/after improvement.
```

**验收**：文件存在，内容包含四个子动作的完整操作指引

---

### Task 4.3 — 编写 explore.md（探索协议 Skill）

文件路径：`skills/explore.md`

此文件同时用于：(1) 分发给用户 Agent 的自主探索指引，(2) knowledge_ask 内部子 Agent 的 system prompt。

```markdown
# Sediment Explore Skill

You have access to a complex knowledge base via these tools:
- knowledge_list(): returns all entry names
- knowledge_read(filename): reads the full content of an entry

## Exploration Protocol

1. Call knowledge_list() to get all entry names.
2. Based on the question, reason about 2-5 semantically relevant entry names.
   File names are natural language — use semantic understanding for fuzzy matching.
   Example: "interface permission control" semantically matches "clarify-permission-boundaries-before-api-design".
3. Call knowledge_read() on each candidate.
4. Assess relevance. If relevant, look at the [[Related]] section and continue reading linked concepts.
5. If the current keywords yield no results, rephrase and try different angles.
6. Synthesize all relevant entries into a complete answer.
   Always list the source entry names you drew from.

## Output Format (for knowledge_ask)
Return a JSON object:
{
  "answer": "synthesized answer in natural language",
  "sources": ["entry-name-1", "entry-name-2"]
}

## Notes
- Placeholder entries (Status: placeholder) mean the concept exists but is not fully defined. Use with caution.
- [[Related]] links are exploration leads — always go at least 2 levels deep before concluding nothing is relevant.
- If you find contradictory entries, report the contradiction rather than silently picking one.
```

**验收**：文件存在，JSON 输出格式有明确说明（供 knowledge_ask 解析）

---

## Phase 5：集成测试

### Task 5.1 — 端到端测试：knowledge_list 和 knowledge_read

启动 MCP Server，通过 MCP client 或直接调用验证：

```
测试 1：knowledge_list()
期望：返回 ["示例-候选链接规则", "示例-原子知识条目规范", "示例-占位文件说明"]（或含这三项）

测试 2：knowledge_read("示例-原子知识条目规范")
期望：返回该文件的完整 Markdown 内容

测试 3：knowledge_read("不存在")
期望：返回 ERROR 字符串，不崩溃

测试 4：knowledge_list() 后手动创建一个新文件，再次调用 knowledge_list()
期望：新文件名出现在列表中（验证实时性，无缓存）
```

**验收**：4 个测试全部通过

---

### Task 5.2 — 端到端测试：health_check.py

```bash
# 测试 1：正常知识库
python scripts/health_check.py knowledge-base
# 期望：输出格式正确，数字与实际文件状态一致

# 测试 2：手动制造一个悬空链接
echo "# 测试条目\n[[不存在的概念]]" > knowledge-base/entries/测试悬空链接.md
python scripts/health_check.py knowledge-base
# 期望：DANGLING LINKS 显示 Count: 1

# 测试 3：清理测试文件
rm knowledge-base/entries/测试悬空链接.md
```

**验收**：3 个测试全部通过，清理完成后 health_check 恢复原始状态

---

### Task 5.3 — 端到端测试：tidy_utils.py

```python
from scripts.tidy_utils import *
kb = "knowledge-base"

# 制造测试数据
import os
with open(f"{kb}/entries/测试孤立节点.md", "w") as f:
    f.write("# 测试孤立节点\n\n这是一个没有任何链接的条目。\n")

# 测试
orphans = find_orphan_entries(kb)
assert any("测试孤立节点" in o for o in orphans), "Should detect orphan"

dangling = find_dangling_links(kb)
# 无悬空链接（孤立节点本身没有出链）

# 清理
os.remove(f"{kb}/entries/测试孤立节点.md")
print("All tidy_utils tests passed")
```

**验收**：脚本运行输出 "All tidy_utils tests passed"

---

## Phase 6：收尾

### Task 6.1 — 补充 README.md

补充 Quick Start 章节：

```markdown
## Quick Start

### 1. Install
pip install -r mcp_server/requirements.txt

### 2. Set knowledge base path
export SEDIMENT_KB_PATH=/path/to/your/knowledge-base

### 3. Start MCP Server
python mcp_server/server.py

### 4. Connect from Claude Code
Add to your Claude Code MCP config:
{
  "sediment": {
    "command": "python",
    "args": ["/path/to/sediment/mcp_server/server.py"],
    "env": {
      "SEDIMENT_KB_PATH": "/path/to/your/knowledge-base"
    }
  }
}

### 5. Ingest documents (admin)
In Claude Code, load skills/ingest.md as your system prompt, then provide document paths.

### 6. Query knowledge (users)
Use the knowledge_ask MCP tool, or load skills/explore.md and use knowledge_list + knowledge_read directly.
```

**验收**：README 包含完整的 Quick Start，新用户可按步骤运行

---

### Task 6.2 — 最终目录检查

确认以下所有文件存在且非空：

```
sediment/
├── README.md                          ✓
├── mcp_server/
│   ├── server.py                      ✓
│   └── requirements.txt               ✓
├── scripts/
│   ├── tidy_utils.py                  ✓
│   └── health_check.py                ✓
├── skills/
│   ├── ingest.md                      ✓
│   ├── tidy.md                        ✓
│   └── explore.md                     ✓
└── knowledge-base/
    ├── entries/
    │   ├── 示例-原子知识条目规范.md    ✓
    │   └── 示例-候选链接规则.md        ✓
    ├── placeholders/
    │   └── 示例-占位文件说明.md        ✓
    └── sources/
        └── source_map.json            ✓
```

**最终验收**：
```bash
python scripts/health_check.py knowledge-base
# 输出无错误，格式正确

python mcp_server/server.py &
# 进程启动不报错

python -c "from scripts.tidy_utils import find_dangling_links; print(find_dangling_links('knowledge-base'))"
# 返回空列表 []
```

---

## 环境变量参考

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SEDIMENT_KB_PATH` | `./knowledge-base` | 知识库根目录路径 |
| `SEDIMENT_CLI` | `claude` | knowledge_ask 内部调用的 CLI 命令名 |

---

## 关键约束（执行时不得违反）

1. **tidy_utils.py 所有函数必须无状态**，每次调用实时从文件系统计算，不得缓存任何结果
2. **knowledge_read 必须防路径穿越**，filename 中含 `/` 或 `..` 时返回错误
3. **knowledge_ask CLI 不可用时必须降级**，不得让 MCP 工具抛出未捕获异常
4. **整理类写操作必须等待人工确认**，tidy.md Skill 中所有建议均须 present → confirm → write
5. **MCP Server 只读知识库**，server.py 中不得有任何写文件操作
```
