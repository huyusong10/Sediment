# 当前设计：校验与巡检

Sediment 的校验目标不是把知识库变成僵硬表单，而是用少量高价值规则保护可靠性。

## 1. 条目硬校验

### 1.1 Formal Entry

所有 `concept` / `lesson` 必须满足：

- frontmatter 必须是有效的 YAML mapping
- `frontmatter.type` 合法
- `frontmatter.status` 合法
- `frontmatter.sources` 非空
- 首段或摘要区有实质性核心结论

### 1.2 Concept

`concept` 还必须满足：

- 有实质性的 `Scope`
- `Related` 中至少有一个真实 wikilink

### 1.3 Lesson

`lesson` 还必须满足：

- 有实质性的 `Trigger`
- 有实质性的 `Why`
- 有实质性的 `Risks`
- `Related` 中至少有一个真实 wikilink

### 1.4 Placeholder

`placeholder` 必须满足：

- `type: placeholder`
- 正文明确描述知识缺口

## 2. 轻量告警

以下问题不一定阻断使用，但应作为改进信号：

- `sources` 重复
- 摘要过长，难以直接用于查询与问答

## 3. 图谱与知识层巡检

health 应持续输出以下高价值问题：

- dangling links：知识正文中的链接没有目标
- orphan entries：正式条目几乎不与其他条目发生连接
- promotable placeholders：被多次引用、值得提升的缺口
- canonical gaps：正式条目仍然依赖 placeholder 作为关键概念
- provenance contamination：来源型链接污染了知识图谱
- root index skeleton：root index 长期停留在空骨架状态
- missing segment index：正式条目规模增长后仍没有分段入口
- low cluster coverage：formal KB 存在，但稳定 cluster surface 过薄
- latent cluster ready：某个 latent cluster 已满足物化为 `InsightProposal` 的阈值
- index cluster drift：当前 index 网络与高频 query cluster 已明显脱节

这些检查项的目的，是为 tidy 生成明确工作队列。

## 4. 索引巡检

索引层还需要额外检查：

- root index 是否存在
- index frontmatter 是否是有效的 YAML mapping
- index frontmatter 是否有效
- index 是否过载
- index 是否链接到未知目标或 placeholder
- 是否存在未被任何索引覆盖的正式条目

索引巡检关注的是“检索可达性”，而不是追求一棵形式完美的目录树。

## 5. Issue Queue Contract

企业部署下，health 不应只输出一段供人阅读的文本，而应输出结构化问题队列，供管理后台常驻展示。

每个 issue 至少应包含：

- `type`：问题类型，例如 `hard_failure`、`dangling_link`、`orphan_entry`
- `severity`：`blocking`、`high`、`medium`、`low`
- `target`：受影响的条目、索引或 placeholder
- `summary`：人类可快速理解的问题摘要
- `suggested_action`：推荐动作，例如 `run_tidy`、`edit_entry`、`promote_placeholder`
- `evidence`：必要的上下文、链接目标、缺失字段或引用列表

补充字段：

- `cluster_coverage`：当前 formal KB 被稳定 cluster / index 入口覆盖的比例
- `emerging_clusters`：高价值 latent knowledge signals 的摘要
- `canonical_stress_points`：被长尾 query 反复围攻的 canonical entry

管理后台至少要把这些 issue 分成两层：

- 阻断型问题：禁止合并、需要优先处理
- 提升型问题：不阻断使用，但应进入 tidy 或人工修复队列

## 6. 后台呈现要求

health 在后台中的呈现不应只是总数面板，还应支持：

- 按类型、严重度、责任域筛选
- 直接跳转到受影响条目或索引
- 查看具体缺失段落、断链目标、引用上下文
- 对高价值问题一键创建 tidy 任务

## 7. 设计意图

巡检和校验都应保持克制：

- 约束真正影响可靠性的部分
- 避免把写作负担转嫁给知识录入者
- 让 Agent 与人工维护者都能快速理解问题所在
- 对 malformed frontmatter，应优先产出结构化 hard failure，而不是让整轮 health / audit 直接中断

如果某条规则只会增加格式成本，却不能显著提升检索、整理或审阅质量，它就不应成为通用硬约束。
