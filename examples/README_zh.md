# 官方样例工作区

官方 `examples/` 不只是一个能搜出结果的示例目录，它的目标是让新用户尽量少准备就能把 Sediment 的主路径体验一遍。

当前样例已经包含：

- 带分段 index 的 canonical knowledge base
- 会在 health / graph / tidy 里出现的 placeholder 缺口
- 能点亮 portal universe 和 admin insights 的 insight proposal
- 用来演示文本提交和文件上传的 `demo-materials/`
- 一个只写本地 `.sediment_state/` 的运行态播种脚本 `scripts/seed_runtime_demo.py`

## 快速开始

```bash
cd examples
sediment init
uv run --project .. python scripts/seed_runtime_demo.py --workspace .
sediment server run
```

这个播种脚本是幂等的，重复执行不会无限堆重复 cluster / inbox item，也不会改动仓库里 checked-in 的 Markdown 知识文件。

## 建议体验路径

- 打开 `/portal` 和 `/portal/graph-view`，看首页热点、insight proposal 和完整知识宇宙。
- 打开 `/admin`，用启动时打印的一次性 token 登录，然后依次看 `Overview`、`Knowledge Base`、`Files`、`Inbox`。
- 把整个 `demo-materials/ingest-batch/` 文件夹上传，体验 staged document ingestion。
- 把 `demo-materials/text-feedback/图谱体验建议.md` 的内容粘贴进文本提交表单。
- 用 `demo-materials/explore-queries.md` 里的问题去试 CLI `sediment kb explore` 或 admin Explore 面板。
