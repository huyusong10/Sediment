# 当前设计：提交流、接口与版本管理

企业版 Sediment 的写路径不再以独立 review 页面为中心，而是以三段式工作台为中心：

- `提交收件箱`：接收并分拣用户提交
- `知识库管理`：执行 ingest / tidy
- `版本管理`：托管 Git 提交、回退与推送

目标是保持流程简单、可追溯、可回退，同时避免把门户提交、知识提炼、Git 落盘混成一个动作。

## 1. 接口分层

接口分成三类：

- MCP 读接口：给 Agent、IDE 和自动化流程做知识检索
- MCP 写接口：给 Agent 或自动化流程提交材料、发起 ingest / tidy 或查询任务状态
- REST 接口：给 Web 前后台做收件、分拣、执行、版本管理和在线编辑

## 2. MCP 工具规划

### 2.1 保持稳定的读工具

以下工具继续保持稳定：

- `knowledge_list`
- `knowledge_read`
- `knowledge_ask`

### 2.2 提交工具

新增两类提交工具：

- `knowledge_submit_text`
- `knowledge_submit_document`

建议输入：

`knowledge_submit_text`

```json
{
  "title": "热备份切换前先确认接管链路",
  "content": "……纯文字意见或经验……",
  "submitter_name": "Alice"
}
```

`knowledge_submit_document`

```json
{
  "filename": "incident-review.docx",
  "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "content_base64": "...",
  "submitter_name": "Alice"
}
```

行为约束：

- 工具只创建收件箱记录
- 返回稳定主键 `id`
- 为兼容旧调用方，REST 层可同时附带 `item_id = id`
- 不直接写入知识库
- 文本意见不自动分析
- 上传原件不自动抽取文本，不自动运行 ingest
- `knowledge_submit_text` / `knowledge_submit_document` 的 `submitter_name` 必须是非空文本；错误输入不得创建任何收件箱项，也不能回退成匿名提交
- `knowledge_submit_document` 必须在 `content_base64` 与 `files` 之间二选一；不能同时提供，也不能同时省略
- `knowledge_submit_document.files` 中的每一项都必须提供非空 `filename` 与 `content_base64`；任一坏条目都必须拒绝整次提交，不能静默跳过

### 2.3 后续可选治理工具

面向 `committer` 或自动化流程，可增加：

- `knowledge_health_report`
- `knowledge_inbox_list`
- `knowledge_ingest_batch_create`
- `knowledge_job_status`
- `knowledge_tidy_request`
- `knowledge_version_status`

MCP 治理工具写入契约：

- `knowledge_tidy_request` 遇到不支持的 `scope` 必须返回结构化 `error`，且不得创建 tidy job
- `knowledge_tidy_request` 的 `actor_name` 若显式提供，则必须是非空文本；错误输入不得生成匿名审计记录
- `knowledge_tidy_request` 的 `reason` 若显式提供，则必须是非空文本；仅在真正省略时才允许服务端回退到 issue / scope 派生理由
- `knowledge_review_decide` 的 `review_id`、`decision`、`reviewer_name` 必须是非空文本
- `knowledge_review_decide` 遇到不支持的 `decision`、不存在的 review 或已不可决议的 review，必须返回结构化 `error`
- MCP 写工具返回错误时，不得推进 review / job 等已有状态

## 3. REST 接口契约

### 3.1 前台知识库界面

- `GET /api/portal/home`
- `GET /api/portal/search?q=...`
- `GET /api/portal/search/suggest?q=...`
- `GET /api/portal/entries/{name}`
- `GET /api/portal/graph`
- `GET /api/portal/graph?focus=...`
- `POST /api/portal/submissions/text`
- `POST /api/portal/submissions/document`

门户写入契约：

- 文本意见只创建 `text_feedback` 收件箱项
- 上传文件只创建 `uploaded_document` 收件箱项并保存原件
- 成功响应返回 `id`、当前 `status` 与完整 `item`
- 若需要兼容旧前端，可额外返回 `item_id`，但前台新实现必须以 `id` 为唯一读取源
- 不返回 `analysis`
- 不依赖 `submission_type`
- 请求体必须是顶层 JSON object；malformed / non-object body 必须返回 `400`，且不得创建任何收件箱项
- 门户文档上传的 `content_base64` 与 `files` 必须二选一；任一 `files` 坏条目都必须让整次提交返回 `400`

### 3.2 管理后台

- `GET /api/admin/session`
- `POST /api/admin/session`
- `DELETE /api/admin/session`
- `GET /api/admin/users`
- `POST /api/admin/users`
- `GET /api/admin/users/{id}/token`
- `POST /api/admin/users/{id}/disable`
- `GET /api/admin/system/status`
- `GET /api/admin/settings/config`
- `PUT /api/admin/settings/config`
- `POST /api/admin/settings/restart`
- `GET /api/admin/audit`
- `GET /api/admin/health/summary`
- `GET /api/admin/health/issues`
- `GET /api/admin/graph`
- `GET /api/admin/insights`
- `GET /api/admin/insights/{id}`
- `POST /api/admin/insights/{id}/review`
- `GET /api/admin/inbox`
- `POST /api/admin/inbox/text/{id}/resolve`
- `POST /api/admin/inbox/text/{id}/reopen`
- `POST /api/admin/inbox/document/{id}/mark-ready`
- `POST /api/admin/inbox/document/{id}/move-to-staged`
- `POST /api/admin/inbox/document/{id}/remove`
- `GET /api/admin/inbox/document/{id}/download`
- `POST /api/admin/inbox/ingest-batches`
- `POST /api/admin/ingest/document`
- `GET /api/admin/jobs/{id}`
- `POST /api/admin/jobs/{id}/retry`
- `POST /api/admin/jobs/{id}/cancel`
- `POST /api/admin/tidy`
- `GET /api/admin/version/status`
- `POST /api/admin/version/commit`
- `POST /api/admin/version/push`
- `POST /api/admin/version/revert`
- `GET /api/admin/kb/documents`
- `GET /api/admin/files`
- `GET /api/admin/files/suggest?q=...`
- `GET /api/admin/entries/{name}`
- `PUT /api/admin/entries/{name}`
- `GET /api/admin/quartz/status`
- `POST /api/admin/quartz/build`

补充契约：

- `/api/portal/graph` 与 `/api/admin/graph` 共用统一 payload，至少包含 `graph_version`、`graph_kind`、`kb_language`、`stats`、`nodes`、`edges`
- graph payload 必须以事件驱动局部投影为默认语义，并额外提供 `scene_mode`、`focus_seed`、`story_caption`、`ambient_seed`、`playback_events`
- `nodes` / `edges` 顶层 shape 保持稳定，便于图前端独立演进
- node 至少补充 `visual_role`、`energy`、`stability`、`entry_target`、`event_type`、`burst_level`、`formation_stage`、`recentness`
- edge 至少补充 `activation`、`formation_role` 与 `pulse_level`
- `POST /api/admin/insights/{id}/review` 只接受 `observe / promote / merge / reject`
- insight review 不直接改文件；服务端只创建受管 `insight_review` job，由 Agent Runner 在隔离工作区执行并提交
- `insight_review` 的 Git 提交必须只覆盖该次 payload 命中的路径，不能顺手提交整个 `knowledge-base/`
- `knowledge-base/insights/` 中允许同时存在多个待审 proposal 脏文件；review 当前 proposal 时，只忽略 `insights/` 层的既有脏状态，canonical / indexes / placeholders 的脏状态仍然必须阻塞提交

后台写入契约：

- 接受 JSON body 的写接口必须把 malformed / non-object body 明确拒绝为 `400`
- 当请求体无效时，不得推进 inbox / review / git / settings 等状态变更
- `/api/admin/reviews/{id}/approve` 只能接受批准语义；拒绝或取消语义不能借 approve 路由透传
- `/api/admin/ingest/document` 的 direct upload 模式必须复用与门户一致的文档 payload 契约；坏 upload payload 返回 `400`，且不得创建 inbox item / batch / job
- `/api/admin/ingest/document` 的 direct upload 成功后，主返回体必须以 `item` 表示新建的 `uploaded_document`；如保留 `submission` 旧字段，也只能作为兼容别名

兼容行为：

- `/admin/reviews` 保留兼容跳转到 `/admin/inbox`
- `/api/admin/reviews*` 不再是主流程接口

## 4. 收件箱数据模型

主写入语义由 `inbox_items` 承担，不再由 `submissions` 作为产品主模型。

建议字段：

- `id`
- `item_type`：`text_feedback`、`uploaded_document`
- `title`
- `body_text`
- `stored_file_path`
- `original_filename`
- `mime_type`
- `status`
- `submitter_name`
- `submitter_ip`
- `submitter_user_id`
- `notes`
- `ingest_batch_id`
- `job_id`
- `commit_sha`
- `created_at`
- `updated_at`
- `version`

状态契约：

| 项目类型 | 可用状态 |
|------|------|
| `text_feedback` | `open`、`resolved` |
| `uploaded_document` | `staged`、`ready`、`ingesting`、`ingested`、`removed` |

行为约束：

- `resolved` 文本进入历史区，但可恢复成 `open`
- `removed` 与 `ingested` 文档进入历史区
- `removed` 在 v1 不提供恢复

## 5. Ingest Batch 模型

`ingest_batches` 用于把一组 `ready` 文档原子化地绑定到一次 ingest 触发。

建议字段：

- `id`
- `status`
- `item_count`
- `created_by_id`
- `created_by_name`
- `job_id`
- `commit_sha`
- `created_at`
- `updated_at`

状态契约：

- `created`
- `ingesting`
- `ingested`
- `failed`

行为约束：

- 创建 batch 时，所选文档必须一次性从 `ready` 变为 `ingesting`
- 任一条目版本冲突，整个 batch 创建失败
- ingest enqueue 或执行失败时，batch 中的条目统一恢复为 `ready`

## 6. 任务模型

ingest 和 tidy 都是后台任务，而不是同步 HTTP 写入。

建议 `jobs` 字段：

- `id`
- `job_type`：`ingest`、`tidy`、`insight_review`
- `source_submission_id`：兼容字段
- `source_batch_id`
- `target_entry_name`
- `status`
- `runner_host`
- `workspace_path`
- `result_payload`
- `error_message`
- `commit_sha`
- `revert_commit_sha`
- `created_at`
- `started_at`
- `finished_at`

`status` 建议值：

- `queued`
- `running`
- `cancel_requested`
- `succeeded`
- `failed`
- `cancelled`

行为约束：

- ingest / tidy 的 Agent 推理在隔离工作区运行
- 真正写主工作区、校验、commit、revert 时必须持有 repo lock
- 任务成功后必须把 `commit_sha` 回写到 `job`，必要时同步回写 batch 与 inbox item

Insight review 补充约束：

- `observe` / `reject` 只改 `insights/` 层
- `merge` 需要显式 `target_name`
- `promote` 需要新的 canonical 标题，并生成正式条目提交
- 任何 canonical 写入都必须走 job + Git commit，不能前端直写

## 7. Git 与版本管理契约

Git 是正式版本层。

配置项：

```yaml
git:
  enabled: true
  repo_root: "../.."
  tracked_paths:
    - "knowledge-base"
  remote_name: "origin"
  system_author_name: "Sediment System"
  system_author_email: "sediment-system@local"
```

默认行为：

- `sediment init` 写入默认 `git` 配置
- `sediment init` 创建或合并 Sediment 管理块 `.gitignore`
- 默认忽略 `.sediment_state/`
- 默认忽略 `config/sediment/config.yaml`

### 7.1 自动提交

以下动作成功后自动生成 Git commit：

- ingest
- tidy

作者规则：

- 由 UI 中的 committer 手工触发：author 使用该 committer 名字，email 使用 `sediment+<user_id>@local`
- 由系统自动触发：author 使用 `Sediment System <sediment-system@local>`

提交消息规则：

- ingest：`ingest: <batch_title_or_count>`
- tidy：`tidy(<scope>): <reason>`

统一 trailer：

- `Sediment-Operation`
- `Sediment-Actor-Id`
- `Sediment-Actor-Name`
- `Sediment-Job-Id`
- `Sediment-Batch-Id`
- `Sediment-Source-Item-Ids`

### 7.2 手工提交

`文件管理` 页面保存只写工作区，不自动 commit。

手工 commit 由 `版本管理` 页面完成，约束如下：

- 只提交 `git.tracked_paths` 覆盖的文件
- 提交理由必填
- 空理由请求必须在进入 repo lock 之前返回 `400`
- 第一行作为 subject
- 完整文本作为 body
- 统一追加 `Sediment-Operation`、`Sediment-Actor-Id`、`Sediment-Actor-Name`

### 7.3 回退

一键回退只面向 Sediment 管理的 ingest / tidy 提交。

实现约束：

- 使用 `git revert --no-edit <sha>`
- revert 成功后生成新的 revert commit
- 把 `revert_commit_sha` 回写到原 job
- 回退失败必须显式 `git revert --abort`

### 7.4 推送

- push 一律手工触发
- v1 只支持“当前分支已配置 upstream”的 push
- 不提供 branch / merge / pull UI

## 8. 并发与锁

v1 采用两层保护：

### 8.1 收件箱条目级并发

- 所有状态变更接口都要求 `version` 或 `updated_at`
- 当前 REST 状态变更接口统一要求 `version`
- 缺失、非整数或小于 `1` 的 `version` 必须返回 `400`
- 使用乐观并发控制
- 冲突返回 `409`

### 8.2 仓库级串行锁

以下动作共用一个全局 repo lock：

- ingest
- tidy
- manual commit
- revert
- push

版本管理状态接口必须返回：

- 当前锁持有人
- 锁定动作类型
- 开始时间

前端据此禁用相关按钮并提示当前仓库正在被其他 committer 使用。

## 9. 写路径状态机

### 9.1 文本意见

1. 用户提交文本意见
2. 系统创建 `text_feedback`，状态为 `open`
3. `committer` 在 `提交收件箱` 查看内容
4. `committer` 点击 `已解决`
5. 条目进入历史区
6. 如有需要，可恢复成 `open`

### 9.2 上传原件与 ingest

1. 用户上传文件
2. 系统创建 `uploaded_document`，状态为 `staged`
3. `committer` 在收件箱下载、移除或放入 `ready`
4. `committer` 选择一组 `ready` 文档创建 ingest batch
5. 页面跳转到 `/admin/kb?ingest_batch=<id>&autostart=1`
6. `知识库管理` 发起 ingest job
7. Agent Runner 读取原件、抽取内容、生成草案操作
8. 主工作区应用草案并自动生成 Git commit
9. job、batch、inbox item 记录 `commit_sha`
10. 文档进入 `ingested` 历史区

### 9.3 tidy

1. `committer` 在 `知识库管理` 中选择 tidy scope 并填写原因
2. 空 `reason` 或未知 `scope` 不能创建 tidy job，必须返回 `400`
3. 创建 `tidy` job
4. Agent Runner 在隔离工作区生成 patch
5. 主工作区应用 patch 并自动生成 Git commit
6. job 记录 `commit_sha`
7. 页面显示摘要、commit SHA、受影响文件与回退按钮

### 9.4 手工编辑

1. `committer` 在 `文件管理` 中保存变更
2. 工作区产生未提交 Git 改动
3. `committer` 转到 `版本管理`
4. 输入理由并提交 commit
5. 如需要，再手工 push

## 10. Agent Runner 结果契约

Agent Runner 必须返回结构化结果，而不是只返回“成功 / 失败”。

推荐结果字段：

- `summary`
- `warnings`
- `drafts` 或 `operations`
- `apply_result`
- `commit_sha`

`apply_result` 至少应包含：

- `operations`
- `health`

每个 operation 至少应包含：

- `name`
- `relative_path`
- `change_type`
- `diff`

这份结果会同时服务于：

- `知识库管理` 结果面板
- `版本管理` 历史面板
- 审计日志

## 11. Web 信息架构

后台导航固定为：

- `总览`
- `知识库管理`
- `文件管理`
- `提交收件箱`
- `版本管理`
- `用户`
- `设置`

页面职责：

| 页面 | 唯一职责 |
|------|------|
| `提交收件箱` | 分拣用户文本意见与上传原件 |
| `知识库管理` | 执行 ingest / tidy，并显示结果与回退入口 |
| `文件管理` | 浏览与编辑 tracked 文档工作区 |
| `版本管理` | 查看 Git 状态、提交、回退、推送 |
