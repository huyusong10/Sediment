# Sediment 测试用例设计思路（E2E + DT）

本文档描述新增测试的设计目标：在“乱序执行 / 乱序操作 / 异常恢复”下验证系统稳定性。

## 1. 设计原则

- **用户真实顺序优先**：优先覆盖用户在生产中最可能的错误顺序，而非理想 Happy Path。
- **状态可重复验证**：每个用例都要有可观测输出（HTTP 状态码、CLI 返回码、JSON 字段）。
- **最小依赖**：在测试内尽量使用项目已有 fixture 和 mock backend，避免引入外部网络/模型依赖。
- **可扩展**：用例按“场景族”组织，后续可在同一族里快速扩展。

## 2. 场景族划分

### A. CLI 乱序执行（Disorder CLI）

重点覆盖：

1. **stop-before-start**：先停后启是否幂等。
2. **double-start**：重复 start 是否正确报错并保护实例。
3. **unlock-all-deleted 空扫描**：批量解锁命令在无目标时是否稳定退出。
4. **init on KB root**：在知识库目录内 init 是否正确识别并回退到父实例。
5. **quartz status/build-if-missing**：runtime/site 不同状态下命令是否可安全执行。

对应实现文件：`tests/test_cli_disorder_e2e.py`。

### B. 网页端乱序操作（Disorder Web）

重点覆盖：

1. **未登录直接调用 Admin API**：必须 401。
2. **错误 token 后恢复登录**：失败后可恢复，后续接口行为符合预期。
3. **logout 后继续操作**：会话失效后应拒绝敏感操作。
4. **越序编辑不存在条目**：应返回 404/错误，而不是写入脏数据。

对应实现文件：`tests/test_web_disorder_e2e.py`。

## 3. DT（Destructive / Disorder Tolerance）策略

新增 DT 用例关注两个维度：

- **破坏性顺序**：先做本不该先做的动作（如 stop、admin 操作、review 操作）。
- **容错恢复**：错误发生后系统是否还能回到可操作状态（如错误登录后重新登录）。

建议后续继续扩展：

- 并发提交 + 并发 ingest 的竞态用例。
- `server start/stop/restart` 快速抖动测试。
- Quartz build 中断后的二次恢复测试。
- instance unlock/remove 与 Windows 文件锁的长链路回归。

## 4. 质量门禁建议

- 将 `test_cli_disorder_e2e.py` 与 `test_web_disorder_e2e.py` 纳入 CI 必跑集合。
- 对关键命令增加平台矩阵（Linux + Windows）回归。
- 对失败场景固定断言：返回码、错误信息关键字、状态字段。

## 5. 验收标准

- 乱序场景下：**系统不崩溃**、**错误可预期**、**可恢复**。
- CLI/网页端操作后：状态数据一致（review、job、session、daemon）。
- 失败路径可追踪（日志 + 明确错误响应）。
