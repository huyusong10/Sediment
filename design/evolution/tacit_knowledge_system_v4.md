# 隐性知识提取系统设计文档（v4）

> 状态：历史快照
> 当前入口：见 [design/README.md](../README.md)
> 后续拆分：v4 中稳定的条目模型与职责边界，已拆入 `design/current/` 下的主题文档。

---

## 1. 核心精神

Sediment 的核心目标不是“自动化得越多越好”，而是把企业中的隐性知识沉淀为一个：

- **白盒**：知识直接保存在文件系统中，可被人类直接打开和修改
- **可信**：来源明确、结构稳定、不会把 provenance 混进知识图谱
- **可维护**：对中等水平的 LLM 也足够稳健，整理和巡检不会因为条目过于自由而失控
- **可协作**：人类、脚本和 Agent 围绕同一份 Markdown 数据工作

Sediment 追求的是“提炼过的知识层”，不是原始材料的镜像，也不是一套黑盒索引系统。

---

## 2. v4 为什么不直接沿用 v3 条目模板

v3 的核心精神是对的，但其条目模板存在几个问题：

- 自由叙述比例过高，导致整理和巡检难以稳定判断条目质量
- `[[来源文档]]` 容易把 provenance 和知识图谱混在一起
- “概念/规范”与“经验/教训”虽然分了两类，但结构边界不够清晰
- 对高水平 LLM 友好，但对中等水平 LLM 缺乏下限保护

因此 v4 做了两个调整：

1. **保留 v3 的核心精神**
2. **重做条目结构，采用中结构方案**

v4 不追求完全自由，也不追求过重 schema，而是选择一套足够约束下限、又不至于过度僵化的结构。

---

## 3. 知识条目模型

v4 中，知识库只有三种条目类型：

- `concept`：概念、规则、边界、定义
- `lesson`：经验、教训、触发条件、风险判断
- `placeholder`：已知存在但尚未成形的知识缺口

所有条目都以 Markdown 文件保存。

### 3.1 Frontmatter

v4 统一使用 YAML frontmatter 保存关键元数据：

```yaml
type: concept | lesson | placeholder
status: fact | inferred | disputed   # 仅 concept / lesson 需要
aliases: []                          # 可选
sources: []                          # 仅 formal entry 必需，纯文本来源名
```

原则：

- `sources` 是 provenance 元数据，不参与知识图谱
- `sources` 中必须使用纯文本来源名，不能写成 `[[wikilink]]`
- `aliases` 用于提升可检索性，但不替代主标题

### 3.2 标题规则

- `concept` / `placeholder`：使用裸概念名
- `lesson`：使用可检索的规则句或判断句

判断标准：

- 如果用户会问“什么是 X”，通常应建 `concept`
- 如果用户会问“什么时候 / 为什么应该做 Y”，通常应建 `lesson`

---

## 4. v4 条目结构

### 4.1 Concept

用于定义稳定的概念、规则和边界。

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
[适用范围、前提条件、边界、不适用场景]

## Related
- [[相关条目]] - 关系说明
```

要求：

- 首段必须能直接回答“X 是什么”
- `Scope` 负责表达边界，而不是堆砌背景说明
- `Related` 是显式图谱索引，至少应有一个真实关联

### 4.2 Lesson

用于表达经验、风险、触发条件和操作判断。

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

- 首段必须给出判断，而不是先讲背景
- `Trigger` 负责告诉 Agent 什么时候该想到这条知识
- `Why` 负责支撑可信度
- `Risks` 负责保护下限，防止误用

### 4.3 Placeholder

用于保持知识网络连通，同时承认当前知识还不够完整。

```markdown
---
type: placeholder
aliases: []
---
# [概念名]

这个概念在知识库中被引用了，但目前还没有足够清晰的定义可供提升。
```

placeholder 的职责只有一个：指出缺口。它不是低质量正式条目。

---

## 5. Provenance 原则

这是 v4 最重要的设计改变之一。

### 5.1 来源不是图谱节点

来源文档、复盘标题、方案名、文件名默认都属于 provenance，不属于知识图谱中的概念节点。

因此：

- 来源必须进入 frontmatter `sources`
- `Source/来源` 区域只视为 provenance
- provenance 不参与 dangling link 检查
- provenance 不参与 placeholder 引用计数
- provenance 不参与 detective mode 的归纳上下文

只有当某个文档名本身已经在多个上下文中被当成一等领域概念使用时，才可以单独成为知识条目；这种情况必须明确判断，不能默认发生。

### 5.2 为什么要这么做

如果 provenance 混入图谱，会造成几个后果：

- 整理阶段生成大量伪 placeholder
- 归纳推理从来源标题而非知识正文中“猜定义”
- 图谱被来源噪音污染，影响检索质量

v4 明确禁止这种混用。

---

## 6. 系统职责边界

### 6.1 Ingest

摄入的职责是：

- 从原始材料中提炼 `concept`、`lesson`、`placeholder`
- 写出满足 v4 结构的条目
- 保留来源元数据

摄入**不负责**：

- 过度优化知识粒度
- 全局重构既有知识
- 因为一个概念只被提到一次就强行拆成很多碎片

原则：摄入阶段只做“足够好的首次提炼”。

### 6.2 Tidy

整理的职责是：

- 修复结构不合法的 v4 条目
- 修复真实的图谱断链
- 提升高引用 placeholder
- 为孤立条目补充合理连接

整理**不负责**把 provenance 当知识去扩图。

### 6.3 Retrieve

检索的职责是：

- 优先使用 `concept` 回答“什么是 X”
- 优先使用 `lesson` 回答“什么时候 / 为什么做 Y”
- 必要时跨条目综合
- 明确标注 gaps 与 contradictions

### 6.4 Health Check

巡检的职责是：

- 报告结构硬错误
- 报告图谱健康度
- 报告 placeholder 提升机会
- 报告 concept coverage 缺口

巡检不是为了追求形式完美，而是为了给整理提供稳定工作队列。

---

## 7. 最小必要校验

v4 的校验规则故意保持克制，只约束真正重要的部分。

### 7.1 Formal Entry

所有 `concept` / `lesson` 必须满足：

- 有合法 `type`
- 有合法 `status`
- 有非空 `sources`
- 有可检索的首段核心结论

### 7.2 Concept 必须满足

- 有 `Scope`
- 有 `Related`

### 7.3 Lesson 必须满足

- 有 `Trigger`
- 有 `Why`
- 有 `Risks`
- 有 `Related`

### 7.4 Placeholder 必须满足

- `type: placeholder`
- 有明确缺口说明

### 7.5 v4 明确不再强制的事项

以下内容可以鼓励，但不作为通用硬约束：

- 固定数量的 inline wikilink
- `Why This Matters`
- `Common Pitfalls`
- `Evidence / Reasoning`
- `date`
- `tags`

原因很简单：这些要求会抬高格式成本，却不总是提高知识质量。

---

## 8. 演进原则

v4 不是为了让模板更复杂，而是为了让系统更稳。

未来如果继续演进，应遵守：

1. 先保护白盒和 provenance 边界
2. 再考虑自动化和智能化增强
3. 任何新结构都必须解释它如何改善中等 LLM 的稳定下限
4. 不允许为了追求检索指标而把条目写成机器友好、但人类难读的格式

Sediment 的目标始终不是“更像数据库”，而是“更像一个可靠、可审阅、可协作的知识层”。
