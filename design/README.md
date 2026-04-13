# Sediment 设计文档

Sediment 的设计文档按三层组织：

- 核心精神：[core-principles.md](core-principles.md)
- 当前设计：
  - [current/overview.md](current/overview.md)
  - [current/entry-model.md](current/entry-model.md)
  - [current/workflows.md](current/workflows.md)
  - [current/retrieval-and-indexing.md](current/retrieval-and-indexing.md)
  - [current/validation-and-health.md](current/validation-and-health.md)
  - [current/enterprise-governance.md](current/enterprise-governance.md)
  - [current/platform-architecture.md](current/platform-architecture.md)
  - [current/interfaces-and-review-flow.md](current/interfaces-and-review-flow.md)
  - [current/web-surfaces.md](current/web-surfaces.md)
  - [current/delivery-roadmap.md](current/delivery-roadmap.md)
- 演进记录：[evolution/README.md](evolution/README.md)

## 为什么这样拆

- 核心精神应该稳定，不应跟着每次结构调整一起漂移
- 具体设计应该按关注点拆开，便于局部修改、评审和替换
- 企业部署新增的平台层，应和知识层设计分开描述
- 版本文档应该保留，但只负责说明“为什么演进”，不再充当唯一入口

## 建议阅读顺序

1. 先看 [core-principles.md](core-principles.md)
2. 再看 [current/overview.md](current/overview.md)
3. 看 [current/workflows.md](current/workflows.md) 和 [current/enterprise-governance.md](current/enterprise-governance.md)，理解知识流和审核责任
4. 看 [current/platform-architecture.md](current/platform-architecture.md)、[current/interfaces-and-review-flow.md](current/interfaces-and-review-flow.md)、[current/web-surfaces.md](current/web-surfaces.md)，理解企业平台形态
5. 需要落实施工时，看 [current/delivery-roadmap.md](current/delivery-roadmap.md)
6. 需要追溯设计取舍时，再看 [evolution/README.md](evolution/README.md)

## 文档归类约定

- 如果某个结论在多个版本中都不应变化，放入核心精神
- 如果某个结论描述的是当前系统如何工作，放入 `current/`
- 如果某个文档主要解释“为什么从 A 走到 B”，放入 `evolution/`
