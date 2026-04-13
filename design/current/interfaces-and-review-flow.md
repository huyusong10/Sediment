# 当前设计：接口与审核流

企业版 Sediment 的接口设计目标不是“让所有人都能写文件”，而是“让所有人都能提交，且所有写路径都有显式状态”。

## 1. 接口分层

接口分成三类：

- MCP 读接口：给 Agent 和 IDE 做知识检索
- MCP 写接口：给 Agent 或自动化流程提交材料、发起任务或读取治理状态
- REST 接口：给 Web 前后台做浏览、上传、审核、任务管理和在线编辑

## 2. MCP 工具规划

### 2.1 保持稳定的读工具

以下工具继续保持稳定：

- `knowledge_list`
- `knowledge_read`
- `knowledge_ask`

### 2.2 新增提交工具

第一阶段应新增两类提交工具：

- `knowledge_submit_text`
- `knowledge_submit_document`

建议输入：

`knowledge_submit_text`

```json
{
  "title": "热备份切换前先确认接管链路",
  "content": "……纯文字概念或经验……",
  "submitter_name": "Alice",
  "submission_type": "concept|lesson|feedback"
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

- 工具只创建缓冲区记录
- 返回 `submission_id`
- 不直接写入知识库

### 2.3 后续可选治理工具

面向 `committer` 或自动化流程，可后续增加：

- `knowledge_health_report`
- `knowledge_submission_queue`
- `knowledge_review_decide`
- `knowledge_job_status`

## 3. REST 接口规划

### 3.1 前台门户

- `GET /api/portal/home`
- `GET /api/portal/search?q=...`
- `GET /api/portal/entries/{name}`
- `GET /api/portal/graph`
- `POST /api/portal/submissions/text`
- `POST /api/portal/submissions/document`
- `POST /api/portal/feedback`

### 3.2 管理后台

- `GET /api/admin/session`
- `POST /api/admin/session`
- `DELETE /api/admin/session`
- `GET /api/admin/system/status`
- `GET /api/admin/audit`
- `GET /api/admin/health/summary`
- `GET /api/admin/health/issues`
- `GET /api/admin/submissions`
- `GET /api/admin/submissions/{id}`
- `POST /api/admin/submissions/{id}/triage`
- `POST /api/admin/submissions/{id}/run-ingest`
- `POST /api/admin/jobs/{id}/run-tidy`
- `GET /api/admin/jobs/{id}`
- `POST /api/admin/jobs/{id}/retry`
- `POST /api/admin/jobs/{id}/cancel`
- `GET /api/admin/reviews`
- `POST /api/admin/reviews/{id}/approve`
- `POST /api/admin/reviews/{id}/reject`
- `GET /api/admin/entries/{name}`
- `PUT /api/admin/entries/{name}`
- `GET /api/admin/diffs/{id}`

这些接口不要求一次全部实现，但 URL 形态应尽早固定。

## 4. 提交缓冲区数据模型

提交缓冲区至少需要一张 `submissions` 表。

建议字段：

- `id`
- `submission_type`：`text`、`document`、`feedback`
- `title`
- `raw_text`
- `stored_file_path`
- `mime_type`
- `submitter_name`
- `submitter_ip`
- `submitter_user_id`
- `status`
- `dedupe_hash`
- `created_at`
- `updated_at`

`status` 建议值：

- `pending`
- `triaged`
- `ingesting`
- `draft_ready`
- `accepted`
- `rejected`
- `archived`

## 5. 审核记录模型

审核记录不应只保存在 Git 评论里，还应显式建表。

建议 `reviews` 表字段：

- `id`
- `submission_id`
- `job_id`
- `review_type`：`ingest`、`tidy`、`manual_edit`
- `decision`
- `reviewer_id`
- `reviewer_name`
- `comment`
- `created_at`

`decision` 建议值：

- `approve_placeholder`
- `approve_formal`
- `request_changes`
- `reject`
- `cancel`

## 6. 任务模型

ingest 和 tidy 都应被建模成后台任务，而不是一次同步 HTTP 调用。

建议 `jobs` 表字段：

- `id`
- `job_type`：`ingest`、`tidy`、`health_refresh`、`reindex`
- `source_submission_id`
- `target_entry_name`
- `status`
- `runner_host`
- `workspace_path`
- `result_payload`
- `error_message`
- `created_at`
- `started_at`
- `finished_at`

`status` 建议值：

- `queued`
- `running`
- `cancel_requested`
- `awaiting_review`
- `succeeded`
- `failed`
- `cancelled`

默认实现形态建议是：

- server 负责创建 `queued` job
- 独立 worker 进程认领并执行 job
- worker 定期写 heartbeat
- worker 或 store 层回收心跳超时的陈旧任务
- 执行完成后把 job 更新为 `awaiting_review`、`succeeded` 或 `failed`

## 7. 写路径状态机

典型的 ingest 路径如下：

1. 用户提交文本或文档
2. 系统创建 `pending` submission
3. `committer` triage，决定拒绝、归档或运行 ingest
4. 创建 `ingest` job
5. Agent Runner 产出草案和 diff
6. 任务进入 `awaiting_review`
7. `committer` 批准、退回修改或拒绝
8. 批准后写回知识层
9. 触发 validation / health refresh

典型的 tidy 路径如下：

1. health 发现问题或后台手动发起 tidy
2. 创建 `tidy` job
3. Agent Runner 在隔离工作区执行 tidy skill
4. 产出 patch、原因和上下文
5. `committer` 审核
6. 通过后应用 patch
7. 重新运行对应范围的 health 检查

## 8. Agent Runner 执行契约

Agent Runner 不应只返回“成功 / 失败”，还应返回结构化结果：

- `summary`
- `changed_files`
- `diff`
- `reasoning_notes`
- `evidence_contexts`
- `validation_before`
- `validation_after`

这样后台才能把任务结果变成人类可审阅的对象，而不是黑盒按钮。

## 9. 限流与安全

公开提交接口至少需要：

- 提交者必须填写名字
- 记录可信来源 IP
- 每 IP 每分钟最多一次提交
- 完全重复提交去重
- 可附加同名提交者限流
- 文件大小限制
- MIME 类型白名单

推荐首批支持：

- `text/plain`
- `text/markdown`
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- `application/vnd.openxmlformats-officedocument.presentationml.presentation`

## 10. 合并前保证

任何写回知识层的路径都应满足：

- 有明确 reviewer
- 有可审阅 diff
- 跑过 `validate_entry` 或 `audit_kb`
- 检查目标文件未发生基线漂移
- 记录审计日志
- 管理后台写路径必须有有效 admin session 或 Bearer token

这些保证比“是不是走 Git commit”更重要。
