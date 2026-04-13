# 隐性知识提取系统设计文档（v4.5）

> 状态：历史快照
> 当前入口：见 [design/README.md](../README.md)
> 后续拆分：v4.5 中关于索引网络与检索组织的内容，已拆入 `design/current/retrieval-and-indexing.md`。

---

## 1. 设计目标

v4.5 解决的核心问题：

- 单一 `index.md` 在规模变大后会成为上下文瓶颈
- 完全无导航的自由检索在大库下容易出现路径抖动
- 需要在不压制 LLM 上限的前提下，提升检索稳定性

v4.5 的目标不是把检索“阉割”为固定流程，而是：

1. 提供稳定的索引入口
2. 保留 LLM 自主探索能力（如 grep / 跳读）
3. 通过 tidy 的结构重构维持索引可扩展性

---

## 2. 不变原则（继承 v4）

v4.5 继续坚持 v4 的核心原则：

- **白盒优先**：知识库仍是文件系统中的 Markdown
- **provenance 与图谱分离**：来源仍只作为元数据，不默认成为知识节点
- **中结构优先**：`concept / lesson / placeholder` 三类条目不变
- **人工审核友好**：人类与 Agent 仍围绕同一份文件协作

v4.5 是检索与组织机制升级，不是知识模型推翻。

---

## 3. 目录与索引模型

### 3.1 概念文件继续平铺

`concept` 条目继续平铺在单一目录中，不按子目录强制分类。

原因：

- 路径稳定，减少迁移与重命名成本
- 降低人工维护复杂度
- 避免“目录分类”与“概念关系”混用

### 3.2 引入多段索引（index network）

v4.5 使用索引网络替代单一大索引：

- `index.root.md`：全局入口与分区导航
- `index.<segment>.md`：子索引，面向某一主题簇或问题簇

子索引直接链接到对应 `concept` / `lesson` 条目，不复制正文定义。

### 3.3 子索引是“可重构单元”

子索引的划分不是静态 taxonomy，而是可由 tidy 在长期运行中调整：

- 拆分过大的子索引
- 合并过小且高度重叠的子索引
- 修复错链、孤岛与过时入口

---

## 4. 子索引重构硬规则

v4.5 增加强制重构触发条件。任一条件满足即进入 tidy 重构队列：

- **条目数阈值**：`entry_count > INDEX_MAX_ENTRIES`
- **估算 token 阈值**：`estimated_tokens > INDEX_MAX_TOKENS`

建议默认值（可配置）：

- `INDEX_MAX_ENTRIES = 120`
- `INDEX_MAX_TOKENS = 8000`

### 4.1 重构动作

当触发重构时，tidy 允许执行：

1. 拆分：按主题或问题入口把一个子索引拆成多个
2. 合并：把低密度、强重叠子索引合并
3. 重连：修复 index -> entry 断链
4. 刷新：清理已废弃入口与低价值重复入口

### 4.2 重构原则

- 以“检索入口可达性”优先，而非“学术分类正确性”
- 不改动事实内容，仅调整导航结构
- 所有重构可审计（保留变更说明）

---

## 5. ingest / tidy / explore 职责更新

### 5.1 Ingest（继续轻量）

ingest 继续聚焦“首次提炼”，不承担全局索引治理：

- 产出结构合法的 `concept / lesson / placeholder`
- 写入来源元数据
- 可做最小链接补充

ingest 不负责：

- 全局索引重分区
- 大规模入口重写
- 历史子索引重构

### 5.2 Tidy（新增索引治理）

tidy 新增职责：

- 维护 `index.root.md` 与子索引集合
- 执行阈值触发的索引重构
- 保障索引覆盖率、连通性与无坏链

### 5.3 Explore（index-first + 自主探索）

explore 默认采用“索引优先”路径：

1. 从 `index.root.md` 进入候选子索引
2. 命中候选条目后再进行细读
3. 允许并鼓励 LLM 使用 grep/全文搜索进行补充探索

说明：

- 这不是对检索上限的硬限制
- index 是默认起点，不是唯一通路

---

## 6. 索引文件建议结构

### 6.1 `index.root.md`

建议包含：

- 分区清单（链接到子索引）
- 每个分区的一句话范围定义
- 最近重构时间

### 6.2 `index.<segment>.md`

建议 frontmatter：

```yaml
kind: index
segment: <name>
last_tidied_at: YYYY-MM-DD
entry_count: <int>
estimated_tokens: <int>
```

正文建议：

- 本段适用问题类型
- 概念入口列表（指向 concept）
- 经验入口列表（指向 lesson）
- 相关子索引跳转（可选）

---

## 7. 关于 cards 的取舍

v4.5 不引入独立 `cards/` 目录。

理由：

- `concept` 条目本身已具备 card 属性
- 避免“概念正文”与“卡片摘要”双写导致漂移
- 降低系统复杂度，先把索引网络稳定下来

如未来确有需要，可引入“card 视图生成”能力，而不是新建并长期维护第二套实体文件。

---

## 8. 健康巡检（health）新增检查项

health check 建议增加：

- 子索引阈值告警（条目数 / token）
- index -> entry 坏链检查
- 未被任何索引覆盖的高价值条目检测
- 过度重复入口检测（同义入口过多）

这些检查项用于给 tidy 提供稳定工作队列。

---

## 9. 迁移策略（从 v4 到 v4.5）

建议分三步推进：

1. **引入结构不改行为**
   - 增加 `index.root.md` 与初始子索引
2. **接入 tidy 重构**
   - 开启阈值检测与自动重构建议
3. **更新 explore 路由**
   - 默认先查 index，再自主扩展检索

迁移期间保持：

- 现有条目 schema 不变
- `knowledge_ask` 对外返回结构不变
- provenance 规则不变

---

## 10. 配置建议（初始）

```yaml
index:
  max_entries: 120
  max_tokens: 8000
  root_file: index.root.md
  segment_glob: index.*.md

explore:
  strategy: index-first
  allow_free_search: true

ingest:
  lightweight: true
```

以上默认值用于启动阶段，后续应通过健康报告与真实查询日志迭代。
