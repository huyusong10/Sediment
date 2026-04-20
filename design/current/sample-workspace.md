# 当前设计：官方样例工作区

官方样例工作区是仓库内置的 onboarding 合同，不是随意堆几篇示例 Markdown。

## 1. 目标

`examples/` 必须让新用户在最少准备下体验以下能力：

- canonical knowledge 浏览、搜索与条目阅读
- placeholder health / graph / tidy 入口
- segmented index 导航
- insight proposal 浏览与审阅入口
- portal graph / knowledge universe 的热点与 tacit 节点
- 运行态的 query cluster、graph event、inbox item 演示

## 2. 目录契约

官方样例工作区至少包含以下层：

```text
examples/
  knowledge-base/
    entries/
    placeholders/
    insights/
    indexes/
    index.root.md
  demo-materials/
    ingest-batch/
    text-feedback/
    explore-queries.md
  scripts/
    seed_runtime_demo.py
```

## 3. 白盒与运行态边界

- `knowledge-base/` 内的 canonical / placeholder / insight / index 文件必须是 checked-in 白盒真相
- query cluster、graph event、inbox item 这类运行态投影不直接提交到仓库
- 官方样例只能通过本地 seed helper 写入 `.sediment_state/`，不能把隐藏数据库当成 repo 自带真相

## 4. 样例覆盖要求

官方样例至少满足以下覆盖：

| 维度 | 最低要求 | 目的 |
| --- | --- | --- |
| Formal entries | 一组可搜索、可互链的稳定 canonical entries | 支撑基础浏览与搜索 |
| Placeholders | 至少 3 个，并且每个被至少 3 个 formal entry 引用 | 让 health / graph / tidy 能展示 gap |
| Insights | 至少 3 个 checked-in `InsightProposal` | 点亮 portal hotspot 与 admin insights |
| Indexes | 根索引 + 多个 segment index | 支撑文件导航与 index graph |
| Demo materials | 至少一组可上传文档与一个文本反馈样例 | 让 submit / inbox 可直接体验 |
| Runtime seed | 幂等 helper，能生成 clusters / events / inbox 样例 | 让 overview / graph / insights 不再空白 |

## 5. Seed Helper 约束

运行态 seed helper 必须满足：

- 幂等：重复执行不会无限堆重复 cluster / inbox item
- 局部：只写样例 workspace 自己的 `.sediment_state/`
- 非破坏：默认不重置用户已有 canonical Markdown
- 可发现：README 必须给出明确调用方式

## 6. 多语言要求

- 样例知识内容可以体现特定领域语言，但样例契约本身不能假设产品界面只支持某一种 locale
- 如果样例 KB 的主语言不是英文，应在样例 KB 元数据中显式声明 `default_language`
- 辅助说明、脚本参数和目录约定必须保持语言中立，不把 UI 契约硬编码为单语产品
