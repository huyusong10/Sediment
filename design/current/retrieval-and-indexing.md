# 当前设计：检索与索引

Sediment 当前采用“索引优先，但允许自由探索”的检索组织方式。

## 1. 索引文件布局

知识库中的索引分两层：

- `index.root.md`：全局入口
- `indexes/index.*.md`：分段索引

其中：

- root index 负责把查询引导到合适的主题段
- segment index 负责把查询引导到具体 `concept` / `lesson`
- 索引是导航层，不复制正式条目正文

## 2. Index Contract

分段索引建议使用以下 frontmatter：

```yaml
kind: index
segment: <name>
last_tidied_at: YYYY-MM-DD
entry_count: <int>
estimated_tokens: <int>
```

当前设计中的约束：

- `index.root.md` 应存在
- segment index 应位于 `indexes/`
- index 可以链接正式条目，也可以链接其他 index
- index 不应把 placeholder 当作正式入口

## 3. 检索路径

默认路径是：

1. 从 `index.root.md` 选择候选分段
2. 进入 `indexes/` 中的候选索引
3. 命中相关 `concept` / `lesson`
4. 必要时再跟随 `Related` 或全文搜索补充上下文

这意味着 index 是默认起点，但不是唯一通路。真正的目标是提高入口稳定性，而不是限制 LLM 的上限。

## 4. 为什么不用目录分类当主导航

正式条目仍然适合平铺存放，而不是强制按目录 taxonomy 归类。

原因：

- 路径更稳定，重命名成本更低
- 目录分类和知识关系是两回事
- 索引文件更适合承载“问题入口”，而不是让目录去表达领域语义

## 5. 索引重构触发条件

当前默认阈值为：

- `max_entries = 120`
- `max_tokens = 8000`

当某个索引超过任一阈值时，应进入 tidy 的重构队列。

典型动作包括：

- 拆分过大的索引
- 合并低密度且高度重叠的索引
- 修复错误链接
- 把未被任何索引覆盖的正式条目纳入入口网络

## 6. 索引健康的关键判断

一组好的索引应满足：

- root index 存在
- 正式条目能被至少一个索引覆盖
- 索引不指向缺失目标或 placeholder
- 分段规模不过载
- 入口划分服务于检索可达性，而不是形式上的分类整齐

## 7. 当前不引入 cards

当前设计不单独维护 `cards/` 目录。

理由：

- `concept` 条目本身已经承担了卡片角色
- 摘要层和正文层双写，容易产生漂移
- 现阶段更值得优先稳定的是索引网络，而不是增加第二套知识实体
