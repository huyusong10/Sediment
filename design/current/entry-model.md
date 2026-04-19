# 当前设计：条目模型

Sediment 当前使用三类知识条目：

- `concept`：概念、规则、边界、定义
- `lesson`：经验、教训、触发条件、风险判断
- `placeholder`：已知存在但尚未成形的知识缺口

正式条目放在 `entries/`，缺口条目放在 `placeholders/`。

补充判断：

- `entries/` 继续承载 canonical knowledge state
- `knowledge-base/insights/` 承载“推理出、待确认”的 `InsightProposal`
- `insights/` 是白盒层，但默认不属于公共 ask 的 canonical knowledge surface

## 1. Formal Entry Frontmatter

`concept` 和 `lesson` 统一使用 YAML frontmatter：

```yaml
type: concept | lesson
status: fact | inferred | disputed
aliases: []
sources: []
```

约束：

- `type` 必须是 `concept` 或 `lesson`
- `status` 必须是 `fact`、`inferred` 或 `disputed`
- `sources` 至少包含一个来源名，并且必须是纯文本
- `aliases` 可选，用于增强检索命中率，但不替代主标题
- `aliases` 只能表达同一知识实体的可查询表面；共现团队、事故、来源标题和上下文邻居不能冒充 alias

## 2. Concept

`concept` 用于表达稳定概念、规则和边界。

```markdown
---
type: concept
status: fact
aliases: []
sources:
  - 来源文档名
---
# [概念名]

[一句定义或规则]

## Scope
[适用范围、边界、前提条件、不适用场景]

## Related
- [[相关条目]] - 关系说明
```

要求：

- 标题使用裸概念名
- 首段必须能直接回答“X 是什么”
- `Scope` 必须有实质内容
- `Related` 至少包含一个真实知识链接

## 3. Lesson

`lesson` 用于表达经验、触发条件、因果链和风险判断。

```markdown
---
type: lesson
status: inferred
aliases: []
sources:
  - 来源文档名
---
# [规则句 / 判断句]

[核心结论]

## Trigger
[何时触发、什么情况下适用]

## Why
[因果链、证据、关键权衡]

## Risks
[忽略后的后果、常见误用、反例]

## Related
- [[相关条目]] - 关系说明
```

要求：

- 标题使用可检索的判断句，而不是抽象章节名
- 首段必须先给结论，再讲背景
- `Trigger`、`Why`、`Risks` 都必须有实质内容
- `Related` 至少包含一个真实知识链接

## 4. Placeholder

`placeholder` 只用于承认缺口，不用于存放低质量正式条目。

```markdown
---
type: placeholder
aliases: []
---
# [概念名]

这个概念在知识库中被引用了，但目前还没有足够清晰的定义可供提升。
```

要求：

- 文件必须明确说明“缺了什么”
- placeholder 可以作为 gap evidence 使用，但不能单独充当强证据

## 4.5 InsightProposal

`InsightProposal` 是平台层的白盒知识候选，不等同于正式条目。

当前目录与格式：

- 存放目录：`knowledge-base/insights/`
- 文件格式：Markdown + YAML frontmatter
- 典型 frontmatter：

```yaml
id: insight-hot-backup-workflow-1234abcd
title: Hot backup workflow
kind: workflow
review_state: proposed
origin: explore
```

正文固定包含：

- `Hypothesis`
- `Proposed Answer`
- `Supporting Entries`
- `Trigger Queries`
- `Review Notes`

约束：

- `review_state` 只表示工作流状态，不表示 epistemic truth
- proposal 可以被 `observe / reject / merge / promote`
- 只有 `promote` / `merge` 之后，知识才进入 canonical layer

## 5. Provenance 约束在条目模型中的落地

- 来源只放在 frontmatter `sources`
- `sources` 中不能写成 `[[wikilink]]`
- 正文中的 `Related` 只表达知识关系，不表达来源关系
- 如果正文中出现来源型链接，会被视为 provenance contamination

## 6. 命名与可检索性

条目命名首先服务于检索：

- `concept` 解决“什么是 X”
- `lesson` 解决“什么时候 / 为什么做 Y”

一条好条目的首段，应当能被问答系统直接拿来组成回答，而不需要先进行大量改写。

## 7. 代码与流程知识的提升边界

当前产品中，代码、配置、流程图和复盘文档里的稳定操作知识，也应被提升为正式条目，而不是停留在 provenance 或黑盒检索层：

- 代码里的异常类、失败状态、重试规则、TODO 缺口，如果构成稳定的运行时知识，应沉淀为可审阅的 formal entry，并保留类名 / 方法名作为 alias
- checklist、表格、runbook 和分阶段流程，如果回答的是“完整流程是什么”或“何时触发什么动作”，应提升为 canonical bare-term entry 或直接可问答的 procedure entry
- 文本类 / doc 标题如果本身带有管理、标准、指南等包装词，ingest 应投影出可直接问答的 canonical subject；例如 `谐振腔生命周期管理` 应沉淀为 `谐振腔生命周期`，而不是把“生命周期管理”原样当成碎片标题
- title merge 只能剥离 `管理`、`执行`、`checklist`、`调试模式` 这类 support wrapper；不能把 `启明仪式` 压回 `启明`，也不能把 `谐振腔生命周期` 压回 `生命周期`
- 句中嵌入的稳定公共能力也要显式提升成 bare-term entry；例如 `内置了定海针算法`、`由渡鸦团队介入调查` 这类结构，应沉淀为 `定海针`、`渡鸦团队` 等可审核条目，而不是停留在长句碎片里
- `数据质量`、`触发阈值`、`触发条件`、`部署策略` 这类结构化 wrapper 不能自己变成高频 entry；它们应把事实提升进 canonical 指标或动作条目，例如把 `嗡鸣度数据质量` 回灌到 `嗡鸣度`，把 `换羽触发阈值` 回灌到 `换羽`
- 结构化事实在 fanout 到其它条目时，必须只回灌命中目标的聚焦子句；不能把同段里的 `千机匣...`、`红线...` 之类全局句整段复制进 `换羽`、`渡鸦`、`哈基米` 等无关 summary
- runbook / checklist 的章节知识不能只停留在“首 10 分钟处置流程”“前置条件”这类结构标题上；它们应继续回灌到 `潮涌`、`启明`、`跃迁` 这类主概念条目的 `Scope`，让白盒 KB 能直接回答步骤、触发条件和回退链路
- 多个症状与根因之间存在明确因果链时，应把“症状 -> 原因 -> 动作”写进 `lesson` 或高信号 `Scope`，避免运行时只能命中泛化概念
- tidy / canonicalization 可以补充 bare-term、alias 和 related，但不能用 `X异常`、`X模块`、模板占位语这类低信息 summary 覆盖原本更强的 canonical 定义
- 对 `路由表`、`报文定义`、`监测点配置` 这类 wrapper artifact，ingest 应优先投影出更适合问答的 canonical subject（如 `信使路由策略`、`旋涡协议消息类型`、`回音壁监测点`），wrapper 保留为 alias 或 provenance，而不是成为并列低信号 formal entry
- 对 `启明执行`、`潮涌处理流程`、`听风者周报模板`、`账房审计系统` 这类 support-only title，ingest / tidy 应优先把触发条件、步骤、质量判断和审计发现回灌到 canonical entry，而不是留下平行浅层条目
- 对句内结构包装出来的公共表面，也要继续投影到 bare-term entry；例如 `驿站节点`、`隐身衣技术`、`嗡鸣度数据质量` 这类表达，最终应回到 `驿站`、`隐身衣`、`嗡鸣度` 等 canonical subject，并把部署策略、限制条件、质量判据写进 `Scope`
- canonical 条目的 `Scope` 不能只保留第一句泛化定义；当材料显式给出阈值、阶段、部署位置、质量信号、触发条件或审计发现时，这些高信号事实应优先保留在 `Scope`，供快速问答直接引用
- 表格标题、模板列名和 generic wrapper（如 `指标`、`核心指标`、`数据质量`）默认不是 formal entry；它们只有在被领域反复当作独立概念使用时才值得提升，否则应作为 canonical entry 的 `Scope` 事实存在
- 这类提升仍然必须遵守白盒原则：知识落在 `knowledge-base/entries/` 与索引网络中，而不是留在隐藏的代码旁路里
