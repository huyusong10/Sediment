# 当前设计总览

Sediment 当前设计基线可以概括为：

- 用 v4 条目模型表达正式知识与缺口
- 用 v4.5 的索引网络组织检索入口
- 用 submit / review / ingest / tidy / explore / health 工作流维护知识层
- 用提交缓冲区、审核流、Agent Runner 和 Web 界面把本地运行时提升为企业知识平台

核心原则不在本文重复定义，统一以 [../core-principles.md](../core-principles.md) 为准。

## 1. 当前设计由哪些部分组成

- [entry-model.md](entry-model.md)：知识条目怎样落盘，哪些字段和段落是必需的
- [workflows.md](workflows.md)：提交、审核、摄入、整理、检索、巡检以及人工编辑各自的职责边界
- [retrieval-and-indexing.md](retrieval-and-indexing.md)：如何用 `index.root.md` 和 `indexes/` 组织检索入口
- [validation-and-health.md](validation-and-health.md)：如何判断条目、索引和图谱是否健康
- [enterprise-governance.md](enterprise-governance.md)：企业部署时的角色、权限和审核责任
- [platform-architecture.md](platform-architecture.md)：企业版 Sediment 的服务分层、存储边界和部署结构
- [interfaces-and-review-flow.md](interfaces-and-review-flow.md)：MCP、REST、提交缓冲区、任务流和审核状态机
- [web-surfaces.md](web-surfaces.md)：前台门户与管理后台的页面和功能边界
- [delivery-roadmap.md](delivery-roadmap.md)：按阶段落地企业平台的实施路径

## 2. 当前知识层布局

```text
knowledge-base/
  entries/               正式条目（concept / lesson）
  placeholders/          缺口条目（placeholder）
  index.root.md          全局检索入口
  indexes/               分段索引
```

这个布局表达了三个判断：

- 正式知识和知识缺口要分开保存
- 索引是导航层，不是知识正文副本
- 知识关系主要由条目之间的链接表达，而不是由目录层级硬编码

## 3. 当前平台分层

企业版 Sediment 应拆成两层：

- 知识层：白盒 Markdown 知识库和 Git 工作区
- 平台层：提交缓冲区、审核流、Agent Runner、搜索投影、Web 前后台和服务接口

知识层继续承担 canonical knowledge state。

平台层承担：

- 宽入口提交
- 审核与状态流转
- 任务调度和 Agent 托管执行
- 健康检查与问题队列
- 面向浏览与管理的 Web 能力

## 4. 当前运行时接口

当前企业接口分成两类：

- MCP：面向 Agent 和自动化流程
- REST / HTTP：面向 Web 门户和管理后台
- CLI：面向本地开发、运维和值班排障，统一入口为 `sediment`

其中现有稳定读接口仍保持：

- `knowledge_list`
- `knowledge_read`
- `knowledge_ask`

新增写入和治理能力不应直接写进知识层，而应先进入平台层的提案与审核流。

当前 CLI 统一成三组：

- `sediment server ...`
- `sediment kb ...`
- `sediment status ...`
- `sediment doctor`

运行配置统一来自 `config/sediment/config.yaml`。如果当前工作区没有该文件，
则按平台回退到用户级配置目录：

- macOS：`~/Library/Application Support/Sediment/config.yaml`
- Windows：`%APPDATA%/Sediment/config.yaml`
- Linux：`$XDG_CONFIG_HOME/sediment/config.yaml` 或 `~/.config/sediment/config.yaml`

当前内置的 Agent CLI backend 适配层支持：

- `claude-code`
- `codex`
- `opencode`

## 5. 当前设计的主线

Sediment 的当前设计不是把所有复杂性都压到 ingest，而是把系统拆成三段：

- 提交层负责把线索、文档和修订建议稳定送进系统
- 摄入与审核层负责“先落下来”并决定能否进入正式知识层
- 整理层负责长期结构治理，包括链接修复、placeholder 提升和索引重构

检索层则在此基础上做“索引优先，但不限制自由探索”的问答。

## 6. 读者如何使用这组文档

- 想理解知识文件该怎么写：看 [entry-model.md](entry-model.md)
- 想判断某个动作该由 ingest 还是 tidy 承担：看 [workflows.md](workflows.md)
- 想理解企业里谁可以提交、谁可以审核：看 [enterprise-governance.md](enterprise-governance.md)
- 想落服务和部署：看 [platform-architecture.md](platform-architecture.md)
- 想落接口、队列和审核状态：看 [interfaces-and-review-flow.md](interfaces-and-review-flow.md)
- 想落前后台页面：看 [web-surfaces.md](web-surfaces.md)
- 想设计 index 或调整检索路径：看 [retrieval-and-indexing.md](retrieval-and-indexing.md)
- 想新增巡检项或定义质量门槛：看 [validation-and-health.md](validation-and-health.md)
- 想拆实施阶段：看 [delivery-roadmap.md](delivery-roadmap.md)
