# 当前设计：Graph View 交互契约

## 1. 模块职责

- `/portal/graph-view` 提供“可浏览全量知识 + 可定位 + 可探索”的 universe 图谱入口。
- 门户图谱使用后端稳定坐标作为唯一位置源；节点不再在前端重新跑物理布局。
- 页面重点是浏览、定位、探索与知识小径，不承担后台治理动作。
- 图页默认要呈现“稀疏星图”而不是团块；节点尺寸、光晕和 anchor 连线都必须服从“可辨认、可留白”的视觉优先级。

## 2. HUD 契约

| 区域 | 对外能力 |
| --- | --- |
| 搜索框 | 调用 `/api/portal/search/suggest`，支持输入防抖、候选选择与键盘确认 |
| 热点按钮 | 轮询 `/api/portal/graph/hotspots` 返回的热点队列，按游标向前 / 向后切换 |
| 探索按钮 | 按当前策略在已加载图数据中选择下一个节点 |
| 策略芯片 | 切换 `edge_walk / unvisited / cluster_round_robin` |
| 过滤芯片 | 切换 `all / tacit / canonical / cluster` 客户端过滤；无对象时必须 disabled |
| budget 设置 | 切换 `conservative / medium / aggressive`，并重新拉取 `scene=universe` payload |
| 计数 | 显示 `visible / total`，其中 total 来自 payload `stats.total_*` |
| 状态行 | 显示热点退化、无 tacit、无问题簇等固定说明，不能依赖 silent no-op |
| 左下信息卡 | 默认显示操作指南；选中节点后显示节点标题、类型/状态与一句摘要 |

补充约束：

- HUD 必须停靠在共享顶部骨架中，不能把按钮拆成多个漂浮角标。
- 搜索候选面板必须锚定搜索输入框，不得推动其他 HUD 控件重新排版。
- 视角漫游必须支持中键平移；portal 固定坐标 scene 中，平移只改变相机 target，不得触发节点重排。

## 3. 状态机

搜索定位状态机：

`idle -> searching -> awaiting_fetch -> flying -> focused`

知识小径状态机：

`empty -> start_selected -> complete -> highlighted`

热点游标状态机：

`empty -> ready -> cycling`

## 4. 键盘映射

| 按键 | 行为 |
| --- | --- |
| `/` | 聚焦搜索框 |
| `J` | 上一个热点 |
| `K` | 下一个热点 |
| `R` | 按当前策略执行一次探索 |
| `Esc` | 清除当前焦点 |

## 5. Scene / Budget 契约

| scene | 用途 |
| --- | --- |
| `home` | 首页 `universe-lite` 预览；取自 full universe 的精选子集，并复用相同坐标 |
| `full` | 兼容旧入口的预览档位；行为与固定坐标 universe 语义对齐 |
| `universe` | 全量浏览档位；固定坐标，只允许相机飞行 |
| `universe_focus` | 搜索 / 首页牵引 / 热点 / 邻域加载后的聚焦档位 |

| budget | 约束 |
| --- | --- |
| `conservative` | 面向较小机器的保守节点预算 |
| `medium` | 图页默认预算 |
| `aggressive` | 保留为实验预算，可在 UI 中隐藏 |

## 6. 服务端接口

- `/api/portal/graph?scene=universe&budget=...`
  - 返回 universe graph payload
- `/portal/graph-view?focus=<node-id>`
  - 页面入口 query；首屏用 `scene=universe_focus` 初始化并把镜头落到该节点
- `/api/portal/graph/hotspots?kind=...`
  - 返回 `{ kind, mode, items[] }`；`mode=recommended` 表示当前退化为推荐节点
- `/api/portal/graph/neighborhood?id=...&depth=...`
  - 返回与 graph payload 同 shape 的邻域子图
- `/api/portal/graph/path?from=...&to=...`
  - 返回最短路径结果，包含 `node_ids`、`nodes` 与 `edges`

## 7. Debug / 探针

- 图容器继续暴露 `__sedimentGraphApi`
- 至少保留：
  - `selectNodeById(id)`
  - `clearSelection()`
  - `nodeIds()`
  - `debugCameraState()`
  - `trailEdgeIds()`
