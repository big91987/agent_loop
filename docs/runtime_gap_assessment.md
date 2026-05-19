# 当前 Agent Runtime Gap 盘点

## 目的

这份文档用于回答一个很具体的问题：

- 以“通用 agent runtime”为目标，
- 参考 Claude Code 这类成熟系统的优秀工程实践，
- 我们当前 repo 到底已经具备了什么，
- 哪些只是部分具备，
- 哪些还基本缺失。

这里的评估不是以“coding agent”作为标准，而是以我们后续想要的更通用运行时目标作为标准：

- 场景中立
- 能力解耦
- 长短记忆分离
- 多角色可扩展
- 治理层正式化
- 会话连续性清晰

---

## 评估维度

本轮按下面 8 个维度看：

1. 核心 runtime 主循环
2. 短期上下文治理
3. 会话连续性
4. 长期记忆 runtime
5. tool / skill / MCP 一体化
6. 治理层
7. 多 loop / 多角色模型
8. 观测与失败恢复

状态分三档：

- `已有`：已经形成比较明确的实现主线
- `部分缺失`：已经有雏形，但抽象、边界或稳定性还不够
- `完全缺失`：还没有形成正式层或缺少主线设计

---

## 总览表

| 维度 | 当前状态 | 结论 |
|---|---|---|
| 核心 runtime 主循环 | `部分缺失` | 已有可运行 loop，但更像增强版线性循环，尚未形成更成熟的 runtime kernel |
| 短期上下文治理 | `部分缺失` | 已有 compaction/short memory 机制，但距离多阶段 context management 还有明显差距 |
| 会话连续性 | `部分缺失` | 已有 session/workspace/restore 基础，但 transcript、resume、compact boundary 语义不完整 |
| 长期记忆 runtime | `已有` | `v6.3` 已形成 memory runtime + adapter/backend 主线，是当前相对最成型的一块 |
| tool / skill / MCP 一体化 | `部分缺失` | 三者都已有，但 runtime 级统一抽象仍不够完整 |
| 治理层 | `完全缺失` | 有零散策略与权限判断，但还没有正式治理层 |
| 多 loop / 多角色模型 | `部分缺失` | 已有初步意识和一些雏形，但还未形成正式可配置模型 |
| 观测与失败恢复 | `完全缺失` | 有基础日志和调试输出，但缺少正式 tracing、failure taxonomy、recovery framework |

---

## 1. 核心 runtime 主循环

### 当前状态
`部分缺失`

### 我们已经有的

- 多版本 loop 演进主线（`v1` 到 `v6.3`）
- turn-based agent loop
- 工具调用闭环
- MCP 接入
- skills 注入
- memory passive/active 双通道
- workspace / session 概念

### 还缺什么

- 正式的 runtime kernel 抽象
- 更清晰的 loop 生命周期阶段
- continuation / retry / recovery 正式语义
- 更细粒度状态机
- 更统一的事件模型

### 判断

我们已经有“能跑、可演进的 loop”，但还没有真正形成一个：

- 清晰分层
- 可重入
- 可承载多种 loop 变体

的通用 runtime kernel。

### 结论

这块不是从零开始，但也还没有成熟到能承接后续所有通用场景。  
所以应视为 `部分缺失`，并且是后续最核心的补强点之一。

---

## 2. 短期上下文治理

### 当前状态
`部分缺失`

### 我们已经有的

- `v6.1` 短期记忆/短期压缩思路
- working / raw message 双轨
- token/context 监控
- 在长会话里做一定的上下文裁剪

### 还缺什么

- 多阶段 compaction
- compact boundary 正式语义
- active context / full history / summary 的正式关系
- reactive compact
- “压缩失败后继续跑”的恢复路径
- session memory 驱动的压缩机制

### 判断

我们已经意识到短期上下文治理是正式问题，而不是简单拼 prompt。  
但离 Claude Code 那种“分层 context management”还有明显距离。

### 结论

这块属于 `部分缺失`，且优先级非常高。

---

## 3. 会话连续性

### 当前状态
`部分缺失`

### 我们已经有的

- session 持久化
- restore 基础
- workspace 隔离
- 标题 / summary 这类轻量会话信息

### 还缺什么

- transcript 作为正式层
- resume 语义正式化
- compact 后恢复点语义
- session summary 与 active context 的协同机制
- 会话边界、压缩边界、恢复边界之间的统一定义

### 判断

我们已经有 session 概念，但“会话连续性”还没有形成一整套设计。  
目前更像基础持久化能力，而不是成熟 continuity system。

### 结论

这块是 `部分缺失`。

---

## 4. 长期记忆 runtime

### 当前状态
`已有`

### 我们已经有的

- `v6.3` memory runtime
- passive retrieve / passive write
- active `mem_get / mem_set / mem_update / mem_delete`
- backend / adapter 抽象
- 已接入并验证多个真实 memory system：
  - `Mem0`
  - `SimpleMem`
  - `EverMemOS`
  - `OpenViking`

### 仍然不足的地方

- 写入/检索事件协议还能继续收敛
- 与 loop 生命周期的整合还能更正式
- 主动/被动写冲突治理还可再加强
- 长期记忆对象模型还没完全定型

### 判断

这是我们当前最成型的一条主线，已经不是概念验证，而是形成了：

- runtime
- adapter
- backend
- 实测验证

### 结论

这块可以视为 `已有`。  
后续重点是加强，而不是从头补课。

---

## 5. tool / skill / MCP 一体化

### 当前状态
`部分缺失`

### 我们已经有的

- tools
- MCP
- skills
- memory tools
- 不同版本里逐步增强的能力注入方式

### 还缺什么

- 正式统一的 capability runtime
- 工具、技能、MCP、memory 的统一生命周期
- 更统一的调度与事件语义
- 能力发现、能力描述、能力选择的正式层

### 判断

这条方向是对的，而且我们已经比很多简单 loop 走得更远。  
但目前仍然有点像：

- 多套能力并存
- 还没有完全汇总成一个统一 runtime

### 结论

应视为 `部分缺失`。

---

## 6. 治理层

### 当前状态
`完全缺失`

### 我们已经有的

- 一些零散策略
- 一些 memory policy
- 某些工具/流程里的局部约束

### 真正缺的是什么

- 正式的 `Governance Layer`
- permissions 正式化
- policy limits 正式化
- resource/path validation 正式化
- hooks 作为治理机制的正式位置
- denial / audit / enforcement 语义

### 判断

现在这块不能算“部分有了”，因为还没有抽象成正式层。  
它更多是散落在不同逻辑里的局部判断。

### 结论

这块应明确视为 `完全缺失`。

---

## 7. 多 loop / 多角色模型

### 当前状态
`部分缺失`

### 我们已经有的

- 已经明确意识到主 loop 不应该是唯一中心
- 已经开始讨论：
  - main loop
  - worker loop
  - background loop
  - memory loop
  - planner loop
- 在 memory runtime、service 形态、OpenClaw / Claude Code 对比中，已经有架构判断

### 还缺什么

- 正式的角色模型
- 正式的 loop type 定义
- 共享 kernel / 异构 loop 的实现框架
- 多角色协同的协议与状态模型

### 判断

这块我们已经形成了清晰的认知，但实现层仍然较早期。  
所以不算完全缺失，但远未成熟。

### 结论

应视为 `部分缺失`。

---

## 8. 观测与失败恢复

### 当前状态
`完全缺失`

### 我们已经有的

- 基础日志
- 一些调试输出
- token/cost 的基础统计
- memory backend 验证输出

### 真正缺的是什么

- tracing
- runtime event timeline
- failure taxonomy
- prompt-too-long / retry / compact-recovery 正式机制
- denial / audit / enforcement 事件
- 更系统的指标与实验能力

### 判断

虽然我们有日志，但这还不构成正式的观测层，也不构成失败恢复框架。  
所以这块现在仍应视为缺失。

### 结论

这块是 `完全缺失`。

---

## Gap 结论排序

如果按“最值得优先补强”的顺序排，我建议是：

1. 核心 runtime 主循环
2. 短期上下文治理
3. 会话连续性
4. 治理层
5. tool / skill / MCP 一体化
6. 观测与失败恢复
7. 多 loop / 多角色模型
8. 长期记忆 runtime（继续加强，但不是当前最大 gap）

---

## 一句话总结

我们现在的整体状态不是“什么都没有”，也不是“只差打磨”。

更准确地说：

- **长期记忆 runtime 已经形成主线**
- **通用 agent runtime 主干已经有雏形**
- **但短期上下文治理、会话连续性、治理层、失败恢复还没有形成正式系统**

也就是说，我们当前最大的 gap 不在 memory backend，而在：

- runtime kernel
- context/session continuity
- governance
- observability / recovery

这四块。
