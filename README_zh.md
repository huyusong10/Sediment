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

Sediment 现在默认从
[`config/sediment/config.yaml`](config/sediment/config.yaml) 读取运行配置。
如果需要，也可以在命令行里通过 `--config /path/to/config.yaml` 覆盖。

如果当前工作区没有这份配置文件，Sediment 会回退到用户级配置目录：

- macOS：`~/Library/Application Support/Sediment/config.yaml`
- Windows：`%APPDATA%/Sediment/config.yaml`
- Linux：`$XDG_CONFIG_HOME/sediment/config.yaml` 或 `~/.config/sediment/config.yaml`

例如：

```bash
uv run sediment server run
```

默认配置文件是仓库内本地文件，并且兼容多平台。路径统一通过
`paths.workspace_root` 做解析，`agent.command` 同时支持 YAML 字符串和
字符串数组，能减少 Windows 下的转义问题。

如果要用守护进程方式管理，也统一走同一条入口：

```bash
uv run sediment server start
uv run sediment server status
uv run sediment server stop
```

`uv run sediment up` 仍然保留为前台本地启动的简写别名。

平台会同时提供三类入口：

- `MCP`：SSE / JSON-RPC
- `Portal`：`/portal`
- `Admin`：`/admin`

在内部，排队的 `ingest` / `tidy` 任务仍然由 worker 角色执行。
正常部署仍然建议保持队列执行独立。

兼容性的底层入口仍然保留，便于更细粒度调试：

- `uv run sediment-server`
- `uv run sediment-worker`
- `uv run sediment-up`

主要配置分组包括：

- `paths`：工作区根目录、知识库、状态目录、数据库、上传目录、worker 工作区
- `server`：监听地址、端口、SSE 路径、是否进程内跑 job
- `auth`：admin token、session secret、cookie 安全配置
- `network`：可信代理和真实 IP 获取规则
- `submissions`：限流、去重、文本/文件大小上限
- `jobs`：重试次数和 stale timeout
- `agent`：所选后端，以及命令、模型、sandbox 等参数
- `knowledge`：locale、query language override、index 合约默认值

支持的 `agent.backend`：

- `claude-code`
- `codex`
- `opencode`

例如：

```yaml
agent:
  backend: codex
  command:
    - codex
  model: gpt-5-codex
  sandbox: workspace-write
  exec_timeout_seconds: 240
```

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
- `knowledge_platform_status`
- `knowledge_submission_queue`
- `knowledge_job_status`
- `knowledge_tidy_request`
- `knowledge_review_decide`

额外的 REST / Admin 入口包括：

- `GET /healthz`
- `GET|POST|DELETE /api/admin/session`
- `GET /api/admin/system/status`
- `GET /api/admin/audit`
- `POST /api/admin/jobs/{id}/retry`
- `POST /api/admin/jobs/{id}/cancel`

统一后的 CLI 入口包括：

- `sediment server ...`：生命周期控制、日志和守护进程状态
- `sediment kb ...`：explore、list、read、health、tidy
- `sediment status ...`：平台总览、daemon、queue、KB health
- `sediment doctor`：检查配置、文件系统和 agent backend 是否健康

## 使用知识库

- **探索**：通过 `knowledge_ask` 提问，或直接运行 `uv run sediment kb explore "你的问题"`
- **巡检**：运行 `uv run sediment kb health`，或运行 `uv run python skills/health/scripts/health_check.py knowledge-base`
- **查看状态**：运行 `uv run sediment status`、`uv run sediment status queue` 或 `uv run sediment server status`
- **摄入（实验性）**：把 `skills/ingest/SKILL.md` 作为工作流说明，输入原始材料
- **整理（实验性）**：把 `skills/tidy/SKILL.md` 作为工作流说明，或直接运行 `uv run sediment kb tidy "<条目名>"`
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
uv run sediment server run
```

常用检查命令：

```bash
uv run sediment doctor
uv run sediment doctor --json
```

测试里会用 `tests/fixtures/mock_workflow_cli.py` 模拟 Agent Runner。

开发时请保持：
- 来源只放 frontmatter `sources`，不要写成 `[[wikilink]]`
- provenance 不得生成知识图谱边
- MCP 工具名和 `knowledge_ask` 返回 schema 不变
- 除受控后台编辑外，写路径应尽量走缓冲区与审核流

## 生产硬化建议

最低部署基线建议：

- 设置 `auth.admin_token`
- 设置 `auth.session_secret`
- 在 HTTPS 下开启 `auth.secure_cookies: true`
- 本地开发推荐 `sediment server run`
- 守护进程控制统一走 `sediment server start|stop|status|logs`
- 生产环境仍建议保持 `server` 和 `worker` 两个角色分离，只是入口统一成 `sediment`
- 如果前面有反向代理，设置 `network.trust_proxy_headers: true`，并限制 `network.trusted_proxy_cidrs`
- 监控 `/healthz` 和 Admin 后台里的 system status 面板

当前 worker 会持续写入 job heartbeat，超过配置超时后会自动回收陈旧
`running` 任务，同时支持显式 cancel / retry，并把 session、入队、审核、
写回等动作写入结构化审计日志。

`sediment server run` 和 `sediment up` 都只是当前分层架构上的轻量启动器：
它们会同时拉起两个角色，为日志加上 `[server]` / `[worker]` 前缀，
等待 `/healthz` 就绪，并在你按下 `Ctrl+C` 时一起优雅退出。

## 许可证

[MIT](LICENSE)
