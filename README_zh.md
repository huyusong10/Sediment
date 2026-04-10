<div align="center">

<img src="resources/logo.svg" alt="Sediment Logo" width="450"/>

<br/>

**适用于 AI Agent 的隐性知识提取系统**

*将复杂的非结构化文档转化为结构化、可人工审阅的知识库。*

<br/>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

[![GitHub Stars](https://img.shields.io/github/stars/huyusong10/Sediment?style=social)](https://github.com/huyusong10/Sediment/stargazers)

</div>

---

[🇺🇸 English](README.md) | [🇨🇳 中文](README_zh.md)

---

Sediment 帮助广大用户和团队提炼和整理**隐性知识** —— 那些埋藏在人的脑子里、散落在各种文档中、以及隐含在操作惯例里的知识 —— 并将其组织为结构化、可被人工审阅的知识库，供 AI Agent 查询和扩充。

核心能力：

| 能力 | 说明 |
|---|---|
| **摄入（Ingest）** | 解析文档，通过 AI Skill 提取原子知识条目 |
| **整理（Tidy）** | 修复悬空链接、归纳推理补充占位概念、合并重复条目、修复孤立节点 |
| **探索（Explore）** | 让 AI Agent 通过 MCP 工具自主发现并综合相关知识 |
| **巡检（Health Check）** | 随时生成知识库的全面诊断报告 |

---

---

> *"我之所以能保持高产，并不是因为我的思想有多么非凡，而是归功于我的卡片盒替我承担了思考的工作。"* —— 尼克拉斯·卢曼（Zettelkasten 发明者）

Sediment 深度践行了 **Zettelkasten（卡片盒笔记法）** 的理念，并极致追求知识存储的**白盒化**：
- **原子化与网状链接**：知识库中的每个概念都被拆解为唯一且独立的 Markdown 文件，通过明确的 `[[双向链接]]` 相互编织。
- **绝对透明的白盒设计**：这里没有黑盒式的隐藏数据库，也没有强依赖隐式匹配的向量库（Vector DB）。所有的隐性知识都清晰地沉淀为纯文本。
- **与 Obsidian 完美兼容**：得益于极其标准的 Markdown 语法和文件结构，你可以直接使用 **Obsidian** 等双链笔记软件打开挂载 `knowledge-base` 目录。无论是可视化整站的知识关系图谱，还是进行人工审查与编辑维护，这套系统都能让人类和 AI Agent 处在同一个数据维度上进行无缝协同。

---

## 目录

- [服务器侧部署与使用](#服务器侧部署与使用)
  - [前置条件](#前置条件)
  - [安装依赖](#安装依赖)
  - [配置并启动-MCP-Server](#配置并启动-mcp-server)
  - [连接至-AI-Agent-宿主程序](#连接至-ai-agent-宿主程序)
  - [摄入文档到知识库](#摄入文档到知识库)
  - [运行巡检报告](#运行巡检报告)
  - [环境变量参考](#环境变量参考)
- [用户侧部署与使用](#用户侧部署与使用)
  - [查询知识库](#查询知识库)
  - [手动探索知识库](#手动探索知识库)
  - [整理知识库](#整理知识库)
- [开发指南](#开发指南)
- [许可证](#许可证)

---

## 服务器侧部署与使用

> **本节面向管理员**，负责搭建和维护 Sediment 服务端、摄入文档、运行巡检报告。

### 前置条件

- Python 3.11 或以上版本
- [uv](https://docs.astral.sh/uv/) — 高速 Python 包管理器

```bash
# 安装 uv（macOS / Linux）
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 安装依赖

克隆仓库并安装：

```bash
git clone https://github.com/huyusong10/Sediment.git
cd Sediment
uv sync
```

此命令会自动创建 `.venv` 虚拟环境并根据 `pyproject.toml` 安装所有依赖。

### 配置并启动 MCP Server

Sediment 以 HTTP 服务器形式运行，使用 SSE 传输：

```bash
# 设置知识库路径（可选，默认为项目下的 knowledge-base 目录）
export SEDIMENT_KB_PATH=/path/to/your/knowledge-base

# 设置 knowledge_ask 使用的 CLI（可选，默认为 claude）
export SEDIMENT_CLI=claude

# 启动服务器（默认监听 0.0.0.0:8000）
uv run python mcp_server/server.py
```

**服务器相关环境变量：**

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `SEDIMENT_HOST` | `0.0.0.0` | 服务器绑定地址 |
| `SEDIMENT_PORT` | `8000` | 端口号 |
| `SEDIMENT_SSE_PATH` | `/sediment/` | SSE 端点路径 |

**生产环境部署** — 建议使用 `systemd`、`supervisor` 等进程管理器，或在前面加一层反向代理（nginx/Caddy）：

```nginx
# nginx 反向代理示例
location /sediment/ {
    proxy_pass http://127.0.0.1:8000/sediment/;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
}
```

### 连接至 AI Agent 宿主程序

客户端通过 HTTP/SSE 连接到 Sediment 服务器，而非启动子进程。

**Claude Desktop / Claude Code** — 在 MCP 配置文件中添加：

- **Claude Desktop**：`~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）或 `%APPDATA%\Claude\claude_desktop_config.json`（Windows）
- **Claude Code**：项目根目录下的 `.claude/settings.json`，或全局配置 `~/.claude/settings.json`

```json
{
  "mcpServers": {
    "sediment": {
      "url": "http://your-server-host:8000/sediment/"
    }
  }
}
```

将 `your-server-host:8000` 替换为 Sediment 服务器实际运行的 IP/域名和端口。

**MCP Inspector** — 用于调试：

```bash
npx @anthropic/mcp-inspector --url http://localhost:8000/sediment/
```

> **安全说明：** `knowledge_read` 会拒绝包含 `/`、`\` 或 `..` 的文件名，防止路径穿越攻击。MCP Server 不对知识库执行任何写操作。

### 摄入文档到知识库

将 `skills/ingest.md` 加载为 Agent 的 system prompt。文件包含 YAML frontmatter（`name`、`description`、`trigger` 元数据），支持 Claude Code 等 skill 感知型 Agent 的自动发现。

然后提供需要摄入的文档（粘贴内容或指明文件路径）。Agent 将自动完成：
   - 提取原子知识条目 → 写入 `knowledge-base/entries/`
   - 为被引用但未定义的概念创建占位文件 → `knowledge-base/placeholders/`

> **摄入原则：** 一个命题 = 一个文件。拿不准时，宁可拆多，不要合并。

### 运行巡检报告

```bash
uv run python scripts/health_check.py knowledge-base
```

输出示例：

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
  - 某概念 (3 refs)
Low (1):       0

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

推荐建议规则：

| 条件 | 建议 |
|---|---|
| 存在 ≥ 5 引用次数的占位文件 | 以归纳推理模式运行整理 |
| 存在孤立节点 | 运行整理以补充缺失链接 |
| 存在悬空链接 | 运行整理以修复断链 |
| 一切正常 | 知识库健康，建议继续摄入文档 |

### 环境变量参考

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `SEDIMENT_KB_PATH` | 项目 `knowledge-base/` | 知识库根目录路径 |
| `SEDIMENT_CLI` | `claude` | `knowledge_ask` 子 Agent 使用的 CLI 命令名 |
| `SEDIMENT_HOST` | `0.0.0.0` | HTTP 服务器绑定地址 |
| `SEDIMENT_PORT` | `8000` | HTTP 服务器端口 |
| `SEDIMENT_SSE_PATH` | `/sediment/` | SSE 端点路径 |

---

## 用户侧部署与使用

> **本节面向最终用户**，通过连接了 Sediment MCP Server 的 AI Agent 查询和使用知识库。

### 查询知识库

Sediment 连接为 MCP Server 后，直接向 AI Agent 以自然语言提问即可。Agent 会调用 `knowledge_ask` 工具：

```
用户：我们的 API 权限管理策略是什么？
Agent：[调用 knowledge_ask("我们的 API 权限管理策略是什么？")]
       → 返回 { "answer": "...", "sources": ["条目名1", "条目名2"] }
```

`knowledge_ask` 内部执行流程：
1. 读取 `skills/explore.md` 作为子 Agent 的 System Prompt（YAML frontmatter 为 skill 感知型 Agent 提供 `name`/`description` 元数据）
2. 调用配置的 CLI 子 Agent 对知识库进行多轮推理
3. 返回综合答案及知识来源引用

> **降级保障：** 若 CLI 子 Agent 不可用，`knowledge_ask` 会返回友好的降级提示，而非崩溃。此时可以切换到手动探索模式（见下方）。

### 手动探索知识库

也可以直接让 Agent 使用底层工具进行探索：

```
# 步骤 1 — 列出所有可用条目
knowledge_list()
→ ["条目A", "条目B", "占位概念C", ...]

# 步骤 2 — 读取具体条目
knowledge_read("条目A")
→ 该条目的完整 Markdown 内容

# 步骤 3 — 沿 [[Related]] 链接继续探索关联概念
```

将 `skills/explore.md` 加载为 Agent 的 System Prompt，可获得完整的自主探索协议指引（要求在得出结论前至少深入探索 2 层链接）。

### 整理知识库

> 整理操作需要**管理员权限**（有权向知识库写入文件）。所有整理建议都会在写入前呈现给人工确认。

1. 将 `skills/tidy.md` 加载为 Agent 的 System Prompt。
2. Agent 会诊断知识库并给出建议：

| 动作 | 触发条件 | 效果 |
|---|---|---|
| 修复悬空链接 | `[[引用]]` 指向不存在的文件 | 创建对应占位文件 |
| 归纳推理（侦探模式） | 占位文件被引用 ≥ 3 次 | 从引用上下文推断定义，起草正式条目 |
| 合并重复条目 | 发现语义相似的条目 | 提议合并，整合来源与关联章节 |
| 修复孤立节点 | 条目既无入链也无出链 | 建议 1-3 条与现有条目的关联链接 |

3. 审阅每条建议，确认后 Agent 执行写入。
4. Agent 最终运行 `health_check.py` 展示整理前后的对比。

---

## 开发指南

```bash
# 安装含开发依赖的完整环境
uv sync --dev

# 运行 Lint 检查
uv run ruff check .

# 运行测试
uv run pytest tests/

# 对示例数据验证整理工具集
uv run python -c "
from scripts.tidy_utils import *
kb = 'knowledge-base'
print('dangling:', find_dangling_links(kb))
print('placeholder refs:', count_placeholder_refs(kb))
print('orphans:', find_orphan_entries(kb))
print('contexts:', collect_ref_contexts(kb, '示例-占位文件说明'))
"
```

---

## 许可证

[MIT](LICENSE)
