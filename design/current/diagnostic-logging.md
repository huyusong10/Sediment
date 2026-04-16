# 当前设计：诊断日志

本文档定义 Sediment 的平台级诊断日志契约，用于支撑值班排障、后台 Live、CLI `logs` 与跨模块问题定位。

它不描述内部实现细节，而只锁定日志结构、边界职责和消费方式。

## 1. 目标

- 让一次请求、一次任务、一次 Agent 执行都能被跨模块追踪。
- 让 launcher、server、worker、Agent Runner、平台服务层与治理入口使用同一套结构化日志规则。
- 让长期日志、CLI 渲染与后台工作台 Live 各司其职，而不是互相替代。

## 2. 诊断日志与其他记录的边界

| 类型 | 回答的问题 | 保存位置 | 是否长期保留 |
| --- | --- | --- | --- |
| 诊断日志 | 系统当时做了什么、卡在哪、失败在哪一层 | 平台日志文件 | 是 |
| 审计日志 | 谁触发、批准、拒绝了什么治理动作 | 工作流存储 | 是 |
| Live 运行轨迹 | 当前 ingest / tidy / explore 正在输出什么 | 后台工作台 | 否，面向当前交互 |

约束：

- 审计日志不能替代诊断日志。
- Live 不能作为唯一真相源；长期排障仍以平台日志为准。
- 诊断日志不记录完整业务原文、用户正文或敏感凭据。

## 3. 标准日志结构

日志文件使用单行 JSON（JSONL）。每条记录至少包含：

| 字段 | 说明 |
| --- | --- |
| `ts` | UTC ISO8601 时间戳 |
| `level` | `DEBUG / INFO / WARNING / ERROR` |
| `component` | 稳定组件名 |
| `event` | 稳定事件名，使用 `domain.action` 风格 |
| `message` | 面向人的简短摘要 |

常见可选字段：

| 字段 | 说明 |
| --- | --- |
| `request_id` | 单次 HTTP 请求或交互链路标识 |
| `job_id` | 平台任务标识 |
| `submission_id` | 提交标识 |
| `review_id` | 审核标识 |
| `session_id / user_id / actor_id` | 会话与操作者标识 |
| `workspace_id` | 隔离工作区或临时执行上下文标识 |
| `details` | 小而稳定的结构化补充信息 |
| `error` | 错误类型与摘要消息 |
| `pid / thread` | 进程与线程信息 |

## 4. 事件与字段规则

### 4.1 命名

- `component` 必须稳定，例如 `launcher`、`server`、`http`、`worker`、`agent_runner`、`platform_services`、`control`、`explore`。
- `event` 必须表达边界动作，而不是实现细节。
- 优先记录这些生命周期：开始、完成、失败、降级、重试、取消、超时、心跳、显式跳过。

### 4.2 关联信息

- 边界入口在进入一次请求或任务时，应先绑定关联上下文，再由下游日志自动继承。
- HTTP 响应必须回传 `X-Request-ID`，便于把用户看到的失败与日志串起来。
- 同一条链路里若同时存在 `request_id` 与 `job_id` / `submission_id`，应同时保留，而不是后者覆盖前者。

### 4.3 内容裁剪

- 一条日志只表达一个事件，不输出多行日志块。
- `details` 只放有助于排障的摘要信息。
- prompt、正文、stdout、stderr、diff、body 等大文本只保留 excerpt 与长度。
- token、cookie、secret、password、authorization 等敏感字段必须打码，只能保留长度、指纹或 redacted 标记。

### 4.4 多语言

- 自动化消费方必须依赖 `component / event / level / 关联字段`，不能把某种语言的 `message` 当成稳定协议。
- `message` 是给人看的摘要，可按 locale 本地化，也可在不同消费端渲染成不同语言。
- 因此测试默认不锁定具体 message 文案，除非某条 message 本身就是外部契约。

## 5. 模块适配边界

| 模块 | 必须负责的日志边界 |
| --- | --- |
| `launcher` | 子进程启动、早退、停机、健康等待、Quartz 构建 |
| `server` | 服务启动、后台重启调度、边界级错误 |
| `http` | 请求完成 / 失败、状态码、时延、请求标识 |
| `worker` | 启动、停止、抢占任务、单次轮询结果 |
| `agent_runner` | ingest / tidy / explore 的 Agent 调度、取消、失败、超时、等待审核 |
| `platform_services` | 提交分析、文档准备、降级路径、创建 submission |
| `control` | 手工 enqueue ingest / tidy 等治理入口 |
| `explore` | CLI 启动、stdout / stderr、心跳、重试、终态 |

## 6. 消费规则

- 日志文件保存原始 JSONL，作为唯一长期诊断真相源。
- `sediment logs show/follow` 负责把 JSONL 渲染成一行摘要，同时兼容历史前缀日志。
- 后台 `/admin/kb` 的 Live 只展示当前工作台动作的运行轨迹，不覆盖长期日志职责。
- 新模块若需要诊断输出，必须复用统一日志工具，不再新造 `print("[xxx] ...")` 约定。

## 7. 非目标

- 诊断日志不是全文归档系统，不负责存原始文档或完整 Agent 输出。
- 诊断日志不替代业务返回值；接口是否成功仍以接口契约为准。
- 诊断日志不要求所有 CLI 用户输出都结构化；面向人的命令结果可继续保持普通文本或 JSON 输出。
