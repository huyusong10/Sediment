# 隐性知识提取系统设计草案（v5 / Insights）

> 状态：draft
> 当前正式入口：见 [../README.md](../README.md)
> 本文目的：沉淀下一代 Sediment 架构草案，重点回答 `explore / tidy / insights / human-in-the-loop / Git 闭环` 如何形成长期稳定系统。

## 附：门户图二次优化判断

在 v5 实现推进后，Graph 的产品定位进一步收敛为：

- 首页不是“图 + 右侧信息卡”的工作台，而是全宽单行的 `知识宇宙` hero
- `/portal/graph-view` 不是门户普通子页，而是纯 3D 的沉浸式 `展开宇宙`
- 节点详情默认通过右侧 `focus sheet` 阅读，不再把用户推去单独条目页
- 门户图的视觉核心不是“知识之间有连线”，而是“新知识从既有碎片中迸发、凝聚并稳定下来”

因此，portal graph 的实现契约进一步强调：

- 小核心点、强 halo、路径脉冲、粒子喷发和 formation playback
- 只表现近期或仍有能量的知识形成局部
- 事件不足时允许使用稳定 canonical 补足构图，但仍保持形成语义

---

## 1. 这次演进要解决什么问题

Sediment 的核心目标一直不是“把材料收进来”，而是把组织中的隐性知识沉淀为可审阅、可协作、可迁移的知识层。

当前系统已经完成了两件事：

- `ingest` 负责把原始材料提炼成正式条目
- `tidy` 负责长期结构治理

但当前 `explore` 仍然更像“在正式知识层上做轻量综合”，还没有成为真正的“隐性知识发现器”。

典型问题：

- 用户会反复询问一个稳定、高价值、可迁移的问题
- 正式 KB 中已经有足够多的碎片证据
- 这些证据尚未被压缩成 canonical entry
- `explore` 仍然可能因为没有直接命中条目而掉入 gap

这说明当前系统还缺一层：

- 它不是 canonical knowledge
- 它不是原始材料
- 它不是纯日志
- 它是“正在形成中的知识”和“围绕这些知识的行为信号”

本文把这层暂时命名为：`Insights`

---

## 2. 设计判断

### 2.1 `tidy` 与 `explore` 是跷跷板两端

这次设计明确承认一个结构性张力：

- `tidy` 越重，更多隐性知识会被预先压缩进正式知识层，`explore` 可以更轻
- `explore` 越重，更多隐性知识会在问答时临时推理，正式知识层可以更薄

本草案偏向：

- `tidy` 更重
- `explore` 更轻，但仍保留“发现隐性知识并反馈”的能力

原因：

- 组织知识通常符合二八分布：`80%` 的使用集中在 `20%` 的知识
- 高频、高价值、稳定的问题，应优先被压缩为 canonical knowledge
- 低频、临时、跨域组合的问题，则继续由 `explore` 承担

### 2.2 真正要控制的不是磁盘，而是知识膨胀

需要控制的不是单纯“条目数变多”，而是两种更危险的膨胀：

- 检索膨胀：同一知识被多个浅层条目、包装词标题和相近碎片重复表达
- 认知膨胀：人和 Agent 都不知道该维护哪一条、该信任哪一条

因此，v5 的重点不是“少存知识”，而是：

- 把高 ROI 的隐性知识压缩进正式知识层
- 把低 ROI 或尚不稳定的知识停留在 Insights 层
- 让 `tidy` 负责持续压缩、合并、归档和提升

### 2.3 `explore` 可以直接落盘，但不能直接进入 canonical state

`explore` 如果抽取出了隐性知识，可以直接物化为白盒对象，但不能立即进入 `knowledge_ask` 默认可见范围。

否则会出现：

- 系统消费自己刚推理出来、尚未确认的知识
- 组织共识被未审阅推断直接污染
- 问答结果对后续问答形成自我放大回路

因此必须把“已形成组织共识的知识”和“正在形成中的知识”明确分层。

---

## 3. 新的系统分层

v5 建议把 Sediment 拆成四层：

| 层 | 作用 | 是否进入默认 ask 可见范围 |
| --- | --- | --- |
| `Canonical Knowledge` | 正式知识层，承载当前组织共识 | 是 |
| `Insights` | 正在形成中的知识候选，等待人工确认、合并或淘汰 | 否 |
| `Signals` | 关于问题、证据、频率、成熟度的行为信号 | 否 |
| `Strategy` | 决定这次任务走哪条路线的兵法层 / 路由层 | 不直接暴露为知识 |

### 3.1 Canonical Knowledge

继续沿用现有：

- `entries/`
- `placeholders/`
- `index.root.md`
- `indexes/`

这是正式知识层，也是 `knowledge_ask` 默认读取的唯一组织共识来源。

### 3.2 Insights

新增一层白盒但非 canonical 的知识候选层，建议采用单独目录，例如：

```text
knowledge-base/
  entries/
  placeholders/
  indexes/
  insights/
```

Insights 层用于保存：

- `explore` 抽取出来、但尚未被人工确认的隐性知识
- 被频繁询问、正在逐渐成形的 latent concept / latent workflow / latent lesson
- 待进一步 merge / promote / archive / reject 的知识候选

Insights 是文件系统中的可审阅对象，但默认不参与公开问答共识。

### 3.3 Signals

Signals 不应直接污染 Git 工作区；它更适合放在平台层的工作流存储中，作为长期行为信号层。

Signals 记录：

- 用户问了什么
- 问了多少次
- 有多少不同用户 / 会话询问
- 当前问题直达命中了哪些 formal entry
- 哪些问题只能依赖 synthesized answer
- 哪些 latent cluster 的证据正在趋稳

### 3.4 Strategy

`Strategy` 是兵法层，用来描述“这次任务应该如何使用工具”，而不是把所有工具统一暴露给 Agent 随机选择。

建议至少支持这些 profile：

- `fast-answer`
- `white-box-research`
- `insight-harvest`
- `tidy-refactor`

每种策略都约束：

- 可见工具集合
- 允许的写入边界
- 是否允许产生 insight proposal
- 是否允许进入 repo-level 治理动作

---

## 4. 对象模型重构

### 4.1 当前 `type / status` 已不足够

现有模型中的：

- `type`
- `status`

足以描述 `concept / lesson / placeholder`，但不足以描述 “推理得到、待确认、已拒绝、长期未使用、需要归档” 这类状态。

因此 v5 建议把条目元数据拆成多个正交维度，而不是继续把所有语义压进一个 `status` 字段。

### 4.2 v1 的建模原则：先极简，再长大

本草案在第一版实现上不追求“一次把所有治理字段做全”。

v1 的优先级是：

- 先跑通 `explore -> signal -> insight proposal -> review -> promote`
- 先让人类一眼看懂 proposal
- 先让 MCP、本地 Skill、CLI、后台工作台共用一套最小语义

因此，v1 建议把字段分成三层：

- `必须有`
- `可以后算`
- `先不要做`

这里的核心原则是：

- `InsightProposal` 偏“人类可读”
- `Signals` 偏“机器可算”
- 复杂聚类、责任域、淘汰策略等高级治理字段，放到后续阶段再补

### 4.3 Insight Proposal 的基本语义

Insight Proposal 是：

- 一个白盒对象
- 认识论上通常是 `inferred`
- 工作流上默认是 `proposed`
- 来源上通常是 `explore`

它表达的不是“系统已经确认这是真的”，而是：

- “系统在正式 KB 中看到了足够多的证据，认为这是一条值得人类进一步确认和沉淀的知识”

### 4.4 v1 最小 Contract

#### `ExploreEnvelope`

`ExploreEnvelope` 是一次 `explore` 运行的统一结果对象。它是运行时对象，不一定落盘进 Git。

v1 建议只保留这些字段：

| 字段 | 示例值 | 说明 |
| --- | --- | --- |
| `query` | `外乡人的入职流程是什么` | 用户原始问题 |
| `entrypoint` | `mcp` / `local-skill` / `cli` / `web` | 从哪里触发本次 explore |
| `strategy` | `fast-answer` / `insight-harvest` | 本次采用的兵法 profile |
| `mode` | `direct` / `synthesized` / `gap` | 回答态 |
| `answer` | `<text>` | 实际给用户的答案 |
| `confidence` | `low` / `medium` / `high` | 系统对本次答案的置信度 |
| `sources` | `<entry ids>` | 这次回答依赖的 canonical entries |
| `proposal_state` | `none` / `ready` / `materialized` | 是否进入后续 insight 闭环 |

v1 暂不要求在 `ExploreEnvelope` 中显式保存：

- `query_cluster_id`
- `evidence_cluster_id`
- `contradictions`
- `demand_delta`
- `maturity_estimate`

这些更适合作为 Signals 层的内部计算结果，而不是第一版对外 contract 的必选字段。

#### `InsightProposal`

`InsightProposal` 是被 materialize 之后的白盒候选对象，建议以 Markdown + frontmatter 保存到 `insights/`。

v1 建议只保留这些字段：

| 字段 | 示例值 | 说明 |
| --- | --- | --- |
| `id` | `insight-xxxxx` | 稳定标识 |
| `title` | `外乡人入职流程` | 给人看的标题 |
| `kind` | `workflow` / `concept` / `lesson` / `mapping` | 这条候选大致属于哪类隐性知识 |
| `hypothesis` | `<text>` | 系统正在提出的判断 |
| `proposed_answer` | `<text>` | 当前综合出的候选答案 |
| `supporting_entries` | `<entry ids>` | 直接支撑这条候选的正式条目 |
| `trigger_queries` | `<questions>` | 是哪些问题把它“问出来”的 |
| `review_state` | `proposed` / `observing` / `promoted` / `merged` / `rejected` / `archived` | 当前审阅状态 |
| `origin` | `explore` / `tidy` / `manual` | 这条候选最初从哪里来 |

v1 暂不要求在 `InsightProposal` 中显式保存：

- `epistemic_status`
- `criticality`
- `owner_domain`
- `demand_snapshot`
- `maturity_snapshot`
- `suggested_target`

这些字段并非没有价值，而是更适合作为第二阶段的治理增强，而不是第一阶段的必选负担。

### 4.5 `InsightProposal` 的 v1 文件形态

v1 建议：

- `InsightProposal` 放在 `knowledge-base/insights/`
- 继续使用 Markdown + frontmatter
- 尽量复用现有条目文件的阅读体验，而不是重新发明一套格式
- 但必须通过目录与 `review_state` 明确区分它不是 canonical entry
- 多个 proposal 可以同时以脏文件形式共存于 `insights/`
- `insight_review` 提交只允许覆盖当前 proposal 与目标 canonical/index 路径，不能顺手提交整个 `knowledge-base/`
- review 过程中只能容忍 `insights/` 层既有脏状态；canonical / indexes / placeholders 的脏状态仍应阻塞提交

建议的最小模板：

```markdown
---
id: insight-<stable-id>
kind: workflow
review_state: proposed
origin: explore
supporting_entries:
  - 冷启动
  - 试音
  - 晚课
trigger_queries:
  - 外乡人的入职流程是什么
---

# 外乡人入职流程

## Hypothesis

正式 KB 中隐含了一条相对稳定的外乡人入职主线，但尚未被压缩为 canonical entry。

## Proposed Answer

<当前综合出的候选答案>

## Supporting Entries

- [冷启动](../entries/冷启动.md)
- [试音](../entries/试音.md)
- [晚课](../entries/晚课.md)

## Trigger Queries

- 外乡人的入职流程是什么

## Review Notes

- 初始由 explore 自动生成
```

v1 不建议在 `InsightProposal` 中强制加入：

- `Related`
- 图谱边
- 复杂打分
- 责任域
- 淘汰策略

这些能力更适合在后续治理阶段逐步补上。

---

## 5. Explore 的新职责

### 5.1 Explore 的三态回答模型

`explore` 的结果不再只区分“答出来 / 答不出来”，而应至少区分三种回答态：

- `direct`
  - 直接命中 canonical entry
- `synthesized`
  - 没有单一条目，但能从多个 formal entry 综合出稳定答案
- `gap`
  - 即使扩展后仍然证据不足

这三种结果都要进入反馈闭环。

### 5.2 Explore 的四段执行流程

`explore` 采用“脚本优先，LLM 归纳”的结构，不以 embedding / 黑盒 RAG 为中心。

#### 第一段：Deterministic Retrieval

先走可解释、可复现的脚本层：

- index routing
- title / alias match
- `Related` / graph neighborhood
- `Scope / Trigger / Why / Risks` 里的高信号片段
- 回链和一跳邻居

#### 第二段：Heuristic Expansion

直达命中失败后，允许做有限启发式扩展：

- wrapper 去壳
- 短语拆分
- 流程词识别
- 角色 / 动作 / 阶段线索恢复
- 共享 provenance 的弱聚类

约束：

- provenance 仍不是知识节点
- 共享 provenance 只能作为召回或聚类线索，不能直接当强证据

#### 第三段：LLM Synthesis

LLM 只在一个经过脚本层准备的小 evidence pack 上做综合：

- 它不负责大海捞针
- 它负责回答“这些 formal entry 是否足以综合出一个稳定结论”

#### 第四段：Feedback

不论结果是 `direct / synthesized / gap`，都必须写回信号层。

### 5.3 Evidence Boundary

Explore 的证据边界保持严格：

- 默认只允许使用已合并的正式 KB
- 不读取原始材料作为公开问答证据
- 不读取未审阅提交
- 不把来源名直接视为概念

如果未来引入 embedding / RAG，也只能作为加速器，而不能成为真相源。

### 5.4 国际化协议归 `explore`

v1 建议把跨语言处理明确收敛到 `explore`，而不是散落到 Signals、Insights 或 Canonical 层。

每个知识库应声明：

- `default_language`

每次 ask 时，`explore` 负责：

1. 检测 `query_language`
2. 当 `query_language != default_language` 时，先生成 `kb_normalized_query`
3. 检索、聚类、evidence synthesis 一律优先使用 KB 默认语言
4. 最终回答再按用户语言输出

这意味着：

- Canonical knowledge 保持单语主轴
- 多语言输入输出能力属于交互层，而不是知识层复制
- `signals` 需要记录 `raw_query_language`、`kb_language`、`response_language`
- `InsightProposal` 默认使用 KB 默认语言撰写正文
- 多语言能力在 v1 只要求 `aliases` / `display_title`，不要求多语 canonical 并列条目

这样可以避免同一知识因为多语言输入而被切碎成多套 canonical graph。

---

## 6. Signals 与反馈机制

### 6.1 记录什么

Signals 应至少捕获：

- 原始问题
- 归一化问题簇 / query cluster
- 是否命中 `direct`
- 是否走到 `synthesized`
- 命中的 formal entry 集合
- evidence cluster
- 问题的时间分布
- 不同用户 / 会话数量

### 6.2 两个核心分数

建议把反馈机制分成两个主分数：

- `demand_score`
  - 由频次、最近活跃度、不同用户数、问题重要性组成
- `maturity_score`
  - 由证据充分度、答案稳定性、命中 formal entry 的重合度、是否存在明确回灌目标组成

这比单纯“被问了多少次”更稳。

但在 v1 中，这两个分数更适合作为 Signals 层的内部计算结果，而不是强行暴露为 `ExploreEnvelope` 或 `InsightProposal` 的必选字段。

也就是说：

- v1 可以先“内部有分数，外部少字段”
- v2 再决定是否把这些分数显式暴露给工作台或 Git 对象

### 6.2.1 v1 的最小聚类规则

v1 不追求“大而全的语义聚类”，而采用保守、可解释、可调试的最小规则集。

核心原则：

- 宁可分裂一点，也不要错误合并
- 不以 embedding / 黑盒相似度为默认真相源
- 先把 query cluster 和 evidence cluster 跑稳，再逐步增加复杂度

v1 的最小 signal 字段建议是：

- `raw_query`
- `language`
- `intent`
- `subject_hint`
- `result_mode`
- `source_entries`
- `timestamp`
- `session_or_user_hash`

v1 的 query normalization 顺序建议是：

1. 先按语言分桶
2. 做轻量文本归一化：空白、全半角、标点、拉丁大小写
3. 抽取一个很小的 `intent` 集合：
   - `definition`
   - `workflow`
   - `relation`
   - `risk`
   - `comparison`
4. 只剥离通用问句外壳，不剥离领域词
5. 再用 canonical `title / alias / index routing` 做白盒归并

v1 的 query cluster key 更接近：

- `<language> + <intent> + <normalized subject>`

v1 的合并规则建议是：

- 同语言
- 同 `intent`
- `subject_hint` 命中同一 canonical target 或 alias
- 若主体尚不稳定，则允许通过 `source_entries` 高重合形成同一 evidence cluster
- 其余情况不强行合并

这是一种保守但稳的起点，更适合后续治理和人工审阅。

### 6.3 物化策略

为避免 Git 与工作区被海量一次性问答污染，本草案当前偏向：

- 每次问答都写 `signal`
- 只有当某个 latent candidate 跨过阈值时，才 materialize 成 `insight proposal`

这样能同时满足：

- 不丢失行为信号
- 控制 Git 噪声和仓库膨胀
- 仍然保留白盒的、可审阅的 insight 候选对象

### 6.4 曾考虑过的替代方案

另一种更激进的方案是：

- 只要 `explore` 抽取出了 latent knowledge，就立即落盘成 insight 文件

这个方案的优点：

- 所有 latent knowledge 都被显式保存
- 人类更容易直接看到一次回答产生了什么

缺点：

- repo churn 很大
- 大量低价值或一次性问题会快速污染工作区

当前 draft 暂偏向“Signals 全量记录，Insights 阈值物化”，但这仍是需要继续确认的设计点。

### 6.5 聚类健康与 tidy 队列

v1 直接把聚类质量纳入 health / tidy 队列，而不是等到图做出来后再补。

建议新增这些结构化 issue 类型：

- `root_index_skeleton`
  - `summary`: root index 仍是空骨架，未承担顶层入口职责
  - `suggested_action`: `run_tidy_indexes`
- `missing_segment_index`
  - `summary`: 已形成稳定 cluster，但缺少对应 segment index
  - `suggested_action`: `run_tidy_indexes`
- `low_cluster_coverage`
  - `summary`: formal entries 已明显增长，但稳定 cluster / segment 覆盖率过低
  - `suggested_action`: `run_tidy_full`
- `latent_cluster_ready`
  - `summary`: latent cluster 已趋稳，应 materialize 为 insight proposal 或进入 tidy
  - `suggested_action`: `materialize_insight`
- `index_cluster_drift`
  - `summary`: 现有 segment index 与实际知识簇明显漂移
  - `suggested_action`: `run_tidy_indexes`

v1 的初始触发阈值建议是：

- `root_index_skeleton`
  - 当 `formal_entry_count >= 30` 且 root index 仍接近默认脚手架，或仅有极少有效出链
- `missing_segment_index`
  - 当某个稳定 cluster 的 `member_count >= 8`，且没有 segment index 能覆盖其大部分成员
- `low_cluster_coverage`
  - 当 `formal_entry_count >= 30` 且稳定 cluster 覆盖率低于 `50%`
- `latent_cluster_ready`
  - 当某个 query / evidence cluster 已反复出现，且需求与证据都达到 proposal 阈值，但系统尚未物化 insight
- `index_cluster_drift`
  - 当 segment index 的链接覆盖与实际 cluster 成员重合度明显过低

这些阈值在 v1 中应视为默认启发式，而不是不可调整的硬常量。

---

## 7. Insights 层的生命周期

### 7.1 形成路径

建议的主路径：

1. 用户提问
2. `explore` 返回 `direct / synthesized / gap`
3. Signals 更新
4. 某个 latent cluster 达到阈值
5. 系统 materialize 一个 `insight proposal`
6. 进入人工审阅与 tidy 重构闭环

### 7.1.1 v1 状态机

v1 建议把状态机明确拆成两段，而不是把平台内部状态和 Git 中的对象状态混在一起。

#### A. Signals 内部状态

这部分主要存在于平台层，不要求直接落 Git：

1. `captured`
   - 一次 ask 已被记录为 signal
2. `clustered`
   - 它已被归入某个 query / evidence cluster
3. `ready`
   - 该 cluster 已达到 materialize proposal 的阈值

#### B. InsightProposal 外显状态

这部分通过 `insights/` 中的对象对人类可见：

1. `proposed`
   - 系统刚刚物化出的候选
2. `observing`
   - 暂不提升，继续累积信号与证据
3. `promoted`
   - 已提升为新的 canonical knowledge
4. `merged`
   - 已并入既有 canonical entry
5. `rejected`
   - 被确认是误判、噪声或不值得沉淀
6. `archived`
   - 长期保留价值不足，但不视为错误

#### C. 关键迁移规则

- 每次 ask 都会创建 `captured`
- 聚类后进入 `clustered`
- 达阈值后进入 `ready`
- `ready` 才允许 materialize 为 `proposed`
- `proposed` 可以直接进入 `promoted` / `merged` / `rejected`
- 如果暂时不决，则进入 `observing`
- `observing` 之后仍可进入 `promoted` / `merged` / `rejected` / `archived`

v1 的关键原则：

- `promote` 与 `merge` 是对 canonical knowledge 的显式治理动作
- `rejected` 与 `archived` 必须保留历史痕迹，避免系统重复制造同类噪声
- canonical knowledge 本身不复用这套状态机；它继续沿用正式知识层已有治理规则

### 7.2 人工可执行动作

领域 committer 面对某个 insight proposal 时，建议至少能做四类决策：

- `promote`
  - 提升为正式知识
- `merge`
  - 并入已有 canonical entry
- `keep_observing`
  - 暂不提升，继续积累信号
- `reject`
  - 标记为误判、噪声或不值得沉淀

### 7.2.1 v1 的 canonical promotion 默认规则

v1 不采用“一律新建条目”或“一律回灌既有条目”的极端策略。

默认规则是：

- 局部知识优先回灌
- 跨条目稳定知识优先新建

更具体地：

- 如果某条 insight 只是补充某个既有 canonical subject 的事实、阈值、风险、适用边界或 alias，优先 `merge`
- 如果某条 insight 回答的是一个稳定、可命名、会被反复问的问题，而且天然跨越多个 formal entries，优先 `promote`
- 如果某条 insight 只是包装词、映射词、别名或表面变体，优先并入 alias / 既有条目，而不单独建条目
- 如果证据仍然不足够稳，则继续停留在 `observing`

建议把下面这些条件当作“更偏向新建 canonical entry”的信号：

- 跨 `3` 个以上 formal entries
- 涉及 `2` 个以上阶段、角色或子流程
- 有自然、稳定、用户会直接使用的标题
- 重复出现，需求明显
- 单靠回灌某一篇 entry 仍然难以稳定回答

这类知识通常更适合作为被压缩后的新 canonical subject，而不是继续散落在多个局部条目中。

### 7.3 Tidy 介入后的重构动作

`tidy` 在 v5 中不再只是“整理器”，而是“知识重构器”。

它在 Insights 层的职责包括：

- 合并重复 insight candidate
- 拆分过于混杂的 candidate
- 把成熟 candidate 提升为 canonical knowledge
- 把 support facts 回灌到现有 canonical entry
- 归档长期低价值、低成熟度的 candidate
- 删除明显噪声、错误聚类或无保留价值的 candidate

### 7.4 删除与归档规则

需要特别注意：

- 不能简单按“长期未使用”删除知识
- 很多低频知识是高价值知识，例如事故处置、审计边界、灾备流程

因此建议：

- `Insights` 层允许基于 `demand + maturity + age + duplication` 做归档或删除
- `Canonical` 层默认不做激进物理删除，更偏向 `merge / archive / deprecate`
- `critical / pinned` 对象不参与常规冷度淘汰

---

## 8. Human in the Loop

### 8.1 人类不是每次都要亲自写知识

v5 的人机协作不应退化为：

- Agent 只是发现问题
- 人类每次都要重新写一遍条目

更合理的分工是：

- 用户提供需求信号
- `explore` 提供候选与证据包
- `tidy` 做批量重构与压缩
- committer 负责确认哪些形成中的知识应成为组织共识
- owner 负责规则、阈值、生命周期和权限边界

### 8.2 人工介入点

建议明确四个 HITL 介入点：

1. 用户提问，提供 `demand`
2. committer 审阅 insight proposal
3. committer 决定 promote / merge / observe / reject
4. owner / 平台维护者维护阈值、保留策略、策略 profile 和 Dashboard 视图

### 8.3 治理边界

HITL 的关键约束：

- `knowledge_ask` 默认只读 canonical knowledge
- Insights 默认不直接成为公开组织共识
- 本地 Skill 与 MCP 都不能绕过这一边界

---

## 9. Git、Job 与长期闭环

### 9.1 Commit 不应只有两类

当前系统里自动 commit 主要围绕：

- `ingest`
- `tidy`

v5 需要扩展为更清晰的语义层。

建议的系统操作类型：

- `explore-capture`
- `tidy(insights)`
- `tidy(promote)`
- `ingest`

### 9.2 推荐提交语义

建议：

- `explore-capture: <insight-cluster>`
  - 只落盘 insight candidate，不改 canonical knowledge
- `tidy(insights): <reason>`
  - 合并、拆分、归档、删除 insight candidate
- `tidy(promote): <reason>`
  - 将成熟 insight 提升或回灌进 canonical knowledge
- `ingest: <batch>`
  - 保持现有首次提炼语义

### 9.3 闭环

完整闭环应当是：

1. 问题驱动 demand
2. `explore` 产生信号
3. Signals 聚合出 latent cluster
4. threshold-crossing 产生 insight proposal
5. `tidy` 重构 insight 池
6. committer promote 或 merge
7. canonical knowledge 更新
8. 后续相同问题更容易 direct hit

---

## 10. MCP、本地 Skill 与统一 Contract

### 10.1 不应为不同入口造两套业务语义

MCP 与本地 Skill 是两种入口，不应该演化成两套彼此独立的业务 contract。

建议统一为两个核心对象：

- `ExploreEnvelope`
- `InsightProposal`

无论调用来源是：

- `knowledge_ask`
- 本地 Explore Skill
- CLI
- 后台工作台

都应尽量产出相同结构。

v1 的重点不是“先把 contract 做到最全”，而是“先让所有入口说同一种最小语言”。

因此：

- `ExploreEnvelope` 先保持极简
- `InsightProposal` 先保持人类可审
- 聚类 ID、复杂分数、责任归属等高级字段放到后续治理阶段

### 10.2 Transport Adapter

在统一 contract 之上，再允许多个 transport：

- MCP / server-side ask
- 本地白盒 Skill
- CLI sink
- outbox sink

这样本地 Skill 不需要强依赖在线服务才能参与闭环。

### 10.3 兵法层 / Strategy Profile

本草案明确把“兵法问题”上升为一等设计对象。

建议的 profile：

- `fast-answer`
  - 只允许服务端快答
- `white-box-research`
  - 只允许 list/read 或本地白盒探索
- `insight-harvest`
  - 允许综合并产生 insight proposal
- `tidy-refactor`
  - 允许治理、提升、归档和结构重构

这些 profile 的核心作用：

- 限定工具集合
- 限定写入权限
- 限定是否允许产生 insight candidate
- 避免多个工具链并行冲突、重复劳动或产生不一致结论

### 10.4 v1 策略矩阵

v1 建议直接把四个 profile 定成下面这张表：

| Profile | 主要目标 | 允许读取 | 允许写入 | 是否允许 synthesis | 是否允许 materialize insight | 是否允许改 canonical |
| --- | --- | --- | --- | --- | --- | --- |
| `fast-answer` | 低延迟回答问题 | canonical knowledge | signals | 是，轻量 | 否 | 否 |
| `white-box-research` | 白盒探索与人工分析 | canonical knowledge、indexes、本地只读上下文 | signals | 是，较深 | 否 | 否 |
| `insight-harvest` | 抽取隐性知识并形成候选 | canonical knowledge、indexes、signals 摘要 | signals、insights | 是 | 是 | 否 |
| `tidy-refactor` | 治理、提升、合并、归档 | canonical knowledge、insights、indexes | insights、canonical knowledge、indexes | 否，默认不是问答模式 | 否，主要消费既有 proposal | 是，但必须经过 review gate |

v1 进一步建议：

- `fast-answer` 可以返回 `direct` 或轻量 `synthesized`，但只写 signals，不写 `insights/`
- `white-box-research` 用于本地 Skill 或后台分析，重点是“看清楚”，不是“落对象”
- `insight-harvest` 是唯一默认允许新建 `InsightProposal` 的 profile
- `tidy-refactor` 不负责发现新问题，它负责重构已有 insight 池并更新 canonical knowledge

这意味着：

- “发现”与“治理”分离
- “回答”与“落盘”分离
- “可以改 canonical” 必须被严格限制在 `tidy-refactor`

---

## 11. Web 与 Dashboard

### 11.1 Graph 是产品亮点，而不是 Quartz 补丁

Graph 在 v5 中不再只是 canonical relationship 的只读可视化，而应升级为 Sediment 的核心产品表面之一。

但这里存在两种完全不同的图语义：

- 门户图：强调“隐性知识正在形成”的感觉
- 管理图：强调“哪些知识值得提升、合并、拒绝”

因此 v5 建议：

- 保留 `/quartz/` 作为 canonical knowledge 的静态关系图
- 把 `/portal/graph-view` 升级为 Sediment 自己的动态 `Insights Graph`
- 把首页中的“最近更新”替换为 Graph hero，使门户首屏直接呈现知识气候图
- 不新增 `/admin/insights` 一级页，而是把 Insights 能力重构吸收到现有后台 IA

后台吸收方式建议是：

- `/admin/overview`
  - 吸收趋势、Top emerging clusters、canonical stress points
- `/admin/kb`
  - 吸收 insight review、治理图、proposal 操作
- `/admin/files`
  - 继续承担 promote / merge 后的目标文档编辑

### 11.2 一套图模型，两种渲染 profile

门户图和管理图不应各自维护一套独立数据语义，而应共用统一图模型，再由前端以不同 profile 渲染。

v5 的进一步决定是：两者共用同一 3D 图引擎，但采用不同 profile：

- `portal-story`
  - 自动镜头、发光、粒子、路径脉冲、形成动画
- `admin-governance`
  - 低动效、弱自动镜头、保留筛选、详情和审阅动作

统一图模型建议至少包含这些节点：

- `cluster_anchor`
  - 表示相对稳定的知识簇 / 主题盆地
- `query_cluster`
  - 表示正在被反复询问的一类问题
- `insight_proposal`
  - 表示已经物化的隐性知识候选
- `canonical_entry`
  - 表示正式知识
- `index_segment`
  - 表示正式索引入口

统一图模型建议至少包含这些边：

- `weak_affinity`
  - 弱关联、灰线、可由共现或白盒相近性产生
- `ask_reinforcement`
  - ask 过程中被不断强化的连接
- `supports`
  - formal entry 支撑某个 insight
- `routes_to`
  - 某个 insight 可能进入的 canonical target 或 index segment
- `belongs_to_cluster`
  - 节点归属于哪个 cluster anchor

同一套图模型在门户和后台的表达完全不同：

- 门户图偏“知识气候图 / 知识磁场”
- 后台图偏“证据图 / 治理图”

### 11.3 Dashboard 需要看什么

建议至少包含：

- 被问最多的知识主题
- `direct / synthesized / gap` 的比例变化
- 高频 latent candidate
- 最近进入 tidy 提升队列的 insight
- 证据正在趋稳但尚未进入 canonical 的知识簇

此外，后台总览还应新增：

- `canonical stress points`
  - 哪些 canonical entry 周围持续出现 synthesized ask，说明现有条目或索引需要重构
- `cluster coverage`
  - 当前正式 KB 中有多少 entry 已被纳入稳定 cluster / segment

### 11.4 图模型

图的布局目标不只是“把节点摆开”，而是要让人看到：

- 哪些知识天然聚在一起
- 哪些连接正在变强
- 哪些新的知识团簇正在隐约成形

因此 v5 明确引入：

- `知识簇 / cluster anchor`

这不是目录 taxonomy，也不是强制文件夹分类；它是高维知识空间在可视化层和索引层上的稳定投影。

具体建议：

- canonical cluster 优先落到 `indexes/index.*.md`
- latent cluster 先停留在 Signals / Insights 层
- `tidy` 负责把长期稳定的 cluster 提升为 segment index

这意味着：

- 正式条目仍然可以平铺存放
- 但 KB 不能长期停留在“只有大量 entry、没有可感知 cluster / segment”的状态
- 当 formal entry 规模增长到中大型时，`tidy` 必须对“缺失稳定 cluster / segment”视为治理问题

### 11.5 视觉状态

建议把“形成中的知识”状态可视化为不同层次：

- 灰色：刚出现
- 蓝色：重复被问
- 橙色：证据趋稳，建议 tidy
- 绿色：已被吸收进 canonical knowledge

门户图在此基础上还应额外表达三种动态感觉：

- 弱关联灰线：表示“这些知识隐约互相牵引，但还没有形成稳定结论”
- 强化通路：当 ask 持续把几个节点一起拉进 evidence pack 时，连接应以脉冲、辉光或流动动效增强
- 成形中的节点：当 latent cluster 趋于稳定但尚未 canonicalize 时，应以半透明、呼吸感、局部聚光等方式表现“正在显现”

这部分是 Sediment 的亮点，不应刻意压平为静态管理图。

### 11.6 聚类能力必须进入 tidy 主职责

现实中的 KB 不应只有条目和散链，还必须逐渐形成可感知的主题盆地。

因此 v5 建议把“聚类质量”上升为 tidy 的正式职责：

- 识别图中高密度知识盆地
- 识别长期缺少 segment index 的 entry 群
- 发现“实际已形成 cluster，但 root / segment index 仍然空骨架”的情况
- 为成熟 cluster 生成或重构 `index.root.md` 与 `indexes/index.*.md`
- 把 cluster coverage 作为健康度的一部分

以 `/Users/hys/dev/kb` 这类实例为例：

- formal entries 已经很多
- `index.root.md` 仍接近空骨架
- 这意味着 KB 有条目，但没有形成足够强的入口网络和 cluster surface

这类情况在 v5 中不应再被视为“可有可无的整理问题”，而应视为需要 tidy 介入的结构性缺陷。

### 11.7 v1 Graph Payload

门户图与后台图应共用同一套最小 graph payload，而不是各自发明一套 schema。

v1 建议的最小返回结构：

```json
{
  "graph_version": "v1",
  "graph_kind": "insights",
  "kb_language": "zh",
  "generated_at": "2026-04-19T12:00:00Z",
  "stats": {
    "node_count": 0,
    "edge_count": 0,
    "cluster_count": 0,
    "cluster_coverage": 0.0
  },
  "nodes": [
    {
      "id": "cluster:onboarding",
      "label": "Onboarding",
      "node_type": "cluster_anchor",
      "state": "stable",
      "weight": 0.82,
      "cluster_id": null,
      "url": null
    }
  ],
  "edges": [
    {
      "id": "edge:1",
      "source": "query:...",
      "target": "cluster:onboarding",
      "edge_type": "ask_reinforcement",
      "strength": 0.74,
      "state": "active"
    }
  ]
}
```

其中字段含义建议固定为：

- `graph_version`
  - payload 版本，允许后续平滑演进
- `graph_kind`
  - v1 固定为 `insights`
- `kb_language`
  - 当前 KB 的默认语言
- `generated_at`
  - 本次图数据生成时间
- `stats`
  - 供 overview / graph header 直接使用的摘要
- `nodes`
  - 同时承载 cluster、query、insight、canonical、index segment
- `edges`
  - 表示节点之间的关系、强化和路由

v1 的最小 node 字段建议是：

- `id`
- `label`
- `node_type`
- `state`
- `weight`
- `cluster_id`
- `url`

v1 的最小 edge 字段建议是：

- `id`
- `source`
- `target`
- `edge_type`
- `strength`
- `state`

为了兼容现有 `GET /api/portal/graph` 的简单 `nodes / edges` 消费方式，v1 建议：

- 继续保留顶层 `nodes` 与 `edges`
- 以新增字段方式扩展，而不是打破旧 shape
- `/api/portal/graph` 返回门户可见字段
- 新增 `GET /api/admin/graph`，复用同一 schema，但允许返回更多治理相关字段

这样可以在不把门户图和后台图彻底拆成两套接口的前提下，保留权限边界和演进空间。

---

## 12. 对既有功能的影响与矛盾

### 12.1 `/portal/graph-view` 不再只是 Quartz 兼容入口

当前设计里，`/portal/graph-view` 只是一个重定向到 `/quartz/` 的兼容入口。

v5 明确改变这一点：

- `/portal/graph-view` 成为 Sediment 自己的动态 `Insights Graph`
- `/quartz/` 继续作为 canonical knowledge 的静态关系图

这是一个明确的大原则变更。

解决方案：

- 保留 `/quartz/` 完整语义，不影响现有 Quartz 托管
- 取消 `/portal/graph-view -> /quartz/` 的默认重定向
- 当动态 graph 运行不可用时，`/portal/graph-view` 显示自己的 fallback，而不是退回 Quartz 站点语义

### 12.2 `/api/portal/graph` 当前 payload 过薄

当前 `graph_payload()` 只把 inventory 中的 entry / index 节点与 wikilink 边直接吐给前端，这只够画静态关系图，不足以表达：

- cluster
- ask reinforcement
- insight proposal
- canonical stress
- latent formation

解决方案：

- 升级 `GET /api/portal/graph` 为版本化 graph payload
- 新增 `GET /api/admin/graph`
- 保持 `nodes / edges` 顶层字段不变，以兼容旧消费者
- 把 cluster、state、strength、stats 等作为新增字段引入

这是接口能力扩展，不一定要破坏已有 consumer。

### 12.3 后台 IA 已拥挤，不能只增不减

当前 `/admin/overview`、`/admin/kb`、`/admin/files` 已经各自有较明确职责。如果再新增 `/admin/insights` 一级页，后台导航会继续膨胀。

v5 的解决方案是：

- 不新增一级页
- 直接重构现有 `/admin/overview` 与 `/admin/kb`

具体地：

- `/admin/overview`
  - 增加 emerging clusters、cluster coverage、canonical stress points
- `/admin/kb`
  - 从“导入 + tidy + explore 的动作工作台”升级为“知识运营台”
  - 内部再拆子工作区：
    - `Operations`
    - `Insights Review`
    - `Graph`
    - `Live`
- `/admin/files`
  - 继续承接 promote / merge 之后的目标文档编辑

这也是一个大原则变更：

- `/admin/kb` 不再只是动作面板，而是知识运营中枢

### 12.4 `retrieval-and-indexing` 反对目录分类，但不反对 cluster

当前设计明确反对“用目录层级表达知识关系”。

v5 与这一点并不冲突，因为：

- `cluster_anchor` 不是目录 taxonomy
- `index segment` 也不是文件夹分类
- 它们是高维知识空间在检索层与可视化层的稳定投影

所以这里没有原则冲突，但需要在 current docs 中补一句：

- “cluster / segment 是检索入口与图可视化单元，不等于目录分类”

### 12.5 `health` 现在看不到 cluster 缺陷

当前 health 主要关注：

- dangling link
- orphan entry
- placeholder promotion
- canonical gap
- provenance contamination

但它还无法识别：

- root index 空骨架
- segment 缺失
- cluster coverage 过低
- index 与真实 cluster 漂移

解决方案：

- 扩展 issue queue 类型
- 把 cluster quality 纳入 `validation-and-health`
- 允许后台对 cluster 类问题一键发起 `tidy(indexes)` 或 `tidy(full)`

这里没有推翻原有原则，只是把“检索可达性”从链接层扩展到 cluster 层。

### 12.6 UI locale 与 KB 默认语言是两套概念

当前前台设计里，页面 locale 与 `Accept-Language` 相关；而 v5 新增了 KB 层的 `default_language`。

这两者容易混淆，但它们语义不同：

- UI locale 决定页面文案显示语言
- KB default language 决定 explore 的检索、聚类和 synthesis 主语言

解决方案：

- current docs 里应显式区分 `active_locale` 与 `kb.default_language`
- 页面可以是英文 UI，但对中文 KB 做中文检索与聚类
- 页面也可以是中文 UI，但对英文 KB 做英文检索与聚类

这不是原则冲突，而是需要补清边界。

### 12.7 Quartz 继续保留，但不再承担“形成中的知识”表达

当前平台设计已经明确：

- Quartz 不是主产品壳
- Quartz 更适合 canonical knowledge 的静态浏览

v5 保持这一判断不变。

变化只是：

- “形成中的知识”不再试图塞进 Quartz
- 这部分回到 Sediment 主壳，用动态 graph 表达

因此：

- Quartz build/status 仍留在 `/admin/system`
- `/quartz/` 仍服务静态知识浏览
- Sediment 主壳负责知识形成、review、signals 和治理图

这是一种职责再分配，而不是对 Quartz 价值的否定。

---

## 13. 仍待继续确认的问题

本草案已经收敛的结论：

- 系统需要 `Insights` 层
- `explore` 需要 feedback 机制
- `tidy` 需要从“整理”升级为“重构”
- `knowledge_ask` 默认只读 canonical knowledge
- `Signals`、`Insights`、`Canonical` 需要分层
- MCP 与本地 Skill 需要统一 contract，而不是各造一套语义

仍待继续拍板的问题：

1. `Insights` 是否总是阈值后再物化，还是允许某些高置信 synthesized answer 立即物化
2. `Insights` 目录是否放在 `knowledge-base/` 内，还是作为工作区并列目录
3. `ExploreEnvelope / InsightProposal` 的 v1 极简字段 contract 是否还需要继续裁剪
4. `Signals` 的聚类算法与 query normalization 规则
5. `demand_score / maturity_score` 的初始打分方式，以及它们是否需要在 v2 对外显式暴露
6. committer 是否需要显式“接受为 proposed insight”步骤，还是系统自动落 proposal 后再审阅
7. 门户图在大 KB 下的性能分层、LOD 与首屏加载策略

---

## 14. 本文的定位

本文不是当前已落地契约，而是下一代 Sediment 的架构草案。

如果后续决定正式推进，应至少拆回当前设计文档中的这些模块：

- `current/workflows.md`
- `current/entry-model.md`
- `current/enterprise-governance.md`
- `current/platform-architecture.md`
- `current/interfaces-and-review-flow.md`
- `current/web-surfaces.md`
- `current/validation-and-health.md`

在这些文档完成拆分之前，本草案用于：

- 保留这轮讨论中的关键结论
- 避免上下文压缩造成遗忘
- 为后续细化 `Insights` 相关契约提供统一起点
