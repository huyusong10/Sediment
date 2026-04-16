# 当前设计：Web 界面

企业版 Sediment 的 Web 层分成两个真正独立但共享 API 与配置的界面：

- 前台知识库界面
- 后台管理台

两者不应混在一个导航层里，否则“浏览知识”和“治理知识”会互相污染。

## 1. 产品决策

当前设计选择继续保留 Python + Starlette + asset-template 的服务端渲染栈，不把 Quartz 作为主产品壳。

理由：

- 前台和后台都需要动态 API、提交、审核、状态轮询和鉴权
- Quartz 更适合只读静态浏览，不适合作为审核流与管理工具的基础
- 现有 Python 服务栈已经覆盖搜索、提交、审核、会话和审计能力，继续沿用成本最低
- 两套页面虽然共享基础壳，但必须在导航、配色和职责上彻底拆开

Quartz 现在作为前台可直达的只读知识入口挂载在 `/quartz/` 下，由 Sediment 服务层以 clean URL 方式托管。

## 2. 前台知识库界面

### 2.1 目标

前台面向普通用户，负责：

- 浏览知识库
- 搜索概念
- 查看条目全文
- 直接跳入 Quartz 只读站点
- 提交材料和修订意见

### 2.2 页面结构

- `/`
  - 公共知识库概览页
  - 品牌区使用带文字的 Sediment logo lockup，知识库名显示在 logo 右侧
  - 搜索作为主入口，搜索按钮居中
  - live suggestions 以悬浮下拉窗显示，不应挤压页面布局
  - 为避免与已选中的“知识库概览”菜单重复，首页可将语义 h1 设为 sr-only；品牌标识与 utility 图标不能替代 page-level heading
  - 一级导航单独放在标题区下方，不与品牌和 utility 混排
  - 知识库统计以横向卡片条展示，并位于最近更新上方
  - 最近更新区不再放二次提交按钮，避免与主搜索入口竞争注意力
- `/portal`
  - 兼容性重定向到 `/`
- `/search`
  - 全文搜索结果浏览
  - 支持标题、别名、摘要、正文命中
  - 支持摘要片段
- `/tutorial`
  - 接入教程页
  - 说明如何通过 MCP SSE 服务接入
  - SSE 端点优先从 `server.public_base_url` 生成；未显式配置时，才回退到受信代理头或当前请求基址
  - 顶层只要求用户先做一个决策：选择 MCP 还是选择本地 Skill
  - 同时说明两条接入路径：`knowledge_ask` 的服务端快答路径，以及 `knowledge_list` / `knowledge_read` 的本地白盒推导路径
  - 默认以精简说明展示，补充细节通过 hover / focus tip 展开，而不是默认堆叠长段落
  - Agent 接入示例使用自然语言指令句式，强调如何点名特定 MCP server / tool，而不是展示 SDK 代码
  - `工具分工` 与 `如何让 Agent 用对工具` 都属于 MCP 区块内部说明，而不是独立于 MCP / Skill / 决策之外的第四类模块
  - 提供单个本地 Explore SKILL 下载入口，用于在本地复刻 ask 的白盒推导逻辑
- `/entries/{name}`
  - 独立条目详情页
  - 页头承担标题
  - hero 区的可见一级标题与浏览器标题都要同步到 canonical title
  - 结构化 metadata / canonical sections / residual Markdown 分离显示
- `/submit`
  - 纯文本概念/经验提交
  - 文档上传
  - 默认匿名，但登录用户会被额外记录 `submitter_user_id`
- `/quartz/`
  - 直接进入 Quartz
  - 由 Sediment 负责 `exact -> .html -> /index.html -> 404.html` 解析
  - 前台主导航里的 `Quartz` 默认使用新标签打开
- `/portal/graph-view`
  - 兼容性入口
  - Quartz 已构建时重定向到 `/quartz/`
  - Quartz 未构建时显示 fallback 说明页
  - 意见反馈

### 2.3 前台功能要求

- 支持 live suggestion 下拉、debounce、键盘导航与“查看全部结果”
- 搜索建议弹层不应导致搜索按钮、统计区或最近更新发生布局位移
- 搜索状态文案固定在搜索控件下方，并预留稳定高度，避免 suggestion / 搜索态切换时推挤按钮或结果区
- 支持查看结构化条目详情，而不是 modal-only 渲染
- 支持查看 Markdown 正文渲染结果
- 浏览保持匿名
- 提交默认匿名；如携带有效 owner / committer session，则额外绑定真实 user identity
- 后端自动记录 IP
- 至少按 IP 做每分钟 1 次限流
- 主导航不出现后台入口；主题切换与语言切换位于 utility 区
- utility 区与一级导航必须形成清晰的视觉分区，不能混在同一排主功能中
- 一级导航固定左对齐，并使用等宽、等高且更紧凑的按钮承载知识库主路径
- utility 控件固定在右上角，使用紧凑图标按钮或弱化 utility action，而不是一级菜单样式
- 内容区中并排出现的 CTA 也必须使用等宽等高动作行，不能混用导航按钮样式和普通按钮样式
- 除首页概览页可使用 sr-only 语义标题避免重复外，其余前台主页面都保留可见一级标题；brand 负责实例身份，不负责替代当前页面标题
- 各页面大标题下不再放额外说明性段落，避免重复噪音
- `/submit` 的标签、按钮和占位提示必须完全走 locale 文案，不能残留单语言硬编码
- Web 默认语言为英文；只有 query 明确指定 `lang=zh` 或检测到本地 / `Accept-Language` 为中文时才默认显示中文
- 接入教程必须给出工具分工、MCP vs Skill 的选择说明，以及至少一个 AI Agent 接入示例
- 接入教程中的 MCP 端点说明必须能适配域名、反向代理与路径前缀，不能把本地监听地址硬编码到页面中
- 接入教程中的冗长说明默认折叠为 compact note，并通过右上角 tip 展示完整解释，避免首屏信息噪音
- 条目详情页的 `Entry Signals` 只展示有效信号，并以紧凑侧栏/紧凑卡片布局呈现，避免空占位

## 3. 后台管理台

### 3.1 目标

后台面向 `committer` 与 `owner`，负责：

- 审核提交
- 在线编辑条目
- 常驻展示 health
- 发起和查看 ingest / tidy 任务
- 审阅 diff 和 patch
- 管理用户与系统（owner-only）

### 3.2 页面结构

- `/admin`
  - 兼容性重定向到 `/admin/overview`
  - 登录页与后台各主页面都保留可见一级标题
- `/admin/overview`
  - 总览卡片
  - health 摘要
  - 只读问题概览
  - 最近活动与审计
  - 治理焦点列表和最近活动列表都设置较大的最大高度并启用滚动，避免后台首屏被超长队列无限拉长
  - 两列信息卡片使用 top-aligned 布局，不把短列强行拉伸成与长列等高
- `/admin/kb`
  - 显示名称为“知识库管理”
  - Ingest：支持拖入文件、文件夹或压缩包，上传后直接创建 submission 并入队 ingest
  - Tidy：只保留一个原因输入框和一个执行按钮；后台默认按阻断性 health scope 发起治理
  - Explore：保留当前知识探索 / 问答能力
  - 中文界面内的功能标题统一采用 `English + 中文` 形式，例如 `Ingest 导入`、`Tidy 整理`、`Explore 探索`
- `/admin/files`
  - 独立一级功能“文件管理”
  - 不直接平铺全部 Markdown，而是按 `index.root` 与分段 index 组织结构浏览
  - 浏览区与编辑区采用上下布局：上方负责 index 结构与健康联动，下方负责编辑、预览和关联问题
  - 文档搜索必须提供自动建议；点击建议、命中精确名称或从健康问题跳转时直接载入编辑区，不要求额外的“加载”按钮
  - 文档搜索建议必须支持上下键选择与 Enter 打开，且显式键盘/鼠标选择优先于 exact-match 自动载入
  - 编辑区优先保证可用面积：大尺寸 Markdown 编辑器、门户同款预览、关联治理问题纵向排列
  - 当前继续使用原生 details/tree + 搜索建议方案；虽然第三方树组件可提供更复杂交互，但其 jQuery / bundler 依赖与现有 shell 不匹配，因此暂不引入
- `/admin/reviews`
  - 左侧待审队列 + 右侧详情的主从工作流
  - 详情区集中展示来源提交、摘要、diff 与评审备注
  - approve / reject 动作只在详情区出现
  - jobs 作为辅助状态面板保留在下方
- `/admin/users`
  - owner-only
  - 只允许创建 committer
  - owner 保持唯一且不可通过 UI 新建
  - token 在对应用户卡片内联展开，不使用脱离上下文的独立展示面板
- `/admin/system`
  - owner-only
  - 路由保持 `/admin/system`，但可见名称改为“设置”
  - 在线查看和编辑原始 YAML 配置
  - 同时展示展开后的有效配置，以及运行时 / 限流 / Quartz 状态摘要
  - 原始 YAML 编辑器和 resolved config 预览都应占满各自面板的主要空间，而不是只给出狭窄小框
  - 提供 owner-only 的一键重启按钮，用于让 host / port / SSE path 等监听级配置完整生效
  - host / port / SSE path 等监听级配置允许在线修改，但仍需要重启服务后才能完全生效

### 3.3 后台必须具备的能力

- 在线编辑正式条目、placeholder 与 index 文档
- 查看 health 结果并常驻刷新
- 查看未进入正式知识库的提交
- 支持从 index 结构树、搜索建议和 health issue queue 三个角度选择文档
- 支持直接上传文档并触发 ingest
- 以 KB scope 发起 tidy 任务，而不是针对单条目目标
- 审阅 Agent 生成的 patch
- 显示审计日志
- 显示系统状态、Quartz 状态、队列模式和限流配置
- owner-only 在线查看和编辑全部配置
- 支持任务 cancel / retry
- owner-only 管理用户与系统

## 4. 共享组件

前台和后台至少共享以下组件：

- 条目摘要卡片
- Markdown 渲染器
- 搜索结果列表
- 来源和状态标签
- 统一 theme / language utility 控件

## 5. 图谱设计

图谱不应只是一个装饰性页面，而应同时服务于：

- Quartz 前台导航
- 后台诊断孤岛与弱连接条目

图谱节点至少区分：

- `concept`
- `lesson`
- `placeholder`
- `index`

图谱边至少区分：

- `Related`
- `index_link`

## 6. 搜索设计

搜索排序建议优先考虑：

1. 标题命中
2. 别名命中
3. 摘要命中
4. 正文命中
5. canonical / 健康加权

前台默认隐藏未合并草案和缓冲区内容。

后台可选择切换查看：

- 仅正式知识层
- 正式知识层 + 待审核草案

## 7. 编辑器设计

在线编辑器应支持：

- Markdown 编辑
- 即时预览
- frontmatter 保持
- 调用后端校验
- 合并前 diff 预览

后台在线编辑是受控直接编辑路径，不替代 submit / review 主流程。

## 8. 权限设计

前台权限：

- `anonymous` 可浏览、搜索、查看和提交

后台权限：

- `committer` 可 triage、发起 ingest / KB-level tidy、审核、在线编辑、合并
- `owner` 拥有全部后台权限，并额外负责用户管理、系统设置、Quartz 构建与服务器级操作
- Admin Web 登录使用同站 session cookie，也接受 Bearer token
- 所有特权写操作都由服务端从 session / token 解析 `actor_id`、`actor_name`、`actor_role`

## 9. 前端技术建议

当前落地方案：

- 继续使用 `Starlette + asset templates + page-specific JS`
- 知识库界面与后台共享基础 shell，但分别使用 portal/admin palette
- Quartz 继续作为独立静态站点托管，不把图谱重新发明到主壳里
- 重点优先保证“搜索、条目详情、提交、审核、KB-level tidy、用户/系统权限”这些链路完整可用

## 10. UI 视觉规范

- **极简科技风（年轻化）**：多用矩形，去除多余的圆角（`border-radius: 0`）。背景建议增加极其微弱的点阵/网格背景增强极客氛围。
- **去除“AI 味”**：避免过度使用模糊（blur）、高光渐变色、大面积微光发散等显得过于花哨且不写实的修饰效果。
- **动效微交互**：对所有交互元素（Button、Card、Input、Panel 等）加入干脆利落的微过渡动效（`transition`）。通过交互时的 `translate` 悬浮位移与元素微量外发光改变提供明确的即时操作反馈。
- **浅底盘 / 面板悬浮 (Subtle Plate Contrast)**：避免粗笨的直接线框。页面的视觉层级由轻微的底色差构成（例如采用浅灰 `bg` 为底层盘，纯白或深黑作为 `panel` 色），区域间仅以极淡的透明度线条（例如 `rgba(125,125,125, 0.15)`）勾勒，配合微小的弥散阴影提升边界感。用最隐忍克制的区块明暗差，传达“现代、优雅、极客”的高级感。
