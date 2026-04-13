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

安装脚本默认会覆盖并重装已有的 `sediment` CLI，所以你也可以把它当作可靠的升级命令反复执行。

安装脚本现在默认还会尝试准备一个“共享 Quartz runtime”，用于支持可选的图谱页。Sediment 不会把 Quartz 装成全局 npm 包，而是把它放进用户级 Sediment 状态目录里。如果 Quartz 这一步失败，安装脚本不会直接把 Sediment 整体装坏，而是会给出这两条补救路径：

```bash
bash install.sh --quartz-only
```

```bash
git clone https://github.com/jackyzha0/quartz.git "<你的 Sediment 用户状态目录>/quartz-runtime/quartz"
cd "<你的 Sediment 用户状态目录>/quartz-runtime/quartz"
npm i
```

### 手工模式

如果你更希望先看源码、再自己控制安装过程：

```bash
git clone https://github.com/huyusong10/Sediment.git
cd Sediment
uv tool install --from . sediment --force --reinstall --compile-bytecode
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
sediment init
```

在正常终端里，`sediment init` 会打开一个交互式初始化向导。它会询问实例名、知识库名、Agent backend、host 和 port；任何一项直接回车都会采用提示里的默认值。

如果你更希望走脚本化方式：

```bash
sediment init \
  --instance-name ops-prod \
  --knowledge-name "生产运维知识库" \
  --backend claude-code \
  --host 127.0.0.1 \
  --port 8000 \
  --no-interactive
```

先列出实例，再检查当前实例是否可用：

```bash
sediment instance list
sediment doctor
```

启动平台：

```bash
sediment server run
```

服务启动后，Sediment 会在终端里打印一个一次性的管理台登录 token。进入 `/admin` 时，直接使用这个 token 即可登录。

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
sediment instance list
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

如果你当前就在实例根目录，或者位于它的 `knowledge-base/` 子目录里，Sediment 会自动解析本地配置；这时通常不需要显式写 `--instance`。

只有在别的目录里远程管理实例时，才需要：

```bash
sediment --instance ops-prod doctor
sediment --instance ops-prod server start
sediment --instance ops-prod review list
```

如果你暂时不想安装 CLI，也可以直接从仓库源码运行：

```bash
uv run --project /path/to/Sediment sediment --help
```

## Portal 工作流

- 搜索是主界面：Portal 优先服务全文搜索，条目全文改成聚焦弹层，而不是长期占据一整块固定侧栏。
- 文本提交在进入缓冲区之前，会先结合当前 KB 做一次 Agent 建议分析，让 committer 直接看到建议标题、建议类型、重复风险和相关条目。
- 文档提交支持单文件、文件夹、多文件和 `.zip` 压缩包；Sediment 会自动解压支持的文档，并把提取出的文本送进缓冲区。
- Quartz 4 被当作可选增强页，而不是基础运行时依赖。只要你已经构建好 Quartz 静态站点，Sediment 就会在 `/portal/graph-view` 自动嵌入；如果没有，核心安装也依然不需要 Node/npm。
- 安装脚本现在会默认尝试准备 Quartz runtime；如果失败，`/portal/graph-view` 页面会直接提示你重新运行 `install.sh --quartz-only`，或者按官方方式手工安装 Quartz。

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
