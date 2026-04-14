# 当前设计：Web 界面

企业版 Sediment 的 Web 层分成两个真正独立但共享 API 与配置的界面：

- 前台知识门户
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

## 2. 前台知识门户

### 2.1 目标

前台面向普通用户，负责：

- 浏览知识库
- 搜索概念
- 查看条目全文
- 直接跳入 Quartz 只读站点
- 提交材料和修订意见

### 2.2 页面结构

- `/`
  - 公共门户首页
  - 搜索作为主入口，搜索按钮居中
  - live suggestions 以悬浮下拉窗显示，不应挤压页面布局
  - 门户统计以横向卡片条展示，并位于最近更新上方
  - 最近更新区不再放二次提交按钮，避免与主搜索入口竞争注意力
- `/portal`
  - 兼容性重定向到 `/`
- `/search`
  - 全文搜索结果浏览
  - 支持标题、别名、摘要、正文命中
  - 支持摘要片段
- `/entries/{name}`
  - 独立条目详情页
  - 页头承担标题
  - 结构化 metadata / canonical sections / residual Markdown 分离显示
- `/submit`
  - 纯文本概念/经验提交
  - 文档上传
  - 默认匿名，但登录用户会被额外记录 `submitter_user_id`
- `/quartz/`
  - 直接进入 Quartz
  - 由 Sediment 负责 `exact -> .html -> /index.html -> 404.html` 解析
- `/portal/graph-view`
  - 兼容性入口
  - Quartz 已构建时重定向到 `/quartz/`
  - Quartz 未构建时显示 fallback 说明页
  - 意见反馈

### 2.3 前台功能要求

- 支持 live suggestion 下拉、debounce、键盘导航与“查看全部结果”
- 搜索建议弹层不应导致搜索按钮、统计区或最近更新发生布局位移
- 支持查看结构化条目详情，而不是 modal-only 渲染
- 支持查看 Markdown 正文渲染结果
- 浏览保持匿名
- 提交默认匿名；如携带有效 owner / committer session，则额外绑定真实 user identity
- 后端自动记录 IP
- 至少按 IP 做每分钟 1 次限流
- 主导航不出现后台入口；主题切换与语言切换位于 utility 区
- utility 区与一级导航必须形成清晰的视觉分区，不能混在同一排主功能中
- utility 控件固定在右上角，使用紧凑图标按钮而不是一级菜单样式
- 各页面大标题下不再放额外说明性段落，避免重复噪音
- `/submit` 的标签、按钮和占位提示必须完全走 locale 文案，不能残留单语言硬编码
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
- `/admin/overview`
  - 总览卡片
  - health 摘要
  - 只读问题概览
  - 最近活动与审计
- `/admin/kb`
  - Explore
  - buffered submissions
  - KB 级 tidy
  - health issue queue（只读浏览，真正的 tidy 只通过 KB 级 scope 发起）
  - 在线 Markdown 编辑
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
  - runtime / config / limits / Quartz 状态与构建

### 3.3 后台必须具备的能力

- 在线编辑正式条目
- 查看 health 结果并常驻刷新
- 查看未进入正式知识库的提交
- 以 KB scope 发起 tidy 任务，而不是针对单条目目标
- 审阅 Agent 生成的 patch
- 显示审计日志
- 显示系统状态、Quartz 状态、队列模式和限流配置
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
- 门户与后台共享基础 shell，但分别使用 portal/admin palette
- Quartz 继续作为独立静态站点托管，不把图谱重新发明到主壳里
- 重点优先保证“搜索、条目详情、提交、审核、KB-level tidy、用户/系统权限”这些链路完整可用

## 10. UI 视觉规范

- **极简科技风（年轻化）**：多用矩形，去除多余的圆角（`border-radius: 0`）。背景建议增加极其微弱的点阵/网格背景增强极客氛围。
- **去除“AI 味”**：避免过度使用模糊（blur）、高光渐变色、大面积微光发散等显得过于花哨且不写实的修饰效果。
- **动效微交互**：对所有交互元素（Button、Card、Input、Panel 等）加入干脆利落的微过渡动效（`transition`）。通过交互时的 `translate` 悬浮位移与元素微量外发光改变提供明确的即时操作反馈。
- **浅底盘 / 面板悬浮 (Subtle Plate Contrast)**：避免粗笨的直接线框。页面的视觉层级由轻微的底色差构成（例如采用浅灰 `bg` 为底层盘，纯白或深黑作为 `panel` 色），区域间仅以极淡的透明度线条（例如 `rgba(125,125,125, 0.15)`）勾勒，配合微小的弥散阴影提升边界感。用最隐忍克制的区块明暗差，传达“现代、优雅、极客”的高级感。
