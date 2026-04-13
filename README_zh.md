<div align="center">

<img src="src/sediment/assets/logo.svg" alt="Sediment Logo" width="360" />

# Sediment

**一个面向 AI Agent 与团队协作的白盒知识库系统。**

把混乱的原始材料沉淀为可审阅、可搜索、可治理的 Markdown 知识库。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

[English](README.md) | [中文](README_zh.md)

</div>

## 为什么是 Sediment

企业知识系统常常会走向两个极端：

- 太黑盒：能用，但没人说得清答案为什么是这样。
- 太松散：人人都能写，最后知识库逐渐腐化。

Sediment 选择中间道路：

- 白盒知识：正式知识就是文件，不是隐藏数据库
- Agent 协作：内置 ingest、tidy、搜索与 health 能力
- 人工审核优先：提交和修改先进入工作流，而不是直接污染正式知识层
- 多入口统一：CLI、MCP、Web 共享同一套运行时

## 它提供什么

- 标准 `src/` 布局的 Python 项目
- 一个统一的命令行入口：`sediment`
- MCP 服务、Web Portal 和 Admin 后台
- 由本地 Agent 托管执行的 `ingest` / `tidy` 工作流
- 多种 Agent CLI 后端支持：
  - Claude Code CLI
  - Codex CLI
  - OpenCode CLI

## 安装

```bash
git clone https://github.com/huyusong10/Sediment.git
cd Sediment
uv run --project . sediment --help
```

本地开发可直接运行：

```bash
uv run --project . pytest -q
```

## 快速开始

先在你的工作目录里初始化一个 Sediment 实例：

```bash
mkdir my-sediment-workspace
cd my-sediment-workspace
uv run --project /path/to/Sediment sediment init \
  --instance-name ops-prod \
  --knowledge-name "生产运维知识库"
```

检查实例是否可用：

```bash
uv run --project /path/to/Sediment sediment doctor
```

启动平台：

```bash
uv run --project /path/to/Sediment sediment server run
```

然后访问：

- `http://127.0.0.1:8000/portal`
- `http://127.0.0.1:8000/admin`
- `http://127.0.0.1:8000/healthz`

## 核心命令

```bash
sediment init
sediment doctor
sediment status
sediment server start
sediment server stop
sediment kb explore "什么是热备份？"
sediment review list
sediment logs tail
```

每个实例的运行配置默认保存在：

```text
./config/sediment/config.yaml
```

这意味着 Sediment 是“实例本地化”的，但依然可以通过 CLI 统一管理多个实例。

## 项目结构

```text
src/sediment/      Python 包、MCP 运行时、Web UI、内置技能
tests/             自动化测试
scripts/           辅助脚本
benchmarks/        内部评估脚手架
design/            设计文档
```

## 核心理念

Sediment 对几件事有明确偏好：

- 知识必须可检查
- 结构必须足够稳定，便于校验
- Agent 产出必须先可审核，再成为正式知识
- 企业工作流不该要求用户手工登录知识库宿主机

## 文档

- 设计文档入口：[design/README.md](design/README.md)
- 平台架构：[design/current/platform-architecture.md](design/current/platform-architecture.md)

## License

MIT
