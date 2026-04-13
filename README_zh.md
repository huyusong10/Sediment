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

Sediment 是一个面向 AI Agent 的白盒隐性知识系统。它当前重点提供
稳定的 Markdown 知识库运行时：可读、可校验、可巡检、可检索，
并增加了企业平台层：提交缓冲区、审核流、health 面板，以及通过本地
Agent Runner 托管执行的 ingest / tidy。

Sediment v4 坚持几条核心原则：
- **白盒优先**：知识库就是文件，不是隐藏数据库
- **来源是元数据**：来源必须可追溯，但来源名不是知识图谱节点
- **中结构优先于过度自由**：条目要有足够结构，保证整理和巡检的下限
- **人工审核友好**：同一份文件同时服务于 Agent、脚本和 Obsidian 等编辑工具

设计文档入口见 [design/README.md](design/README.md)。核心精神独立放在 [design/core-principles.md](design/core-principles.md)，当前设计按主题拆分在 [design/current/](design/current/overview.md)，`v3` / `v4` / `v4.5` 历史版本保留在 [design/evolution/](design/evolution/README.md)。

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

## 启动平台服务

```bash
export SEDIMENT_KB_PATH=/path/to/your/knowledge-base
export SEDIMENT_CLI=claude
uv run sediment-server
uv run sediment-worker
```

Server 会同时提供三类入口：

- `MCP`：SSE / JSON-RPC
- `Portal`：`/portal`
- `Admin`：`/admin`

Worker 是默认的 `ingest` / `tidy` 队列执行路径。
如果只是本地单进程调试，也可以设置 `SEDIMENT_RUN_JOBS_IN_PROCESS=1`
只启动 server，但生产部署建议保持 worker 独立运行。

环境变量：

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `SEDIMENT_KB_PATH` | 项目 `knowledge-base/` | 知识库根目录 |
| `SEDIMENT_CLI` | `claude` | `knowledge_ask` 以及实验性工作流脚本使用的 CLI |
| `SEDIMENT_HOST` | `0.0.0.0` | HTTP 绑定地址 |
| `SEDIMENT_PORT` | `8000` | HTTP 端口 |
| `SEDIMENT_SSE_PATH` | `/sediment/` | SSE 端点路径 |
| `SEDIMENT_ADMIN_TOKEN` | 空 | `/admin` 和管理接口使用的可选 Bearer token |
| `SEDIMENT_SESSION_SECRET` | `SEDIMENT_ADMIN_TOKEN` | Admin Web session cookie 的签名密钥 |
| `SEDIMENT_ADMIN_SESSION_COOKIE_NAME` | `sediment_admin_session` | Admin session cookie 名称 |
| `SEDIMENT_ADMIN_SESSION_TTL_SECONDS` | `43200` | Admin session 有效期，单位秒 |
| `SEDIMENT_SECURE_COOKIES` | `0` | 是否把 Admin cookie 标记为 `Secure`，HTTPS 下建议开启 |
| `SEDIMENT_TRUST_PROXY_HEADERS` | `0` | 是否信任 `X-Forwarded-For` / `X-Real-IP` |
| `SEDIMENT_TRUSTED_PROXY_CIDRS` | 空 | 允许提供真实客户端 IP 的反向代理 CIDR 列表 |
| `SEDIMENT_SUBMISSION_RATE_LIMIT_COUNT` | `1` | 单个 IP 在窗口内允许的最大提交次数 |
| `SEDIMENT_SUBMISSION_RATE_LIMIT_WINDOW_SECONDS` | `60` | 提交限流窗口，单位秒 |
| `SEDIMENT_SUBMISSION_DEDUPE_WINDOW_SECONDS` | `86400` | 完全重复提交的去重窗口，单位秒 |
| `SEDIMENT_MAX_TEXT_SUBMISSION_CHARS` | `20000` | 纯文本提交大小上限 |
| `SEDIMENT_MAX_UPLOAD_BYTES` | `10485760` | 上传文档大小上限 |
| `SEDIMENT_STATE_DIR` | `.sediment_state/` | 平台状态目录，包含 DB、上传文件和 worker 工作区 |
| `SEDIMENT_DB_PATH` | `.sediment_state/platform.db` | 提交、任务、审核、审计日志的 SQLite 路径 |
| `SEDIMENT_UPLOADS_DIR` | `.sediment_state/uploads/` | 上传文档存储目录 |
| `SEDIMENT_WORKSPACES_DIR` | `.sediment_state/workspaces/` | ingest / tidy 隔离工作区 |
| `SEDIMENT_JOB_MAX_ATTEMPTS` | `3` | worker 自动重试上限 |
| `SEDIMENT_JOB_STALE_AFTER_SECONDS` | `900` | 运行中任务超过该心跳超时后会被回收 |
| `SEDIMENT_RUN_JOBS_IN_PROCESS` | `0` | 是否在 server 进程内直接执行任务，而不是交给独立 worker |

## Portal 与 Admin

启动 server 后可访问：

- Portal: [http://localhost:8000/portal](http://localhost:8000/portal)
- Admin: [http://localhost:8000/admin](http://localhost:8000/admin)
- Health: [http://localhost:8000/healthz](http://localhost:8000/healthz)

Portal 支持：

- 全文搜索
- 图谱浏览
- 查看条目与索引全文
- 提交纯文本概念、经验、意见和文档到缓冲区

Admin 支持：

- 通过同站签名 session cookie 登录后台
- 常驻 health issue 队列
- 查看系统状态、队列模式和运行时限制
- 提交缓冲区 triage
- ingest / tidy 排队、运行与待审结果查看
- 任务取消、重试与陈旧任务恢复可见性
- patch 批准 / 拒绝
- 带校验的在线 Markdown 编辑
- 最近审计日志

## 对外接口

稳定读工具仍然保持：

- `knowledge_list`
- `knowledge_read`
- `knowledge_ask`

新增平台工具包括：

- `knowledge_submit_text`
- `knowledge_submit_document`
- `knowledge_health_report`
- `knowledge_submission_queue`
- `knowledge_job_status`
- `knowledge_review_decide`

额外的 REST / Admin 入口包括：

- `GET /healthz`
- `GET|POST|DELETE /api/admin/session`
- `GET /api/admin/system/status`
- `GET /api/admin/audit`
- `POST /api/admin/jobs/{id}/retry`
- `POST /api/admin/jobs/{id}/cancel`

## 使用知识库

- **探索**：通过 `knowledge_ask` 提问，或直接使用 `knowledge_list` + `knowledge_read`
- **巡检**：运行 `uv run python skills/health/scripts/health_check.py knowledge-base`
- **摄入（实验性）**：把 `skills/ingest/SKILL.md` 作为工作流说明，输入原始材料
- **整理（实验性）**：把 `skills/tidy/SKILL.md` 作为工作流说明，修复断链、坏条目和可提升 placeholder
- **Portal 提交**：把文字或文档送进缓冲区，等待 committer 审核
- **Admin 审核**：在 Web 管理台中批准 / 拒绝 ingest 与 tidy 结果

`testcase/` 下的 benchmark 脚本用于内部评估，不属于 Sediment 公共运行时接口的一部分。

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

本地端到端调试建议：

```bash
export SEDIMENT_KB_PATH=/absolute/path/to/knowledge-base
export SEDIMENT_CLI=claude
export SEDIMENT_RUN_JOBS_IN_PROCESS=0
uv run sediment-server
uv run sediment-worker
```

测试里会用 `tests/fixtures/mock_workflow_cli.py` 模拟 Agent Runner，
但真实部署应把 `SEDIMENT_CLI` 指向实际可用的本地编码 CLI。

开发时请保持：
- 来源只放 frontmatter `sources`，不要写成 `[[wikilink]]`
- provenance 不得生成知识图谱边
- MCP 工具名和 `knowledge_ask` 返回 schema 不变
- 除受控后台编辑外，写路径应尽量走缓冲区与审核流

## 生产硬化建议

最低部署基线建议：

- 设置 `SEDIMENT_ADMIN_TOKEN`
- 设置 `SEDIMENT_SESSION_SECRET`
- 在 HTTPS 下开启 `SEDIMENT_SECURE_COOKIES=1`
- 把 `sediment-server` 和 `sediment-worker` 分开部署
- 如果前面有反向代理，开启 `SEDIMENT_TRUST_PROXY_HEADERS=1`，并限制 `SEDIMENT_TRUSTED_PROXY_CIDRS`
- 监控 `/healthz` 和 Admin 后台里的 system status 面板

当前 worker 会持续写入 job heartbeat，超过配置超时后会自动回收陈旧
`running` 任务，同时支持显式 cancel / retry，并把 session、入队、审核、
写回等动作写入结构化审计日志。

## 许可证

[MIT](LICENSE)
