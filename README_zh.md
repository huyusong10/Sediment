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

Sediment 建立在一个很简单、但很少被认真贯彻的判断上：

> 如果 AI 要参与组织记忆，那么这份记忆必须始终对人类保持可理解。

所以，知识库不能只是“能搜到”。它还必须能被检查、被 diff、被审阅、被治理，并且在时间尺度上持续保持清晰。

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

### 自动模式

对 macOS 和 Linux 用户，最快的安装方式是一条命令：

```bash
curl -fsSL https://raw.githubusercontent.com/huyusong10/Sediment/master/install.sh | bash
```

这个脚本会通过 `uv` 安装 `sediment` CLI，安装完成后你就可以直接在 shell 里使用：

```bash
sediment --help
```

### 手工模式

如果你更希望先看源码、再自己控制安装过程：

```bash
git clone https://github.com/huyusong10/Sediment.git
cd Sediment
uv tool install --from . sediment
sediment --help
```

这也是 Windows 上更推荐的路径。

本地开发可直接运行：

```bash
uv run --project . pytest -q
```

## 快速开始

先在你的工作目录里初始化一个 Sediment 实例：

```bash
mkdir my-sediment-workspace
cd my-sediment-workspace
sediment init \
  --instance-name ops-prod \
  --knowledge-name "生产运维知识库"
```

检查实例是否可用：

```bash
sediment doctor
```

启动平台：

```bash
sediment server run
```

然后访问：

- `http://127.0.0.1:8000/portal`
- `http://127.0.0.1:8000/admin`
- `http://127.0.0.1:8000/healthz`

## 它真正不同的地方

Sediment 不是那种“套一个好看的 UI，然后把一切留给黑盒检索”的系统。

它把知识当作一种基础设施来设计：

- 正式知识是明文文件，而不是藏在系统内部状态里的幻影
- Agent 可以高效参与，但不能偷偷把草案直接变成组织共识
- Web、CLI、MCP 不是三套割裂产品，而是同一后端逻辑的不同表面
- 企业级治理不是事后补丁，而是从第一天就进入系统边界

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

如果你暂时不想安装 CLI，也可以直接从仓库源码运行：

```bash
uv run --project /path/to/Sediment sediment --help
```

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

再往深一层说，Sediment 追求的是“长期清晰”，而不是“短期神奇”：

- 它偏爱显式结构，而不是隐含启发式
- 它偏爱审阅队列，而不是静默改写
- 它偏爱本地可检查实例，而不是中央黑盒系统
- 它偏爱能穿越人员流动、工具更替和模型变化的知识资产

## 文档

- 设计文档入口：[design/README.md](design/README.md)
- 平台架构：[design/current/platform-architecture.md](design/current/platform-architecture.md)

## License

MIT
