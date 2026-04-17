# 当前设计：工作流边界

企业版 Sediment 把知识层维护拆成七种一等动作：

- 人工直接编辑
- submit
- ingest
- tidy
- version control
- explore
- health

这些动作围绕同一份白盒知识库协作，但不共享同一权限边界。

## 1. 人工直接编辑

人工编辑仍然是默认支持路径，不是例外情况。

- 可以直接修改 Markdown 条目
- 可以补充链接、修正表述、拆分或合并内容
- 可以通过本地 Git 工作区或管理后台在线编辑器完成修改

它的设计意图仍然是保证 Sediment 始终可接手、可迁移、可审阅。

但在企业环境中，人工直接编辑默认只面向 `committer` 和平台维护者开放，不等于所有用户都能直接改 canonical knowledge state。

## 2. Submit

submit 是企业部署新增的一等入口。

它负责把知识线索稳定送进系统，而不要求用户具备本地知识库访问能力。

submit 支持两类输入：

- 文本意见
- 文档上传

应该做的事：

- 记录提交者名字、时间、来源 IP 和原始内容
- 对内容做基础安全校验、限流和去重
- 把材料写入提交收件箱，而不是直接写入正式知识层

不应该做的事：

- 绕过审核直接改动知识库文件
- 把未审阅提交直接暴露给 `knowledge_ask`

## 3. Submission Inbox

提交收件箱是从“可贡献”到“可进入正式治理路径”的关键入口。

应该做的事：

- 对文本意见做人工查看、解决和恢复
- 对上传原件做下载、移除、放入 `ready to ingest`
- 为一组 ready 文档创建 ingest batch，并跳转到知识库管理页执行 ingest
- 把用户输入和正式 KB 写路径解耦

不应该做的事：

- 把收件箱做成第二个 Git 客户端
- 把所有状态都设计成复杂审批流

## 4. Ingest

ingest 的职责是把 ready to ingest 材料做成“足够好的首次提炼”，并在成功时直接落成 Git 提交。

在企业部署下，ingest 默认由服务托管的本地 Agent Runner 执行，而不是要求用户手工登录知识库主机运行本地 Agent；执行入口固定在知识库管理页。

应该做的事：

- 从材料中提炼 `concept`、`lesson`、`placeholder`
- 产出符合条目模型的 Markdown 草案
- 保留来源元数据
- 补充最小必要的知识链接
- 成功后自动生成 Git commit，并把 `commit_sha` 关联回 batch / job / inbox 历史

不应该做的事：

- 为了追求完美粒度而过度拆分
- 对整个知识库做全局重构
- 因为单次输入里提到很多名词，就强行扩图

## 5. Tidy

tidy 负责长期结构治理。

tidy 的核心执行者仍然是本地 Agent，而不是简单脚本；脚本负责发现问题和提供约束，Agent 负责推理、生成修复草案和结构提升建议。

在企业部署下，tidy 同样通过服务托管的 Agent Runner 执行：

- 管理台或定时任务提出 tidy 任务
- Agent Runner 在知识库所在工作区运行 skill
- 产出 patch、草案、原因说明和引用上下文
- 成功后直接自动生成 Git commit；如需撤销，则通过 Git revert 回退

应该做的事：

- 修复不合法条目
- 修复真实断链
- 提升高引用 placeholder
- 维护 `index.root.md` 与 `indexes/`
- 拆分、合并或重连索引入口

不应该做的事：

- 把 provenance 当成知识节点去扩图
- 为了形式整齐而改写大量事实内容
- 在无审核的情况下直接落地高风险重写

简化地说：ingest 负责“先落下来”，tidy 负责“长期变得更稳”。

## 6. Explore

explore 负责在当前正式知识层上回答问题，而不是回到原始材料重新做一次摄入。

应该做的事：

- 先从索引入口进入候选区域
- 优先使用正式条目作为强证据
- 必要时跨条目综合
- 明确返回 gaps 和 contradictions

不应该做的事：

- 把 placeholder 当作唯一证据
- 把来源名当成概念进行推理
- 用猜测填补证据缺口
- 读取缓冲区中尚未合并的提交作为组织共识

## 7. Health

health 负责输出稳定工作队列，而不是追求形式完美。

应该做的事：

- 报告条目结构硬错误
- 报告图谱断链、孤岛、缺口与污染
- 报告索引覆盖与负载问题
- 把问题输出成可供管理台消费的结构化队列
- 给 tidy 提供可执行的治理入口

不应该做的事：

- 自己直接篡改知识内容
- 为了追求零告警而抬高写作成本

## 8. Version Control

version control 是正式版本层，而不是 review 的附属能力。

应该做的事：

- 展示当前 Git 状态、分支、ahead / behind 和最近提交
- 允许 committer 为文件管理页产生的工作区修改填写理由并手工 commit
- 允许手工 push 当前已配置 upstream 的分支
- 为 ingest / tidy 生成的 Sediment 管理提交提供 Git revert 回退入口

不应该做的事：

- 在 UI 内实现 branch / merge / pull 等完整 Git 客户端能力
- 自动 push
- 把配置文件、状态目录等本地产物混进默认 tracked paths

## 9. 企业写路径边界

企业部署下的写路径应固定为：

1. 用户提交文本意见或上传原件到提交收件箱
2. `committer` 在收件箱内处理文本意见，或把文档放入 `ready to ingest`
3. `committer` 从知识库管理页触发 ingest / tidy
4. Agent Runner 生成草案或 patch，并直接写回知识层
5. ingest / tidy 成功后自动生成 Git commit
6. 如需撤销 ingest / tidy，则通过 Git revert 创建回退提交

只有本地专家操作、紧急修复或后台在线编辑等受控路径，才允许绕过 submit 直接进入人工编辑。

## 10. 接口边界

运行时接口应分成两类：

- MCP：给 Agent、自动化流程和 IDE 使用
- REST / HTTP：给知识库 Web 界面、管理后台和文件上传使用

其中读接口继续围绕当前知识库工作。

写接口一律围绕“收件箱、任务、Git 提交、回退”这些显式状态工作，不应隐式依赖另一套不可见操作。
