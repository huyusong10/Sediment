# 知识宇宙 v1 演进草案（Graph View Enhancement）

> 状态：in-progress
> 当前正式入口：见 [../README.md](../README.md)
> 本文目的：记录 `/portal/graph-view`（"知识宇宙"）从当前"小核心 + 近期事件局部"的沉浸图升级为"固定坐标、可浏览全量知识、可定位、可探索"的 v1 形态的设计选择与实施蓝图。
> 相关上游：[../current/web-surfaces.md](../current/web-surfaces.md) 的 `/portal/graph-view` 段、[tacit_knowledge_system_v5_insights_draft.md](tacit_knowledge_system_v5_insights_draft.md) "门户图二次优化判断"。
> 当前实现进度：已落地 `scene=home / full / universe / universe_focus`、热点 / 邻域 / 最短路径接口、Universe HUD、策略 / 过滤 / budget 切换、键盘映射、迷你地图、固定坐标与首页 `universe-lite` 牵引入口。

---

## 1. 这次演进要解决什么问题

当前知识宇宙已经完成两件事：

- 以 universe profile 表达"新知识正在迸发、凝聚"的形成感
- 通过 universe / universe-lite 两层视图同时承担首页预览和完整版浏览

但使用中暴露四个体验短板：

- **节点会乱跳和闪烁**：前端物理推进导致点击后整图抖动、偏向一侧、视觉不稳定
- **展开前后像两张图**：首页 hero 与图页完整版不是同一宇宙的不同层级
- **in-scene 无导航工具**：没有搜索、没有"跳到最新/未成形知识"、没有"探索"
- **空能力没有明确反馈**：当 KB 没有 tacit / cluster / hotspot 时，用户只会看到“按钮没反应”

v1 演进目标：在不破坏既有事件驱动数据管线、不污染 `admin-governance` 后台图的前提下，把 `/portal/graph-view` 升级为四件套 ——
**固定坐标 + 同图双层级 + 搜索定位 + 热点 / 探索**，并强化"新鲜 / 未成形 / 隐性"的视觉语言。

设计原则：

- 后端继续以"事件驱动投影"为语义源头，新增档位而非新建镜像
- 前端按模块拆分控制职责，主文件只做装配，保留现有 `__sedimentGraphApi` 探针
- 所有新文案走 `ui` 字典中英对照，不硬编码任何语言
- 改动要同步反馈到 `design/current/web-surfaces.md` 与本文件

---

## 2. 架构分层

| 层                  | 改动                                                                                                   |
| ------------------- | ------------------------------------------------------------------------------------------------------ |
| 后端 payload        | `graph_payload()` 新增 `scene=universe` / `universe_focus` 档位；节点补 `hotspot_score`、`cluster_id`、`last_event_at`、`maturity_estimate` |
| 后端路由            | 新增 `/api/portal/graph/hotspots`、`/api/portal/graph/neighborhood`、`/api/portal/graph/path`；复用现有 `/api/portal/search/suggest` |
| 前端图引擎          | 主文件 `frontend/graph/src/index.js` 只做装配；吸附、热点游标、探索策略、过滤、小径、键盘、迷你地图拆为同目录子模块 |
| UI 壳               | `portal-graph-body.html` 顶部新增"宇宙 HUD"（搜索、热点、探索、过滤芯片、设置齿轮、计数、状态行），右下加入迷你地图，左下改为固定信息卡 |
| 文案与多语言        | `web_ui.py::portal_graph_html` 的 `ui` 字典扩充所有新增键的中英对照                                      |

---

## 3. 固定坐标与镜头规则

- 门户 scene (`home / full / universe / universe_focus`) 统一复用 `_build_universe_graph()` 产出的稳定 `x / y / z`
- node payload 必须同时暴露 `fx / fy / fz`，并与 `x / y / z` 对齐，禁止 portal 前端重新开启力学布局
- 点击、搜索、热点、探索、后退都只允许改变 `cameraPosition()` 与 focus target，不能改变节点坐标
- portal 默认关闭 `autoRotate`、关闭 idle camera drift、关闭普通 link particles，仅保留 trail 与选中高亮
- 视角漫游必须支持中键平移；漫游时的平移不能被后台重心回拉偷偷抵消
- 星图布局要优先制造“浩瀚留白感”：宁可把节点做小、把 anchor 连线做淡，也不能把所有知识星球挤成一团发光云
- `admin-governance` 不属于本次固定坐标收敛范围，继续保留后台图自己的弱动效策略

## 4. 首页预览与完整版的同图双层级

- `scene=home` 不再是旧事件图，而是 `portal-universe-lite`
- `scene=home` 与 `scene=universe` 的重叠节点必须位置完全一致；首页只是精选子集，不允许出现“展开前后完全换了一个宇宙”
- featured 节点选择顺序：
  1. `hotspot_score` / forming candidate
  2. 最近形成、正在凝聚的节点
  3. 若 KB 没有上述对象，则按 degree + energy 回退为推荐节点
- 首页点击精选节点后进入 `/portal/graph-view?focus=<node-id>`，图页首屏使用 `scene=universe_focus`
- `scene=full` 只保留兼容语义，但行为与固定坐标 universe 保持一致

### 节点规模三档可切换

| 档位         | 总节点上限 | L1 邻域上限 | 备注                                       |
| ------------ | ---------- | ----------- | ------------------------------------------ |
| conservative | 800        | 400         | 兜底档，MBP M1 稳 60 fps                   |
| **medium**   | **1500**   | **800**     | **首发默认**；关闭默认 link particles      |
| aggressive   | 3000       | 1500        | 需要 InstancedMesh 重写节点渲染（Feature Flag 隐藏） |

后端 `graph_payload()` 接受 `?scene=universe&budget=<档位>`；前端 HUD "设置齿轮"提供切换，写入 `localStorage`。`aggressive` 档在首发里保留入口但不开放，等 shader 重写到位再放开。

**渲染侧优化**：默认关闭 link particles，只给 trail 高亮保留；首页和 portal static scene 关闭 burst/cloud 粒子；label 仅在近景、悬停或选中时增强。
进一步收敛：

- `belongs_to_cluster` 连线在 portal static scene 下需要显著弱化，避免中心星爆线团
- cluster anchor 与普通知识星球的尺寸差必须收敛，避免 anchor 把视觉重心压成“巨型主星”

**感知层**：HUD 显示 `可见 X / 总数 Y`；左下信息卡默认显示操作指南，选中节点后显示节点摘要。

---

## 5. 搜索定位

复用 `/api/portal/search/suggest`。新增前端状态机：

```
idle → searching → awaitingFetch → flying → focused
```

数据流：

1. 输入 `q` → `search/suggest` 防抖 160ms → 下拉候选（显示 label + 所属 cluster）
2. 选中候选：
   - 节点 id 已在 `nodeIds()` 内：`selectNodeById(id)` + 现有 950ms 相机飞行 + Sticky Focus
   - 否则：拉 `/api/portal/graph?focus=<id>&scene=universe_focus` → 与当前图合并 → 再飞行
3. 飞行结束后目标节点 ring + 脉冲 1.5 秒，给出"你到了"的反馈
4. 最近 10 次 focus 存 `sessionStorage`，HUD 提供"后退"

复用位点：`search_kb_suggestions()` 已在 `src/sediment/platform_services.py`。

---

## 6. 热点队列（新知识 + 隐性）

### 后端排序公式

新端点 `/api/portal/graph/hotspots?kind=recent|tacit|all`，后端 helper `rank_hotspots()` 计算：

```
hotspot_score =
      0.35 · recentness
    + 0.25 · burst_level
    + 0.20 · (1 - maturity_estimate)   # 越不成形越靠前
    + 0.10 · formation_stage_level
    + 0.10 · event_intensity

# 隐性加成：node_type=insight_proposal 且 stability<0.3 → +0.15
```

返回 `[{ id, reason_code, reason_label_zh, reason_label_en, score }]`，最多 24 条。

### 前端游标

维护 `{ queue, cursor }`。"找到热点"按钮每次点击 `cursor = (cursor + 1) % queue.length`，然后 `selectNodeById(queue[cursor].id)`；若目标不在当前图内先走"搜索定位"数据流。
队列每 60 秒或每次 focus sheet 关闭后静默刷新；刷新后按 id 对齐旧游标位置，保持幂等。

当当前 KB 没有真实 forming hotspot 时，接口 `mode` 必须显式标注为 `recommended`，UI 状态区同步说明"热点按钮当前退化为推荐节点"。

---

## 7. 探索规律（三种策略，芯片切换）

**默认 = 沿边漫游**（`edge_walk`）；HUD 策略芯片允许切换。三种策略：

| 策略                 | 权重公式                                         | 体验        |
| -------------------- | ------------------------------------------------ | ----------- |
| **沿边漫游（默认）** | 从当前 focus 按 `edge.activation` 加权走 k=1 步   | 叙事连贯    |
| 未访问优先           | `(1 - visited[id]) · energy`                     | 覆盖率最高  |
| 跨簇轮换             | `cluster_id` round-robin + cluster 内按 energy   | 主题多样    |

前端 `explore-strategy.js` 暴露统一的 `pickNext(state) → nodeId`。
已访问记录走 `localStorage`（每个 KB 独立 key），避免跨知识库污染。
冷启动（尚无 focus）时，沿边漫游降级为"随机挑一个 energy 较高的非 `cluster_anchor` 节点"。

---

## 8. 额外创意（首发范围）

五项全部纳入首发，先做 S 难度再做 M 难度；时间回放推迟：

| 创意          | 描述                                                             | 难度 | 首发 |
| ------------- | ---------------------------------------------------------------- | ---- | ---- |
| 键盘导航      | `/` 搜索、`J/K` 热点前后、`R` 探索、`Esc` 取消焦点                 | S    | ✅   |
| 主题过滤芯片  | 按 `node_type` + `formation_stage` 客户端筛选                    | S    | ✅   |
| 呼吸脉冲模式  | tacit 节点（`insight_proposal` 或 `formation_stage=condensing`）shader 低频闪烁 | S    | ✅   |
| 迷你地图      | 右下 200×200 Canvas 2D 投影 + 当前 frustum 矩形                   | M    | ✅   |
| 知识小径      | 任意两节点间 BFS 最短路径高亮（服务端 `/api/portal/graph/path`）   | M    | ✅   |
| 时间回放滑杆  | 按 `created_at` 过滤 + 脉冲复演形成感                             | L    | ⏭ 后续 |

补充收口：

- 图页删除 `Open Quartz`
- 底部中央漂浮提示并入左下固定信息卡
- `tacit / cluster / hotspot` 在无对象时保留控件但 disabled，并在状态区说明原因

---

## 9. 已确认的决策

1. **探索策略默认** = 沿边漫游（`edge_walk`）；三策略 HUD 芯片可切换
2. **首发加分项** = 键盘导航 + 主题过滤芯片 + 呼吸脉冲 + 迷你地图 + 知识小径；时间回放滑杆推迟
3. **节点规模** = 默认 `medium`（≤1500），HUD 设置齿轮内提供 `conservative / medium / aggressive` 切换；`aggressive` 首发走 feature flag 隐藏，待 InstancedMesh 重写就绪后开放
4. **吸附力** = A（重心回拉）+ C（Sticky Focus）默认启用；B（Elastic Frustum）在 `scene=universe` 档位下追加启用

---

## 10. 关键文件清单（按优先级）

> 以项目根 `Sediment/` 为基准的相对路径。

1. `src/sediment/platform_services.py`
   - `graph_payload()`：新增 `scene=universe` / `universe_focus` 分支，接受 `budget` 参数
   - 保留既有 BFS focus 扩展
   - 新 helper：`rank_hotspots()`、`graph_neighborhood_payload()`、`shortest_graph_path()`
2. `src/sediment/server.py`
   - `_api_portal_graph` 支持 `scene` / `budget` 参数
   - 新路由：`/api/portal/graph/hotspots`、`/api/portal/graph/neighborhood`、`/api/portal/graph/path?from=&to=`
3. `frontend/graph/src/index.js`
   - 常量区扩充：`ROLE_COLORS` 增 `tacit_pulse`；新增 `HUD_STRINGS`、`STRATEGY_IDS = ["edge_walk", "unvisited", "cluster_round_robin"]`、`BUDGET_PRESETS = { conservative, medium, aggressive }`
   - `styleForceGraph()` 接入 `installCameraAnchor()`
   - `animateGraph()` 增加 LOD 门限、sticky focus、tacit 呼吸 shader uniform
   - `mount3DGraph()` 装配 HUD、搜索、热点、探索、过滤、键盘、迷你地图
   - 新增同目录子模块：
     - `camera-anchor.js`（吸附力 A + B + C；B 仅 universe 启用）
     - `hotspot-cursor.js`（热点队列游标）
     - `explore-strategy.js`（三策略，默认 `edge_walk`）
     - `filter-chips.js`（主题过滤，客户端）
     - `mini-map.js`（2D Canvas 投影 + frustum 框）
     - `knowledge-trail.js`（最短路径高亮）
     - `keyboard.js`（`/ J K R Esc` 映射）
     - `hud.js`（统一控件装配）
4. `src/sediment/templates/portal-graph-body.html`
   - 顶部 `#portal-graph-hud`：搜索、热点、探索、策略芯片、过滤芯片、设置齿轮、计数、状态行
   - 右下 `#portal-graph-minimap`：200×200 canvas 容器
   - 左下 `#portal-graph-info-card`：操作指南 / 节点摘要 / 不可用原因
5. `src/sediment/web_ui.py`
   - `portal_graph_html` `ui` 字典新增（全部中英对照）：
     - `hud_search_placeholder / hud_hotspot / hud_explore`
     - `hud_strategy_edge_walk / hud_strategy_unvisited / hud_strategy_cluster`
     - `hud_filter_all / hud_filter_tacit / hud_filter_canonical / hud_filter_cluster`
     - `hud_count_template`、`hud_settings_title`、`hud_budget_*`
     - `hud_keyboard_hint`、`hud_trail_from / hud_trail_to`
   - `page_data` 增加：`hotspotsApi`、`neighborhoodApi`、`searchSuggestApi`、`pathApi`、`defaultStrategy: "edge_walk"`、`defaultBudget: "medium"`
6. `tests/test_web_browser_e2e.py`（追加）
   - `test_portal_graph_search_focuses_offscreen_node`
   - `test_portal_graph_hotspot_queue_cycles`
   - `test_portal_graph_explore_defaults_to_edge_walk`
   - `test_portal_graph_camera_sticky_focus`
   - `test_portal_graph_filter_chip_hides_canonical_nodes`
   - `test_portal_graph_keyboard_slash_focuses_search`
   - `test_portal_graph_minimap_reflects_viewport`
   - `test_portal_graph_trail_highlights_shortest_path`
   - 既有 `test_portal_graph_page_renders_dynamic_insights_surface` 微调，改为断言 `portal-graph-info-card` / `portal-graph-status` 而不是旧 `portal-graph-hint`
7. `tests/`（新增单元）
   - `test_graph_hotspot_ranking.py`
   - `test_graph_neighborhood_endpoint.py`
   - `test_graph_shortest_path.py`
8. `design/current/web-surfaces.md`
   - `/portal/graph-view` 段落重写：universe LOD、吸附力三机制、HUD 控件契约、键盘映射
9. `design/evolution/tacit_knowledge_system_v5_insights_draft.md`
   - 正式化字段：`hotspot_score`、`maturity_estimate`、`cluster_id`、`tacit_pulse`
10. `design/current/graph-view-interaction.md`（新增）
    - 契约文档：状态机、策略芯片、键盘映射、budget 档位、HUD 控件对外事件

---

## 11. 验证方案

### 单元层

- `pytest tests/test_graph_hotspot_ranking.py`：给定样例节点集合，验证 `hotspot_score` 公式对 `recentness`、`stability`、`insight_proposal` 的单调响应
- `pytest tests/test_graph_neighborhood_endpoint.py`：命中 / 未命中 / 越界 depth 的返回契约
- `pytest tests/test_graph_shortest_path.py`：连通 / 不连通 / 同节点的路径返回契约

### 端到端（Playwright）

- `test_portal_graph_search_focuses_offscreen_node`：搜索一个不在 L0 视野中的节点，断言拉取邻域、节点加入 `nodeIds()`、`portal-graph-focus` 面板可见
- `test_portal_graph_hotspot_queue_cycles`：连续点击热点按钮 N 次，断言选中节点 id 不重复且循环
- `test_portal_graph_explore_defaults_to_edge_walk`：首次进入页面 HUD 策略芯片默认选中 `edge_walk`，点击探索后选中节点与当前 focus 之间存在直接 edge
- `test_portal_graph_camera_sticky_focus`：聚焦后拖动相机，断言 `camera.target` 与 focus 节点距离不超过阈值（通过 `__sedimentGraphApi.debugCameraState()` 探针）
- `test_portal_graph_filter_chip_hides_canonical_nodes`：勾选"仅 tacit"芯片后，`nodeIds()` 不含 `canonical_entry` 类节点
- `test_portal_graph_keyboard_slash_focuses_search`：按 `/` 键后搜索框获得焦点；按 `Esc` 解除 sticky focus
- `test_portal_graph_minimap_reflects_viewport`：迷你地图 canvas 有内容绘制，且包含 `data-testid="portal-graph-minimap-frustum"` 矩形元素
- `test_portal_graph_trail_highlights_shortest_path`：选择 A→B 两个节点，触发小径后图上高亮边数等于最短路径长度
- 既有 `test_portal_graph_page_renders_dynamic_insights_surface` 微调：改为断言 `portal-graph-info-card`、`portal-graph-status` 与“选中前后坐标不漂移”

### 手测清单

- `npm run -w frontend/graph build && python -m sediment.cli serve --kb tmp/demo-kb`
- `/portal/graph-view?lang=zh` 与 `?lang=en` 双语文案
- 三档 budget 切换下的帧率（目标 medium ≥ 45 fps on MBP M1）
- 键盘：`/`、`J/K`、`R`、`Esc` 全部命中
- 固定坐标手感：聚焦前后抽样节点的 `x / y / z` 不发生漂移；镜头切换只改变 target 与距离

---

## 12. 后续（Non-goal of v1）

- 时间回放滑杆（按 `created_at` 过滤 + 脉冲复演）
- `aggressive` 档位（InstancedMesh + 低精度 shader 节点渲染重写）
- 与 Quartz 静态关系图的跨站点跳转联动
- 用户级"书签 / 收藏"与多人协同注释

这些放到 v2 草案或后续专题讨论。
