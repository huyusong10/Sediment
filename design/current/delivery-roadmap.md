# 当前设计：实施路线图

这份路线图的目标不是列愿望清单，而是把企业版 Sediment 拆成可连续交付的阶段。

## 1. 实施原则

- 先把写路径做对，再做界面丰富化
- 先让提交和审核可用，再追求自动化覆盖率
- 先让 Agent Runner 托管化，再把更多治理动作接进后台
- 不破坏现有 `knowledge_list` / `knowledge_read` / `knowledge_ask`

## 2. 阶段 0：服务层重构

目标：

- 把现有 MCP 逻辑从单文件路由中拆成可复用 service 层

交付：

- `inventory`、`knowledge_read`、`knowledge_ask` 下沉到 service 模块
- REST 路由骨架
- 数据库接入骨架

完成标准：

- 现有 MCP 读能力行为不变
- 新增 REST 服务不会破坏现有 SSE / JSON-RPC

## 3. 阶段 1：提交缓冲区

目标：

- 让用户可以在不接触知识库本地文件的情况下提交内容

交付：

- `submissions` 表
- `POST /api/portal/submissions/text`
- `POST /api/portal/submissions/document`
- MCP `knowledge_submit_text`
- MCP `knowledge_submit_document`
- 基础限流、IP 记录、文件落盘

完成标准：

- 纯文本和文档都能提交到缓冲区
- 提交不会直接写入知识库
- 每个提交都可追溯提交者、IP、时间和原始内容

## 4. 阶段 2：前台知识库界面

目标：

- 提供可替代“直接翻文件”的浏览层

交付：

- 首页、搜索页、接入教程页、条目页、图谱页、提交页
- 全文搜索 API
- 图谱 API
- Markdown 渲染

完成标准：

- 用户可在 Web 上搜索、查看条目和浏览图谱
- 搜索结果只包含正式知识层

## 5. 阶段 3：后台管理台

目标：

- 建立 `committer` 的日常工作台

交付：

- 提交列表和详情页
- health 总览和 issue 列表
- 任务列表
- 审核动作接口
- 在线编辑器基础版

完成标准：

- `committer` 可在 Web 上 triage 提交
- `committer` 可查看 health 并定位问题条目
- `committer` 可在线修改条目并触发校验

## 6. 阶段 4：Agent Runner 托管化

目标：

- 把 ingest / tidy 从“手工本地跑”变成“服务托管本地跑”

交付：

- `jobs` 表
- Agent Runner 进程
- ingest 任务执行链
- tidy 任务执行链
- 隔离工作区和 diff 产物

完成标准：

- 后台可发起 ingest / tidy
- Agent Runner 在知识库所在主机执行 skill
- 结果以 diff 和结构化说明返回

## 7. 阶段 5：审核闭环

目标：

- 建立从任务结果到合并入库的闭环

交付：

- review 页面
- patch / diff 预览
- approve / reject / request changes 动作
- 合并前 validation / health refresh
- 审计日志

完成标准：

- Agent 结果必须经 `committer` 批准才能写回
- 合并失败时能看到明确原因
- 所有合并动作可追溯

## 8. 阶段 6：硬化与扩展

目标：

- 把系统从“能跑”推进到“能稳”

交付：

- SSO / OIDC
- 权限模型细化
- 失败重试与任务取消
- 更丰富的搜索排序
- 可选 Quartz 只读导出

完成标准：

- 管理台具备生产环境鉴权
- 提交、任务、审核链路有监控和告警

## 9. 测试与验收

每个阶段至少要补三类测试：

- 服务层单元测试
- API 集成测试
- 关键人工验收脚本

关键验收场景：

- 文本提交 -> 缓冲区可见
- 文档上传 -> 可提取文本 -> 可进入 ingest
- health 问题 -> 发起 tidy -> 看到 diff -> 审核通过 -> 问题消失
- 在线编辑 -> 校验失败阻止保存

## 10. 推荐执行顺序

推荐按下面顺序推进：

1. 阶段 0
2. 阶段 1
3. 阶段 3
4. 阶段 4
5. 阶段 5
6. 阶段 2
7. 阶段 6

这样做的原因是：

- 先把写路径、审核和任务链路跑通
- 再把面向普通用户的浏览体验做完整

如果团队更重视早期展示效果，也可以把阶段 2 提前到阶段 3 前，但不应晚于阶段 5。
