<div align="center">

<img src="resources/logo.svg" alt="Sediment Logo" width="450"/>

<br/>

**适用于 AI Agent 的隐性知识提取系统**

*把混乱的原始材料沉淀为人和 Agent 都能一起审阅的白盒知识库。*

<br/>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

</div>

---

[🇺🇸 English](README.md) | [🇨🇳 中文](README_zh.md)

---

Sediment 是一个面向 AI Agent 的白盒隐性知识系统。它从文档中提炼可复用知识，将结果保存为普通 Markdown 文件，并通过 MCP 提供检索与维护能力。

Sediment v4 坚持几条核心原则：
- **白盒优先**：知识库就是文件，不是隐藏数据库
- **来源是元数据**：来源必须可追溯，但来源名不是知识图谱节点
- **中结构优先于过度自由**：条目要有足够结构，保证整理和巡检的下限
- **人工审核友好**：同一份文件同时服务于 Agent、脚本和 Obsidian 等编辑工具

当前主设计文档见 [design/tacit_knowledge_system_v4.md](design/tacit_knowledge_system_v4.md)。`v3` 仅作为历史参考保留。

## v4 条目模型

Sediment v4 使用两类正式条目和一种轻量 placeholder。

### 概念条目 `concept`

```markdown
---
type: concept
status: fact
aliases: []
sources:
  - 来源文档名
---
# 热备份

热备份是在主链路不再可信时，可立即接管的备份路径能力。

## Scope
适用于需要连续服务的系统，尤其适用于切换路径必须受控的故障场景。

## Related
- [[故障切换]] - 热备份是受控切换的前提
```

### 经验条目 `lesson`

```markdown
---
type: lesson
status: inferred
aliases: []
sources:
  - 故障复盘名称
---
# 泄洪前先确认热备份

执行泄洪前必须先确认热备份，否则保护动作会放大恢复风险。

## Trigger
适用于主动切流、泄洪、降载等风险缓解动作。

## Why
流量一旦重分布，系统结构会立刻变化，所以备份接管能力必须先确认。

## Risks
如果忽略这一步，系统可能躲过原始故障，却在缓解路径上再次失效。

## Related
- [[热备份]] - 前置能力
```

### 占位条目 `placeholder`

```markdown
---
type: placeholder
aliases: []
---
# 暗流

这个概念在知识库中被引用了，但目前还没有足够清晰的定义可供提升。
```

## 安装

```bash
git clone https://github.com/huyusong10/Sediment.git
cd Sediment
uv sync --dev
```

内置运行时代码和 skill 资源位于：

```text
mcp_server/
skills/
  ingest/
  tidy/
  explore/
  health/
```

## 启动 MCP Server

```bash
export SEDIMENT_KB_PATH=/path/to/your/knowledge-base
export SEDIMENT_CLI=claude
uv run sediment-server
```

环境变量：

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `SEDIMENT_KB_PATH` | 项目 `knowledge-base/` | 知识库根目录 |
| `SEDIMENT_CLI` | `claude` | `knowledge_ask` 使用的 CLI |
| `SEDIMENT_HOST` | `0.0.0.0` | HTTP 绑定地址 |
| `SEDIMENT_PORT` | `8000` | HTTP 端口 |
| `SEDIMENT_SSE_PATH` | `/sediment/` | SSE 端点路径 |

## 使用知识库

- **摄入**：把 `skills/ingest/SKILL.md` 作为 Agent 指令，输入原始材料
- **探索**：通过 `knowledge_ask` 提问，或直接使用 `knowledge_list` + `knowledge_read`
- **整理**：把 `skills/tidy/SKILL.md` 作为整理指令，修复断链、坏条目和可提升 placeholder
- **巡检**：运行 `uv run python skills/health/scripts/health_check.py knowledge-base`

`knowledge_ask` 的对外返回结构保持不变：

```json
{
  "answer": "...",
  "sources": ["条目名1", "条目名2"],
  "confidence": "high",
  "exploration_summary": {
    "entries_scanned": 12,
    "entries_read": 4,
    "links_followed": 3,
    "mode": "definition-driven"
  },
  "gaps": [],
  "contradictions": []
}
```

## 开发

```bash
uv sync --dev
uv run ruff check .
uv run pytest
uv build
```

开发时请保持：
- 来源只放 frontmatter `sources`，不要写成 `[[wikilink]]`
- provenance 不得生成知识图谱边
- MCP 工具名和 `knowledge_ask` 返回 schema 不变

## 许可证

[MIT](LICENSE)
