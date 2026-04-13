# 当前设计：条目模型

Sediment 当前使用三类知识条目：

- `concept`：概念、规则、边界、定义
- `lesson`：经验、教训、触发条件、风险判断
- `placeholder`：已知存在但尚未成形的知识缺口

正式条目放在 `entries/`，缺口条目放在 `placeholders/`。

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
