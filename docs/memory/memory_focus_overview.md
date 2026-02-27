# Agent Memory Focus Overview（教学聚焦版）

这份文档只回答 4 个问题：

1. memory 到底在管什么  
2. 短期记忆和长期记忆怎么分工  
3. 主流 code agent 现在怎么做  
4. 我们这个教学 repo 下一步该怎么落地

---

## 1. 一句话总览

一个 memory 系统本质上是两层协同：

- 短期记忆：保证当前任务跑得动、跑得完
- 长期记忆：保证跨会话信息不丢、可复用

工程里常见闭环：

1. 当前回合在短期上下文里推理与执行  
2. 关键内容沉淀到长期层  
3. 新任务再从长期层检索回注到短期层

---

## 2. 短期 vs 长期（最关键）

| 维度 | 短期记忆（Short-term） | 长期记忆（Long-term） |
|---|---|---|
| 主要对象 | 当前对话、工具结果、任务状态、临时摘要 | 可复用知识：规则、偏好、事实、经历、方法 |
| 时间范围 | thread/session 内 | 跨 session / 跨任务 |
| 主要目标 | 控制上下文窗口，保持当前任务连续性 | 让系统“下次还能记得且可检索” |
| 核心操作 | 裁剪、压缩、分块、回填、重试 | 抽取、存储、检索、更新、冲突消解、逐出 |
| 典型位置 | agent loop 内部 | 文件/DB/向量库/图谱/知识库 |

补充：

- “落盘”是短期到长期的桥接动作，不等于短期记忆本体。
- 默认 `flush` 更接近持久化动作；只有加结构化约束时才更像“抽取”。

---

## 3. 长期记忆的 5 类对象（教学用）

1. `Policy`（规则）：必须遵守的约束  
2. `Profile`（画像）：用户偏好  
3. `Fact`（事实）：稳定事实  
4. `Episode`（情节）：发生过什么  
5. `Procedure`（程序）：怎么做更好

可做轻度合并（便于工程实现）：

- 规则层：`Policy + Profile`
- 知识层：`Fact + Episode`
- 技能层：`Procedure`

---

## 4. 主流 code agent 的现实做法

| 系统 | 短期记忆怎么维护 | 长期记忆怎么维护 |
|---|---|---|
| Claude Code / OpenCode / Codex（这类 code agent） | 主要在 loop 中做上下文管理与压缩 | 主要依赖用户维护规则文件（如 `CLAUDE.md` / `AGENTS.md`），自动抽取相对少 |
| Cursor | 会话层短期管理同样存在 | 在规则文件之外，提供一定自动 memory 能力（仓库作用域） |
| OpenClaw | loop 内有 compaction、flush、检索回填 | `MEMORY.md` + `memory/*.md` + memory tools；默认更偏“落盘+检索”，非强结构化抽取 |
| Claude-mem | 依赖 Claude Code 会话流，侧重 observation 压缩与回填 | 通过 MCP 的 search/get_observations 按需召回，不做全量注入 |
| OpenViking | 以分层上下文加载控制短期窗口膨胀 | 把 memory/resources/skills 统一成路径空间（`viking://`），强调可观测检索轨迹 |
| 独立 memory 组件（Mem0/Supermemory/Zep 等） | 通常由宿主 agent 负责短期层 | 更聚焦长期层自动治理：抽取、更新、逐出、冲突处理、检索注入 |

阶段性结论：

- 现在主流 code agent 里，“长期记忆用户手工维护”仍是主路径。
- 自动化长期记忆在增长，但整体仍偏增强项而不是唯一主干。

---

## 5. 不同类型 Agent 应该重点存什么

| Agent 类型/形态 | 长期记忆优先对象 | 短期记忆优先能力 | 不该优先投入的点 |
|---|---|---|---|
| Gateway/Hub Deployment（架构形态） | Policy、Fact、Episode、部分 Procedure（多会话共享） | 会话隔离、队列调度、compaction/flush、按需检索回填 | 过早做超细粒度画像建模（先保证稳定性与隔离） |
| Personal General Assistant（个人通用助手） | Profile、Policy、Fact、Episode（个人连续偏好与历史） | 多任务切换、对话连续性、日程/任务上下文拼接 | 只做规则文件而忽略自动更新；或无边界地全量记忆 |
| Code Assistant（cc/oc/codex/cursor） | Policy、Profile、项目 Fact、少量 Procedure | 上下文压缩、工具结果管理、回合状态可观测 | 过重的自动知识图谱与复杂记忆本体 |
| Workflow Agent（自动化流程） | Procedure、Fact、任务模板、失败经验 | 步骤状态机、重试点、断点续跑上下文 | 过细的人格画像记忆 |
| Research Agent（检索/分析） | Fact、Citation、Episode（研究轨迹） | 大上下文分段摘要、证据对齐 | 仅靠规则文件而无证据索引 |
| Support/CRM Agent | Profile、Fact、Policy（合规） | 会话连续性、意图状态、工单上下文 | 忽略隐私分级的“全量长期记忆” |
| Autonomous Long-running Agent | Procedure、Episode、Fact、Policy | 长窗口压缩、计划状态、异常恢复 | 只靠手工规则文件，不做自动治理 |

一句话：

- 代码助手优先“规则与项目事实”。
- 个人通用助手优先“用户画像连续性 + 稳定事实更新 + 隐私边界”。
- 网关/中枢型部署优先“多会话隔离 + 共享事实召回 + 稳定压缩”。
- 流程代理优先“程序记忆与失败复盘”。
- 服务代理优先“用户画像与事实一致性”。

---

## 6. 对本 repo 的落地建议（聚焦版）

建议分三步，不要一口气做重系统：

1. `v5`：先把短期记忆做扎实  
目标：上下文稳定、可观测、可解释  
能力：压缩策略、回合状态、工具结果管理、可视化日志

2. `v5.x`：再做轻量长期记忆  
目标：先可用再智能  
能力：规则层（Policy/Profile）+ 基础事实层（Fact）的写入与检索

3. `v5.x+`：最后再上自动治理  
目标：减少污染，提升复用  
能力：抽取质量控制、冲突消解、逐出策略、评测回归

---

## 7. 一句话结论（可直接讲给学生）

“短期记忆解决当前能不能跑完，长期记忆解决下次还能不能记得；  
当前 code agent 以规则文件长期记忆为主，独立 memory 组件才是长期自动治理的主战场。”
