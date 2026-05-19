# Phase 02: Context & State

## 1. 文档目的

这篇文档定义 `v7.x` 阶段的核心工作：把当前 repo 中零散的上下文管理、会话状态、短期记忆、恢复语义，收敛成正式的 `Context & State` 层。

这一步的核心不是“再加一个 summary”，而是回答一个更基础的问题：

> agent 在持续运行时，当前上下文和会话状态到底如何延续？

如果 `Phase 01 / Runtime Kernel` 回答的是：

> 一轮运行怎么推进？

那么 `Phase 02 / Context & State` 回答的是：

> 一轮运行推进时，系统到底拿什么作为当前运行态？

这篇文档仍然服务三类人：

- 当前直接实现这一阶段的人
- 后面接手的人
- 通过这个 repo 学习 agent runtime 的学生

所以目标依然是：

- 架构边界清楚
- 实施路径清楚
- 验收标准清楚

---

## 2. 本阶段在整体路线中的位置

在整体路线里：

- `Phase 01 / v7` 解决的是 `Runtime Kernel`
- `Phase 02 / v7.x` 解决的是 `Context & State`

这两步必须紧挨着，因为：

- 没有正式 kernel，就很难定义上下文状态挂在哪
- 没有正式 context/state，kernel 又只能停留在“空壳生命周期”

两者的关系可以简单理解成：

- `Kernel` 负责推进
- `Context & State` 负责延续

所以这一阶段不是附属优化，而是内核之后必须补上的第二层。

---

## 3. 当前问题定义

### 3.1 当前 repo 已经有什么

当前 repo 已经有这些和 `Context & State` 相关的能力：

- session 持久化
- restore 基础
- workspace 概念
- 短期记忆 / 短期压缩思路
- working/raw message 双轨
- token/context 监控
- 标题 / summary 这类轻量会话信息

这说明：

- 我们不是完全没有这层能力
- 但这些能力还没有被抽成正式层

### 3.2 当前真正缺的是什么

当前真正缺的不是“能不能存消息”，而是：

- 缺 `active context` 的正式定义
- 缺 `transcript` 的正式地位
- 缺 `compact boundary` 语义
- 缺 `resume / restore` 的正式关系
- 缺 `summary` 和 `full history` 的清晰边界
- 缺“短期上下文治理”作为正式系统，而不是零散技巧

所以这里说的缺口不是“没有状态”，而是：

> 还没有把状态和上下文升格成一个有正式语义的运行时层。

---

## 4. 本阶段目标

## 4.1 总目标

定义并实现一个正式的 `Context & State` 层，让系统能回答下面这些问题：

- 当前 active context 是什么？
- 完整 transcript 是什么？
- compact 后到底保留了什么？
- session 恢复时，恢复的是哪一层状态？
- 长会话里“还在工作上下文里”和“只是留档可追溯”之间怎么区分？

## 4.2 子目标

### 目标 A：明确三层上下文

至少要正式区分：

- `active_context`
- `compressed_context`
- `full_transcript`

### 目标 B：正式定义短期状态对象

至少要明确：

- 当前运行时可见状态
- session 持久状态
- 从压缩中恢复的状态

### 目标 C：正式定义 compact boundary

让 compact 不再只是“发生过一次压缩”，而是：

- 有边界
- 有意义
- 可恢复
- 可解释

### 目标 D：正式定义 resume / restore

明确区分：

- `restore session`
- `resume active work`
- `show transcript history`

### 目标 E：把短期上下文治理升级成正式机制

从“超长时做一点压缩”升级成：

- 可解释的 context management

---

## 5. 范围与非目标

## 5.1 本阶段包含什么

本阶段包含：

- 上下文分层
- transcript 正式化
- compact boundary
- resume / restore 语义
- short-context compaction 收敛
- session/workspace state 的正式位置

## 5.2 本阶段不包含什么

本阶段不包含：

- 长期 memory backend 重做
- capability runtime 大一统
- 完整治理层实现
- cloud/session 分布式设计
- 重型 UI
- 完整 telemetry 平台

这阶段虽然会和 memory / governance 有交叉，但重点仍然是：

- **当前运行态如何延续**

---

## 6. 借鉴来源：应该吸收什么

## 6.1 从 Claude Code 吸收什么

### 吸收点 1：session continuity 的 seriousness

Claude Code 的一个核心启发是：

- 会话连续性不是顺手加的功能
- 而是 runtime 的核心问题

特别值得吸收的点：

- transcript persistence
- compact boundary
- preserved segment
- resume 语义
- session memory 与 compaction 的协同

我们不照搬它的产品形态，但要吸收它的原则：

- “当前能继续工作” 和 “历史可回看” 不是一回事

### 吸收点 2：短期上下文治理不是一次 summary

Claude Code 强的地方不只是能 compact，而是：

- 它把短期上下文治理当成持续机制

这对我们非常关键，因为它提醒我们：

- `Context & State` 不是一个 static snapshot
- 而是一个持续被管理的运行时层

### 吸收点 3：compact 后的连续性

Claude Code 真正强的是：

- compact 完了还能继续工作

而不是：

- compact 只是总结一下历史

我们这阶段要吸收的就是这个重心。

## 6.2 从 OpenClaw 吸收什么

### 吸收点 1：session ownership 的意识

OpenClaw 给我们的启发是：

- 外层 runtime 应该真正拥有 session 语义

不是只保存一份对话文本，而是：

- 知道当前 session 如何推进
- 知道 queued 输入怎么进入运行
- 知道会话状态属于外层系统，不属于某个局部实现细节

### 吸收点 2：输入/输出与状态推进的区别

OpenClaw 的 queue 语义很提醒人：

- 新输入来了，不代表就是新 session
- 同一个 session 下也可能有不同推进策略

这一点对我们后面定义 `Context & State` 很重要，因为这说明：

- 上下文状态和输入事件不是一回事

### 吸收点 3：外层运行态比底层消息更重要

OpenClaw 在服务化场景下很强调：

- session state
- run state
- queue state

这提醒我们在本阶段要把 state 看成正式对象，而不是附着在 message list 上的副作用。

---

## 7. 本阶段的架构设计

## 7.1 设计原则

本阶段建议遵守 4 条原则：

### 原则 1：消息不等于上下文

`full_transcript` 是完整历史，  
但它不等于当前模型真正看到的上下文。

### 原则 2：恢复不等于回放

恢复 session 时，不应把所有历史原样塞回 active context。  
恢复的是：

- 一个可继续工作的状态

而不是：

- 一段原始回放录像

### 原则 3：压缩不等于丢失

compact 后：

- active context 变小
- 但 transcript 仍应完整可追溯

### 原则 4：短期状态和长期记忆分离

`Context & State` 解决的是：

- 当前运行态如何延续

不是：

- 长期知识如何跨会话积累

---

## 7.2 建议的状态分层

### 1. `full_transcript`

含义：

- 完整的、可追溯的历史
- 用于回看、调试、审计、恢复

它应该：

- 尽量完整
- 不承担“必须直接送模型”的职责

### 2. `compressed_context`

含义：

- 由 compact / summary / boundary 形成的中间层
- 用于把旧上下文压缩成可继续工作的形式

它应该：

- 可解释
- 可生成
- 可替换

### 3. `active_context`

含义：

- 当前真正送给模型的上下文

它应该包含：

- 当前 turn 需要的 recent context
- 当前仍然有效的 short-term state
- 必要的压缩摘要
- 当前轮需要的 runtime additions

### 4. `session_state`

含义：

- session 层的运行状态

至少应包括：

- session id
- workspace id/path
- current branch / current summary ref
- last compact boundary
- current active context pointers

---

## 7.3 compact boundary 的正式定义

建议把 `compact boundary` 明确定义成：

> active context 与 compressed/full transcript 之间的切换点。

它至少应该回答：

- 哪些历史已经不直接进入 active context
- 哪段 summary 对应这些历史
- 从哪里开始还保留 recent context

所以 compact boundary 不只是一个“时间点”，而是：

- 一个语义边界
- 一个恢复边界
- 一个解释边界

---

## 7.4 resume / restore 的区分

建议正式区分三件事：

### `restore_session`

意思是：

- 把 session 的持久状态重新装回来

### `restore_transcript`

意思是：

- 把历史记录重新可视化/可访问

### `resume_work`

意思是：

- 重新恢复可工作的 active context

这三个现在在很多实现里容易混在一起。  
本阶段的目标就是把它们明确拆开。

---

## 7.5 最小接口建议

这阶段不一定马上全面重构，但建议至少形成下面这些概念接口：

### `ContextSnapshot`

表示某一时刻可供模型使用的上下文快照，例如：

- active messages
- summary refs
- compact boundary
- context usage

### `SessionState`

表示可持久化的 session 运行状态，例如：

- session id
- workspace
- current branch
- active context pointers
- compact metadata

### `TranscriptStore`

负责：

- 存完整历史
- 提供恢复与回看

### `ContextBuilder`

负责：

- 把 session_state + transcript + compressed_context 拼成 active_context

这几个对象本身就是后续教学的重要抓手。

---

## 8. 实施计划

## 8.1 第一步：先把概念画清楚

先不要急着重构代码。  
先在文档和代码注释层明确：

- `full_transcript`
- `compressed_context`
- `active_context`
- `session_state`
- `compact_boundary`

目标：

- 让大家先说的是同一种东西

## 8.2 第二步：给现有实现打“状态分层标记”

从当前 `v6.x` 代码里找：

- 哪些是 active context
- 哪些只是 raw history
- 哪些已经是 summary / compact 结果

目标：

- 先把现有行为映射到正式术语上

## 8.3 第三步：补 transcript 正式位置

把 transcript 从“保存历史”提升成正式 runtime 层的一部分：

- 明确存储位置
- 明确读取责任
- 明确和 active context 的关系

## 8.4 第四步：定义 compact boundary 元数据

不要求一开始就做很复杂，但至少：

- compact 之后要知道边界在哪
- active context 从哪开始
- 旧历史被什么 summary 代表

## 8.5 第五步：把 resume 变成正式行为

让恢复不再是“重读一堆消息再碰碰运气”，而是：

- 恢复 session_state
- 恢复 transcript
- 重建 active_context

## 8.6 第六步：补最小可解释输出

至少要能在调试/教学里看见：

- 当前 active context 是什么
- compact boundary 在哪里
- transcript 哪部分没进 active context

---

## 9. 验收标准

## 9.1 架构验收

### 标准 A

能够清楚区分：

- `full_transcript`
- `compressed_context`
- `active_context`

并且代码结构能映射到这三层。

### 标准 B

`compact boundary` 有明确语义，不再只是实现中的隐式结果。

### 标准 C

`restore_session`、`restore_transcript`、`resume_work` 三者语义明确，不再混用。

## 9.2 功能验收

### 标准 D

长会话 compact 后还能继续工作，且行为可解释。

### 标准 E

退出再恢复后：

- active context 正确
- transcript 可回看
- 状态不乱

### 标准 F

能够从运行结果中解释：

- 当前哪些历史仍在 active context
- 哪些只在 transcript 中
- 哪些被 summary 替代

## 9.3 教学验收

### 标准 G

学生可以回答：

- transcript 和 active context 的区别是什么？
- compact boundary 是什么？
- 恢复 session 时到底恢复了什么？

### 标准 H

学生可以看着一个长会话，讲清：

- 为什么 compact 后还能继续
- 哪些信息被压缩
- 哪些信息仍然活跃

---

## 10. 风险与常见误区

## 风险 1：把 transcript 直接当 active context

这是最常见的误区。  
如果 transcript = active context，那系统迟早会炸。

## 风险 2：把 compact 当成“总结功能”

compact 的核心价值不是总结，而是：

- 维持可工作的上下文边界

## 风险 3：把短期上下文和长期记忆混在一起

如果这阶段把 long-term memory 也混进来，很快会让边界失焦。

## 风险 4：恢复语义不清

如果 restore/resume 不分层，后面一旦有：

- compact
- session branching
- multiple shells

问题就会非常难调。

---

## 11. 非目标

本阶段明确不是要完成：

- 长期 memory backend 设计定稿
- capability runtime 大统一
- 正式治理层完整实现
- cloud/session 分布式状态
- 平台化 channel 语义

本阶段只解决一个核心问题：

> 当前运行态如何正式地延续下去？

---

## 12. 一句话总结

`Phase 02 / Context & State` 的目标，不是再加一个 summary，而是：

> 把 transcript、active context、compressed context、session state、compact boundary、resume/restore 这些长期被混在一起的概念正式拆开，并形成一个可解释、可恢复、可持续运行的上下文与状态层。

如果这一步做对，后面的：

- `Governance`
- `Capabilities`
- `Memory`
- `Local Product`

才有真正稳定的运行底座。
