# Sediment 测试方案

Sediment 是一个隐式知识提取系统，核心流程：**Ingest（粗录入）** → **Tidy（精加工）** → **Explore（问答）**。

本测试方案围绕 Tidy 后的知识库质量设计用例，通过 2 次知识库构建（全量 + 分批），跑完全部测试，取平均分作为最终成绩。

## 评分体系

| 用例 | 内容 | 满分 |
|------|------|------|
| TC-01 | 概念覆盖率：100 个概念逐一提问，基于关键词覆盖率和语义匹配评分 | 40 |
| TC-02 | 问答准确率：100 道测试题，多维度语义评分（LLM + 脚本混合） | 60 |
| **总计** | | **100** |

**通过标准：≥ 90 分**

### TC-01 概念覆盖率（40 分）

- 对 `testcase/judge/概念.json` 中 100 个概念逐一通过 MCP `knowledge_ask` 提问
- 每个概念 0～1 分，满分 100 分 × 0.4 = 40 分
- 评分维度：关键词覆盖率 (40%) + 语义匹配 (30%) + 无矛盾 (30%)
- 支持同义词加分和相关概念引用加分

### TC-02 问答准确率（60 分）

- 对 `testcase/judge/问答.json` 中 100 道题逐一通过 MCP `knowledge_ask` 提问
- 评分采用 **LLM 评分器 + 脚本评分混合**模式
- 评分维度：accuracy（准确性）、completeness（完整性）、keyword_coverage（关键词覆盖）、reasoning（推理深度）
- 按难度加权：
  - easy（15 题）：每题满分 0.3
  - medium（35 题）：每题满分 0.6
  - hard（50 题）：每题满分 0.69

| 难度 | 题数 | 每题满分 | 小计 |
|------|------|----------|------|
| easy | 15 | 0.3 | 4.5 |
| medium | 35 | 0.6 | 21 |
| hard | 50 | 0.69 | 34.5 |

每题得分 = 综合评分 × 该题满分值

综合评分权重：
- easy：accuracy × 0.4 + completeness × 0.3 + keyword_coverage × 0.3
- medium：accuracy × 0.3 + completeness × 0.3 + keyword_coverage × 0.3 + reasoning × 0.1
- hard：accuracy × 0.25 + completeness × 0.25 + keyword_coverage × 0.25 + reasoning × 0.25

## 测试流程

### 第 1 步：项目隔离

将整个项目目录复制到临时位置，确保测试不影响源码：

```bash
TIMESTAMP=$(date +%s)
ISOLATED_DIR="/tmp/sediment-test-${TIMESTAMP}"
cp -a . "${ISOLATED_DIR}"
cd "${ISOLATED_DIR}"
```

或使用自动化脚本 `testcase/scripts/isolated_build.py`（推荐），它会自动创建隔离目录、构建 KB、启动 MCP Server。

**流程约束（必须满足）**：

- ingest / tidy 的提示词必须直接来自项目源码中的 `skills/ingest.md` 与 `skills/tidy.md`
- 禁止测试脚本私自维护一套平行提示词（如 `testcase/prompts/*.md`）
- 知识库只能生成在临时隔离目录内，禁止复制快照到 `testcase/results/`
- `testcase/results/` 只用于保存评分结果、报告和改进记录
- 运行时问答默认只能检索构建后的 KB，不能回退读取 `testcase/material/` 原始材料

### 第 2 步：构建知识库

**全量构建**：将全量文档分成 3 个大批次 ingest（批间不 tidy，避免单次提示过大），最后统一 tidy，并追加一次 final canonical convergence pass。

**分批构建**：每次 ingest 1/5 文档，再 tidy，重复 5 次把所有文档吸收完成；全部完成后再执行一次全局 tidy 和一次 final canonical convergence pass。

**构建质量目标**：

- 优先产出 canonical bare-term entries，使 `什么是X` 能直接命中
- placeholder 应在有足够证据时被提升为 formal entry，而不是长期滞留
- 分批 ingest 必须是增量收敛过程，不能不断制造平行标题和浅层重复条目

### 第 3 步：执行测试

对两个构建出来的知识库分别：

1. 拉起 MCP Server
2. 执行 TC-01（概念覆盖率）
3. 执行 TC-02（问答准确率）

### 第 4 步：评分与报告

两个仓库分别计算总分，取平均值作为最终成绩。

### 一键运行

> **超时设置**：完整流程（全量 + 分批）通常不超过 2 小时，调用 Bash 工具时超时应至少设为 **7200000ms（2 小时）**。单次构建（仅全量或仅分批）通常不超过 1 小时，超时至少 **3600000ms（1 小时）**。

```bash
# 完整流程（全量 + 分批 + 评分）
python testcase/scripts/run_all_scores.py

# 仅全量构建
python testcase/scripts/run_all_scores.py --build-type full

# 仅分批构建
python testcase/scripts/run_all_scores.py --build-type batched

# 仅评分（已有构建结果时）
python testcase/scripts/run_all_scores.py --skip-build
```

## 隔离方式

### 为什么需要隔离

测试流程中的 ingest 和 tidy 阶段会**直接修改** `knowledge-base/` 目录。如果在主分支上直接运行：
- 测试产生的 KB 文件会污染工作目录
- 多次运行会产生累积污染，无法区分新旧数据
- `git status` 会显示大量未跟踪的 KB 变更

### 隔离方式

使用 `testcase/scripts/isolated_build.py` 自动处理：

1. 创建临时隔离目录（`tempfile.mkdtemp`）
2. 只读复制项目（排除 `.git`、`__pycache__`、`results` 等）
3. 初始化 KB 目录结构
4. 在隔离目录内执行所有操作（cwd=隔离目录）
5. MCP Server 也在隔离目录内启动（cwd=隔离目录，PYTHONPATH=隔离目录）
6. 若平均分达到通过线，测试完成后自动清理临时目录
7. 若平均分未达到通过线，保留本轮临时目录以便诊断

### 手动隔离

如需手动隔离（不推荐）：

```bash
TIMESTAMP=$(date +%s)
ISOLATED_DIR="/tmp/sediment-test-${TIMESTAMP}"
cp -a . "${ISOLATED_DIR}"
cd "${ISOLATED_DIR}"
export SEDIMENT_KB_PATH="${ISOLATED_DIR}/knowledge-base"
# 运行测试...
rm -rf "${ISOLATED_DIR}"
```

## 得分计算

两个用例分别给出得分（满分 40+60），主流程仅计算每个知识库的总分，并取两次构建的平均值作为最终分数。

## 预期输出

每次完整运行后，`testcase/results/` 目录应包含：

```
testcase/results/
├── builds/
│   ├── full/
│   │   ├── concept_answers_full.json
│   │   ├── concept_match_full.json
│   │   ├── qa_answers_full.json
│   │   ├── answers_scored_full.json
│   │   ├── kb_diagnostics_full.json
│   │   └── status.json
│   └── batched/
│       ├── concept_answers_batched.json
│       ├── concept_match_batched.json
│       ├── qa_answers_batched.json
│       ├── answers_scored_batched.json
│       ├── kb_diagnostics_batched.json
│       └── status.json
├── reports/
│   ├── preflight.json
│   ├── live_status.json
│   ├── scorecard.json
│   ├── scorecard.md
│   ├── last_run.json
│   ├── run_*.json
│   └── report_*.html
├── history/
│   └── <timestamp>/
│       ├── builds/
│       └── reports/
└── improvements/
    └── improvement_*.md
```

详情中包含低分的概念/题目、标准答案以及回复的答案；`kb_diagnostics_*.json` 还会记录条目数、占位符数、平均条目大小、孤立条目、悬空链接和高引用占位符。

**注意**：

- `results/` 中不应出现 `kb_full/`、`kb_batched/` 等知识库快照目录；KB 只应存在于临时隔离目录。
- 平均分低于 90 时，`scorecard.json` / `last_run.json` 会记录被保留的临时隔离目录路径，供后续诊断。

## 测试用例详情

详见 `testcase/judge/` 目录下的 JSON 文件：
- `概念.json`：100 个概念的定义、类型、关联术语
- `问答.json`：100 道测试题，含难度分级、标准答案、预期关键词
