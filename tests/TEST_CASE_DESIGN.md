# Sediment 测试设计契约

本文档约束测试如何保护 Sediment 的稳定对外行为，并尽量不给未来重构制造负担。

## 1. 核心目标

- 测试保护对外契约，而不是当前实现细节。
- 只有用户可感知行为、公开接口、稳定数据结构与核心流程值得被锁定。
- 内部重构在不改变契约的前提下，应尽量不触发测试修改。

## 2. 分层策略

| 层级 | 保护对象 | 适用场景 | 当前主要落点 |
| --- | --- | --- | --- |
| E2E | 核心用户旅程与页面级行为 | 登录、提交、审核、后台工作台、前台搜索 | `tests/test_web_browser_e2e.py` |
| 接口 / 集成 | 路由、CLI、模块边界、流式协议 | Admin API、CLI JSON 输出、Explore runtime、文件管理接口 | `tests/test_web_e2e.py`、`tests/test_cli.py`、`tests/test_explore_runtime.py` |
| 单元 | 稳定且复杂的规则 | 只有规则复杂且实现独立时才新增 | 按需新增，不默认铺开 |

## 3. 编写规则

- 面向契约，不面向私有实现：断言状态码、返回结构、消息类型、用户可见结果，不断言内部变量或调用顺序。
- 优先使用稳定锚点：`data-testid`、语义角色、公开 API 字段；避免依赖脆弱 DOM 层级或具体 CSS 数值。
- 样式与文案微调默认不应触发回归；只有当它们本身构成契约时才应被测试，例如 locale 单语显示、页面级标题是否存在、布局区块的相对关系。
- 对布局只验证稳定的结构关系，例如“右侧上下堆叠”或“Live 位于工作台下方”，不锁死像素、颜色、圆角、渐变等视觉实现。
- 对运行时诊断只验证结构、关联标识、可观测事件与终态，不依赖具体日志模板或某一种语言的 message 文案。

## 4. 当前关键契约

### 4.1 CLI 与运行时

1. `status`、`status queue` 等 JSON 输出必须保持稳定字段，支撑自动化和脚本调用。
2. `kb explore --json` 的成功结果必须来自 Explore runtime；当 runtime 失败时必须返回显式错误，而不是伪造固定答案。
3. Explore runtime 在 Agent 输出无效时必须暴露可诊断原因，至少包含失败原因与可观测重试。
4. 平台诊断日志必须遵守统一 JSONL 结构；`logs show/follow` 要能消费新结构，同时兼容旧前缀日志。
5. HTTP 动态页面与 API 响应必须返回 `X-Request-ID`，便于把用户侧失败与平台日志关联起来。
6. 内置 skill 资产必须保持语言中立；`src/sediment/skills/` 中不能回流中文提示词或中文启发式词表，locale 相关词汇必须通过集中式本地化规则提供。
7. `sediment doctor` 的 `server.port` 检查在受限环境下可以降级为被动本地探测并给出不确定提示；不能因为临时 bind 探针被系统禁止，就把实例整体判成失败。
8. `audit_kb` / health 发现 malformed YAML frontmatter 时，必须把它转成结构化 hard failure 或 invalid index，而不是让整轮巡检直接崩溃。
9. MCP 写工具在空 `submitter_name`、空 document 载荷、混合 document 载荷、部分坏掉的 document files 条目、无效 scope、空 actor/reviewer 身份、显式空 reason、缺失必填字段、无效 decision 或不存在 review 下，必须返回结构化 `error`，且不得创建 inbox item、job 或推进 review / job 状态；只有真正省略 reason 时才允许使用默认审计理由。

### 4.2 前台 Web

10. `/`、`/search`、`/entries/{name}`、`/submit`、`/tutorial`、`/portal/graph-view` 必须稳定渲染同一前台 `Universe OS` 壳层，并通过 route-level initial state 进入对应探索、搜索、阅读、提交或教程态。
11. `survey` 搜索态、搜索建议弹层、`Spatial Card`、提交面板与教程面板不能推挤宇宙主舞台或 HUD；状态切换应保持固定锚点和稳定高度。
12. 前台 HUD、utility 控件与后台入口必须彻底分离；前台不得暴露 admin 主入口，`Quartz` 继续作为次级只读入口存在。
13. 接入教程必须继续锁定“MCP 或 Skill”的决策结构，但内容承载位置改为宇宙内教程面板，而不是独立页面模板。
14. 教程面板必须同时说明 `knowledge_ask` 快答路径与 `knowledge_list` / `knowledge_read` 白盒推导路径，并保留 Skill 下载入口。
15. 默认语言契约为英文优先；显式中文参数或中文环境信号才切换到中文；词条标题保持原始语言，UI 文案才做 locale 切换。
16. Sediment 托管的 `/quartz/` 必须保留 Quartz 图谱运行能力，路由级安全头不能导致图谱脚本失效。
17. Quartz 构建流程必须在需要时归一化上游图谱运行时的浏览器兼容性默认值，不能把已知会导致常见桌面浏览器空白图谱的默认值直接透传给最终站点。
18. Quartz 关系图谱必须排除导航型索引页；根索引与分段索引可以继续参与站点导航，但不能作为图谱节点或关系中心污染知识关系视图。
19. 当当前 Quartz 页面本身是导航型索引页时，局部关系图组件必须隐藏，不能留下空白图谱框作为退化占位。
20. 新实例默认知识库脚手架必须只生成一个根索引首页；不能再默认创建 `Index Root -> index.core` 这种分段索引占位结构。

### 4.3 后台 Web

21. `/admin/overview` 必须稳定呈现总览、治理焦点和最近活动，长列表采用可滚动容器，不无限拉长页面。
22. `/admin/kb` 只负责 ingest、tidy、explore 三类动作，不承载文件编辑工作区。
23. `/admin/kb` 桌面端必须维持“左上 ingest、右上 tidy、右下 explore、下方 Live”的工作台结构。
24. `/admin/kb` 的说明性文案默认折叠进 tip，避免把长说明直接铺进卡片正文。
25. `/admin/kb` 的 Live 区必须作为共享诊断通道存在；explore 运行时至少暴露请求、运行输出与终态，而不是只显示静态“加载中”。
26. `/admin/kb` 各分区的状态条必须只反映各自动作；一个分区失败不能覆盖其他分区的状态，跨动作诊断统一进入 Live。
27. 后台 explore 的成功结果必须来自 Agent 输出；当 Agent 输出无效或 CLI 失败时，公开入口必须返回显式失败，不得回退成固定代码生成的回答卡片。
28. `/admin/files` 必须独立为一级功能，提供结构浏览、搜索建议、在线编辑与健康联动。
29. `/admin/system` 必须保持 owner-only，并提供原始配置、解析后配置与重启入口。
30. 中文后台页面必须直接使用当前 locale，不把通用英文词与中文拼接在同一标题、按钮或主区块里。
31. 接受 JSON body 的 Web 写接口在 malformed 或 non-object 请求体下必须返回 `400`，且不得产生部分写入、误提交或状态推进。
32. 门户文档上传与后台 direct upload ingest 的 document payload 必须在 `content_base64` 与 `files` 之间二选一；任一坏掉的 `files` 条目都必须让整次请求返回 `400`，且不得创建 inbox item / batch / job。
33. `/api/admin/ingest/document` 的 direct upload 成功返回体必须以 `item` 表示新建的 `uploaded_document`；若保留 `submission` 字段，也只能作为兼容别名，且两者必须指向同一 inbox item。
34. 收件箱状态变更接口必须显式要求 `version`；缺失、非整数或过小版本号返回 `400`，真实版本冲突才返回 `409`。
35. `/api/admin/tidy` 与 `/api/admin/version/commit` 的 `reason` 必须是非空文本；无效 tidy scope 或空 reason 不能入队、也不能抢 repo lock。
36. `/api/admin/reviews/{id}/approve` 只能接受批准类 decision；错误的 reject/cancel 语义必须返回 `400`，且 review 与 job 状态保持不变。

### 4.4 乱序与恢复

37. 未登录、错误 token、logout 后继续操作等乱序路径必须稳定失败，并且后续可恢复到正常工作流。
38. stop-before-start、double-start、空目标批量操作等 CLI 乱序场景必须稳定退出，不破坏实例状态。

## 5. 何时新增或更新测试

- 新增或修改公开路由、CLI 命令、核心页面工作流、核心组件对外行为：新增或更新集成 / E2E。
- 修改内部实现但不改契约：优先不改测试；若失败，先判断是否破坏了契约。
- 纯样式微调、排版调整、文案润色：默认不新增测试，也不应导致已有契约测试失败。
- 新增复杂而稳定的规则计算：仅在规则本身具备长期稳定性时补单元测试。

## 6. 文件映射

- `tests/test_web_browser_e2e.py`
  - 保护关键用户旅程、主要页面布局关系、后台工作台可操作性。
- `tests/test_web_e2e.py`
  - 保护公开 Web 路由、流式接口、locale 输出与页面表面契约。
- `tests/test_cli.py`
  - 保护 CLI JSON 契约与命令级边界行为。
- `tests/test_diagnostics.py`
  - 保护结构化日志格式、敏感字段裁剪和旧日志兼容解析。
- `tests/test_explore_runtime.py`
  - 保护 Explore runtime 的 Agent 输出校验、错误显式化与可诊断性。
- `tests/test_web_ui_style.py`
  - 只保护共享 shell 与关键页面的稳定表面钩子，不锁定具体 CSS 实现细节。
- `tests/test_cli_disorder_e2e.py`、`tests/test_web_disorder_e2e.py`
  - 保护乱序操作与失败恢复能力。
