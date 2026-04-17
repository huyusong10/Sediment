# 当前设计：实施路线图

这份路线图围绕一个明确目标展开：

- 门户负责收件
- 知识库管理负责执行 ingest / tidy
- 版本管理负责 Git 落盘、回退与推送

重构优先级以“简单、健壮、可回退”为最高原则，而不是把内部审批流做得越来越重。

## 1. 实施原则

- 先把写路径与 Git 版本层做对，再补体验细节
- 先保证多人协作下不会互相覆盖，再追求更复杂自动化
- 先稳定 `提交收件箱 -> 知识库管理 -> 版本管理` 主链路
- 保持现有读接口稳定，不破坏 `knowledge_list`、`knowledge_read`、`knowledge_ask`

## 2. 阶段 0：配置与仓库基础

目标：

- 给实例引入可管理的 Git 基础设施

交付：

- `git` 配置段
- `sediment init` 写默认 `git` 配置
- Sediment 管理块 `.gitignore`
- tracked path 约束

完成标准：

- 新实例默认具备 Git 配置
- `.sediment_state/` 与 `config/sediment/config.yaml` 默认被忽略
- tracked path 可被版本管理页安全识别

## 3. 阶段 1：提交收件箱

目标：

- 让所有用户提交先进入收件箱，而不是进入 review 队列或直接写知识库

交付：

- `inbox_items` 表
- 门户文本意见提交
- 门户文档上传
- 文本意见 `resolve / reopen`
- 文档 `staged / ready / removed`

完成标准：

- 文本意见进入 `open`
- 文档进入 `staged`
- committer 可在后台完成基本分拣
- 门户提交不再返回自动分析结果

## 4. 阶段 2：知识库管理执行链

目标：

- 把 ingest / tidy 固定为知识库管理页面中的唯一执行入口

交付：

- `ingest_batches` 表
- 从 `ready` 创建 ingest batch
- `/admin/kb?ingest_batch=<id>&autostart=1`
- ingest / tidy job 托管执行
- 任务结果面板

完成标准：

- 收件箱只负责分拣与跳转
- ingest / tidy 由知识库管理统一发起
- job 成功后界面能展示摘要、受影响条目和 commit SHA

## 5. 阶段 3：Git 自动提交与回退

目标：

- 把 ingest / tidy 结果正式落成 Git 历史，并允许安全回退

交付：

- ingest 自动 commit
- tidy 自动 commit
- `commit_sha` 回写到 job / batch / inbox item
- `git revert` 回退接口与按钮
- 版本管理提交历史

完成标准：

- ingest / tidy 成功后必有 Git commit
- 回退动作生成新的 revert commit
- 原任务记录能追溯到 `commit_sha` 与 `revert_commit_sha`

## 6. 阶段 4：文件管理与手工提交分离

目标：

- 明确“保存工作区”和“提交版本”是两个动作

交付：

- 文件管理保存仅写工作区
- 版本管理页显示 tracked changes
- 手工 commit 表单
- 手工 push

完成标准：

- 手工编辑不会自动写 Git commit
- committer 必须在版本管理页填写理由才能提交
- push 只在 upstream 已配置时可用

## 7. 阶段 5：并发保护与失败恢复

目标：

- 在多 committer 场景下保证流程简单但不互相覆盖

交付：

- 收件箱条目级乐观并发
- 仓库级 repo lock
- ingest/tidy 失败时恢复 `ready`
- revert 失败时 abort

完成标准：

- 同一条目并发修改返回 `409`
- 同一时刻只有一个仓库级写动作在运行
- 失败不会留下半应用工作区

## 8. 阶段 6：文档、测试与清理

目标：

- 让设计文档、测试和代码对齐到同一产品心智

交付：

- 重写提交 / 任务 / Git 契约文档
- API / E2E / 浏览器用例更新
- 清理 review-first 遗留术语和死代码

完成标准：

- 文档不再把 `/admin/reviews` 视为主流程
- 测试主线覆盖收件箱、ingest、版本管理、回退和并发
- 新接手开发者能按文档直接实现调用方

## 9. 验收场景

核心契约用例：

- 文本意见提交后进入 `open`，可 `resolve`，可 `reopen`
- 文档上传后进入 `staged`，可下载、移除、移入 `ready`
- 从 `ready` 创建 ingest batch 后跳转到知识库管理并自动执行 ingest
- ingest / tidy 成功后自动创建 Git commit
- 文件管理手工保存后，版本管理页可看到 tracked changes
- 手工 commit 只提交 tracked paths
- Sediment 管理提交可在 UI 中回退
- push 只在 upstream 已配置时可用

关键并发场景：

- 两个 committer 同时处理同一条文本意见，后写者收到 `409`
- 两个 committer 同时把同一文档纳入 batch，只允许一个成功
- 仓库级写动作互斥
- tracked paths 有未提交修改时，ingest / tidy 被阻止

## 10. 推荐执行顺序

推荐顺序：

1. 阶段 0
2. 阶段 1
3. 阶段 2
4. 阶段 3
5. 阶段 4
6. 阶段 5
7. 阶段 6

原因：

- 先把 Git 与收件箱这两个底层边界定稳
- 再把 ingest / tidy 和手工提交接上版本层
- 最后再做并发硬化和文档清理
