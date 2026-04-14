# Goal

按照 `benchmarks/TEST_PLAN.md` 在当前 Sediment 仓库上执行完整闭环迭代：在隔离目录里分别完成 `full` 与 `batched` 两次 KB 构建，运行完整评分，并持续基于诊断结果改进，直到 `benchmarks/results/reports/scorecard.json` 中两次构建的平均分达到 90 分以上；如果无法达到，则给出能被审计的、基于真实产物的架构性阻塞证明。整个过程必须把 `design/evolution/tacit_knowledge_system_v3.md` 的白盒知识库精神作为最高设计约束，并与当前实现边界保持一致：Sediment 今天的稳定运行时是建立在同一份 Markdown KB 之上的 Explore / Health，ingest 与 tidy 是构建与治理工作流，不允许靠隐藏检索规则替代 KB 本体。任何提分都必须体现为 KB 结构更好，或是真正通用的运行时 / 构建修复，对未见但结构相似的真实问题同样成立。

# Checks

### Full + batched 闭环完成
- When: 从仓库根目录按当前 benchmark harness 运行完整流程。
- Expect: `benchmarks/results/builds/full/` 与 `benchmarks/results/builds/batched/` 都生成当轮产物，且 `benchmarks/results/reports/scorecard.json` / `last_run.json` 记录 TC-01、TC-02、各自总分和平均分。
- Fail if: 只跑了一个构建类型、关键结果文件缺失，或声称“优化有效”却没有重新执行 full + batched。

### 退出条件有可审计证据
- When: 本轮决定停止迭代。
- Expect: 要么 `scorecard.json` 中平均分达到 90 分以上，要么存在基于当轮报告、诊断文件和被保留隔离 KB 的明确架构性阻塞说明。
- Fail if: 平均分低于 90 就停止，且没有可追溯证据；或把问题笼统归因成“检索不好”“模型不行”而没有结构性证明。

### 提升来源保持白盒且通用
- When: 审查改动文件和构建后的 KB。
- Expect: 提升来自更强的 KB 本体与收敛结构，例如 `entries/`、`placeholders/`、`index.root.md`、`indexes/`、aliases、canonical bare-term entry、显式规则 / 边界 / 前提 / 反例 / 后果、跨文档因果链、链接修复、placeholder promotion、duplicate convergence，或来自已被证明对任意真实问题都成立的通用 bug 修复。
- Fail if: 提升依赖隐藏的 benchmark 特判、题目到条目的隐式映射、只存在于检索代码里的黑盒规则，或无法在可见 KB 结构中落地。

### 低分轮次先诊断再修改
- When: 任一轮平均分低于 90。
- Expect: 在改代码前同时检查 full 与 batched 的 `kb_diagnostics_*`、`concept_match_*`、`answers_scored_*`、`qa_answers_*`、HTML / JSON 报告以及被保留的隔离 KB，并把每个低分项明确归类到 ingest 漏提取、tidy 未收敛、explore 深度不足，或真正的通用检索 / 运行时 bug；随后在 `benchmarks/results/improvements/` 写入 `improvement_<timestamp>.md`。
- Fail if: 还没完成诊断就开始改动，低分项没有精确归因，或改进记录没有说明根因、预期提升、剩余问题，以及为什么这不是 shortcut。

# Constraints

- 以当前仓库中的真实文档为准：`benchmarks/TEST_PLAN.md` 定义评测流程，`design/evolution/tacit_knowledge_system_v3.md` 提供最高设计精神，`design/current/overview.md`、`design/current/workflows.md` 与 `design/current/entry-model.md` 约束今天的系统边界与条目模型。
- 当前 Sediment 的主线不是“把题答对”，而是让同一份白盒 Markdown KB 同时支撑 Explore 与 Health；benchmark 只是 KB 质量的外部信号，不是绕过 KB 设计的许可。
- 唯一合法的提分来源只有两类：一是让知识真正沉淀进可审核的 KB 本体与索引网络，二是修复已经证明对真实用户问题同样成立的通用运行时 / 构建缺陷。
- 禁止按 benchmark 题号、题面原文、低分样例关键词或正则模式做硬编码、隐式特判、宽泛问题特判、细节问题特判。
- 禁止在 `src/sediment/server.py`、`src/sediment/kb.py`、Explore 运行时或相关检索路径中加入 benchmark-oriented 的 `问题 -> 条目` 映射、语义规则表、source-file 映射扩写，或任何只为测试集成立的捷径。
- 禁止为了冲分修改评分脚本、judge 数据、报告脚本或测试流程；如果脚本存在通用 bug，必须在改进记录里说明它为何会影响任意真实运行，而不只是 benchmark。
- 禁止声称“优化有效”却只看局部指标或单次构建；通过线只看 full + batched 的完整闭环平均分。
- 禁止把知识停留在黑盒检索层，而不落到 `entries/`、`placeholders/`、`index.root.md`、`indexes/`、aliases、canonical entry、链接和相关审计产物中。
- 禁止为了覆盖测试而批量制造表面像答案、实则破坏 canonical convergence 的浅层平行标题。
- 禁止复制 KB 快照到 `benchmarks/results/`；该目录只用于保存评分结果、报告、历史和改进记录，真实 KB 只应存在于临时隔离目录。
- 默认优先修改 `src/sediment/skills/ingest/SKILL.md`，重点提升概念提取、规则提取、tacit knowledge 提取、跨文档因果链显式化、canonical bare-term coverage 和 alias 完整性。
- 默认优先修改 `src/sediment/skills/tidy/SKILL.md` 及其辅助脚本，重点提升 placeholder promotion、duplicate convergence、orphan repair、contradiction handling、index / graph repair 和审阅质量。
- 默认优先修改 `src/sediment/skills/explore/SKILL.md` 及其脚本，重点提升探索深度、改写查询角度、沿链接跟进、冲突识别与 gap 诚实表达，但必须保持通用协议，不得加入 benchmark 特判。
- 只有在确认存在真正的通用 bug 时，才允许修改 `src/sediment/kb.py`、`src/sediment/server.py` 或 `benchmarks/scripts/*.py`；并且必须能在不提 benchmark 题目的前提下解释其合理性。
- 每轮固定流程是：先跑 full + batched，记录 TC-01、TC-02、各自总分与平均分；若平均分达到 90 分以上则停止；若低于 90，则必须先做深度诊断，再做少量高杠杆改动并复跑完整流程。
- 深度诊断时必须同时看结构指标和问答失分：formal entry 数量、placeholder 数量、平均条目大小、孤立节点、悬空链接、高引用 placeholder、低分概念、低分问答，以及保留的 isolated directory 中真实生成的 KB。
- 每个低分项都必须归因到以下四层之一：ingest 漏提取、tidy 未收敛、explore 不够深入、通用检索 / 运行时 bug；不允许用“检索不好”这种笼统说法代替分析。
- 只做少量高杠杆修改，优先解决结构性根因，而不是堆很多零碎补丁；优先追求 bare-term 可直达、重要概念脱离 placeholder、平行浅层条目收敛、条目显式写出规则与边界、跨文档因果链进入 KB，以及 batched 构建持续增量收敛。
- 动手前必须能同时回答“是”的四个自检问题：这会让 KB 本体更好吗；这会帮助未见但结构相似的真实问题吗；我能不提 benchmark 题面也解释这次改动吗；把这次改动展示给人类管理员看，它仍然像一个更合理的 Sediment 吗。
- 每轮都必须在 `benchmarks/results/improvements/` 生成 `improvement_<timestamp>.md`，写清修改文件、根因归类、改善的结构性缺陷、预期提升对应的 TC-01 / TC-02 能力、为什么它不是 shortcut，以及仍未解决的问题。
