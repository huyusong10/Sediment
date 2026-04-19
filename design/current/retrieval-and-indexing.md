# 当前设计：检索与索引

Sediment 当前采用“索引优先，但允许自由探索”的检索组织方式。

## 1. 索引文件布局

知识库中的索引分两层：

- `index.root.md`：全局入口
- `indexes/index.*.md`：分段索引

其中：

- root index 负责把查询引导到合适的主题段
- segment index 负责把查询引导到具体 `concept` / `lesson`
- 索引是导航层，不复制正式条目正文
- 默认脚手架只创建 `index.root.md`
- 每个 KB 通过 `index.root.md` frontmatter 声明 `default_language`
- segment index 是按需扩展的导航层，不应作为初始化占位默认生成

## 2. Index Contract

分段索引建议使用以下 frontmatter：

```yaml
kind: index
segment: <name>
default_language: <en|zh>   # 仅 root index 必填；segment 可省略并继承 root
last_tidied_at: YYYY-MM-DD
entry_count: <int>
estimated_tokens: <int>
```

当前设计中的约束：

- `index.root.md` 应存在
- `index.root.md` 应声明 KB 的 `default_language`
- segment index 如存在，应位于 `indexes/`
- index 可以链接正式条目，也可以链接其他 index
- index 不应把 placeholder 当作正式入口

## 3. 检索路径

默认路径是：

1. 从 `index.root.md` 选择候选分段
2. 进入 `indexes/` 中的候选索引
3. 命中相关 `concept` / `lesson`
4. 必要时再跟随 `Related` 或全文搜索补充上下文

这意味着 index 是默认起点，但不是唯一通路。真正的目标是提高入口稳定性，而不是限制 LLM 的上限。

补充约束：

- `explore` 需要先把 query 归一化到 KB 默认语言，再进入 index-first 路由
- query signal / cluster 的主语言与索引网络保持一致，避免同一知识被多语言切碎

## 4. 为什么不用目录分类当主导航

正式条目仍然适合平铺存放，而不是强制按目录 taxonomy 归类。

原因：

- 路径更稳定，重命名成本更低
- 目录分类和知识关系是两回事
- 索引文件更适合承载“问题入口”，而不是让目录去表达领域语义

## 5. 索引重构触发条件

当前默认阈值为：

- `max_entries = 120`
- `max_tokens = 8000`

当某个索引超过任一阈值时，应进入 tidy 的重构队列。

典型动作包括：

- 拆分过大的索引
- 合并低密度且高度重叠的索引
- 修复错误链接
- 把未被任何索引覆盖的正式条目纳入入口网络

## 6. 索引健康的关键判断

一组好的索引应满足：

- root index 存在
- root index 不应长期停留在空骨架状态
- 正式条目能被至少一个索引覆盖
- 索引不指向缺失目标或 placeholder
- 分段规模不过载
- 入口划分服务于检索可达性，而不是形式上的分类整齐

新增健康信号：

- `root_index_skeleton`
- `missing_segment_index`
- `low_cluster_coverage`
- `index_cluster_drift`

这些问题不等于目录树不整齐，而是说明“现有 KB 无法形成稳定的入口聚类与 graph surface”。

补充说明：

- graph surface 默认表现的是“近期或仍具能量的知识形成局部”，不是全量知识库存
- 因此 cluster quality 不只影响检索命中，也直接影响门户知识气候图与后台治理图的可读性

## 7. 当前不引入 cards

当前设计不单独维护 `cards/` 目录。

理由：

- `concept` 条目本身已经承担了卡片角色
- 摘要层和正文层双写，容易产生漂移
- 现阶段更值得优先稳定的是索引网络，而不是增加第二套知识实体

## 8. Benchmark / Fast Path 边界

Explore 的快速路径仍然必须建立在正式 KB 上：

- 默认只允许读取 `knowledge-base/` 中的 formal entry、placeholder 和 index
- 对复合标题、阶段名和专项名，ingest / tidy 应尽量收敛出 canonical bare-term entry 或 alias，避免“问 bare term 只能撞到长标题碎片”
- 对配置、路由表、协议定义、拓扑、指标 schema 这类稳定公共表面，应把关键事实提升为 formal entry，并保留可查询的 artifact alias；不能只把文件名留在 provenance
- 对 `流程`、`步骤`、`阶段`、`内容是什么`、`触发条件` 这类问题，快速路径应优先读取 `Scope` / procedure evidence，而不是只复述 summary 里的泛化定义
- 对 `为什么`、`是否`、`能否完全避免` 这类因果 / 判断问题，快速路径不能只停在 direct entry 的定义句；应继续吸收 `Related` / 邻居中的因果、限制条件和反例证据，把 yes/no 结论与支撑原因一起返回
- 对带有前置证据子句的问题，目标解析必须优先抽取尾部真正被询问的主体，而不是把 `根据/综合/…模板/…定义` 这类上下文子句误当成主目标；例如 `综合 A 和 B，如何判断 X 的质量` 应先命中 `X`
- 多实体直达只应用于问题真的同时询问多个主体的场景；如果 `和/与` 只出现在证据来源子句里，快速路径不应把这些上下文条目一起抬成主答案
- 问句路由不能把中文题面写死成唯一入口；至少要允许 alias 与英文同义问法复用同一套 `Scope` / summary / related 选择逻辑
- 内置 skill 包本身必须保持语言中立；locale 相关的问句词表、包装词和结构化表面同义词应由集中式本地化规则提供，而不是直接写死在 `src/sediment/skills/` 中
- 目标短语规范化应忽略 `完整`、`当前`、`默认`、`overall` 这类低信息修饰词，让 `谐振腔的完整生命周期` 仍能稳定命中 `谐振腔生命周期` 这类 canonical entry
- 目标解析还必须能把 `管理谐振腔的完整生命周期`、`驿站节点`、`隐身衣技术`、`嗡鸣度数据质量` 这类 wrapper surface 回投到更适合问答的 canonical target；否则 exact string hit 会把包装词错误抬成主答案
- 问句里的 canonical term 必须被当成显式 target，而不是让更短的子串碎片抢占命中；例如 `调音师` 不应被 `调音` 这类派生碎片覆盖
- 快速路径应优先命中更具体、更可问答的 formal entry；结构碎片和泛化标题不应压过真正的 canonical entry
- 如果问题显式要求 `阶段`、`部署策略`、`触发条件`、`质量判断` 这类结构化事实，快速路径应优先吸收对应的 canonical `Scope` 证据与被回灌的 support facts，而不是重新把 `指标`、`模板`、`系统` 这类 generic wrapper 拉回答案中心
- 对 `范围/区间`、`部署策略`、`故障类型`、`质量判断` 这类结构化问题，snippet 选择必须优先保留阈值、阶段、部署位置、质量信号、故障枚举等高信号句子，而不是让 generic definition 或图邻居噪声抢占答案首屏
- supporting candidate 的补充应优先沿 formal entry 的显式图关系展开，包括出链、回链和一跳邻接的 canonical 条目；条件、因果和诊断增强必须仍然来自白盒 KB 图，而不是来自题面特判
- 目标短语匹配应按规范化后的完整表面排序，而不是只按最短公共子串；例如 `哈基米系统的设计哲学` 应优先命中 `哈基米系统设计哲学`，`隐身衣技术` 应优先命中 `隐身衣` 而不是 `技术`
- 对 `技术`、`系统`、`指标`、`报告` 这类泛化碎片标题，检索排序应施加低信号惩罚；它们可以保留为审计痕迹，但不应在公共问答接口里压过更具体的 canonical entry
- 对 `路由表`、`报文定义`、`监测点配置` 这类 artifact wrapper，如果 KB 中已经存在更贴近用户问题的 canonical subject，排序必须优先 canonical subject，并把 wrapper 仅当作 alias / 入口线索
- 对 `故障类型`、`消息类型`、`路由策略`、`监测点` 这类 structured surface，排序不能因为候选标题更长就偏向包装词更多的条目；`谐振腔故障类型` 应压过 `管理谐振腔的完整生命周期故障类型` 这类残留 wrapper
- `summary` / snippet 抽取必须保留点号承载的真实事实，例如 `720.0Hz`、`v3.2.1`、`deployment_topology.json`；不能因为句子切分把这些 dotted token 打碎，进而让快速路径输出残缺答案
- 原始 benchmark/material、上传原文或其它工作区文件，默认不能作为问答直接证据
- 如果运行环境没有可用的外部 Agent，benchmark 只能退化到显式的白盒 KB 构建流程，继续产出 Markdown 条目与索引；不能改成隐藏检索旁路
- 如果运行环境禁止本地端口绑定，benchmark 可以退化到进程内调用同一个 `answer_question()` 入口，但输入仍然必须是隔离目录中的 KB 与 skill，而不是旁路读取原始材料

这样做的目的是把 benchmark 分数继续约束在“KB 本体是否更好”上，而不是约束在某个临时回退通道上。
