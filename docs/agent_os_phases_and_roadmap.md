# Agent OS 阶段定义与演进路线

## 1. 目标

这个 repo 后续的目标不是做一个单一形态的 coding agent，而是逐步演进为一个更通用的 `Agent OS`：

- 能承载多种 agent 形态
- 核心抽象保持场景中立
- 能力层可替换
- 长短记忆分离
- 可以从本地壳子走到平台化形态

这里说的 `Agent OS`，不是“大而全的云平台”先行，而是：

- 先把内核抽象做对
- 再用本地产品形态把它压实
- 最后再演进成平台

---

## 2. 总体路线

建议把演进路线分成 3 个 phase：

1. `Core`
2. `Product (Local)`
3. `Platform (Cloud)`

可以压成一句话：

> 先做对，再做顺，最后做大。

其中：

- `Core`：做对
- `Product (Local)`：做顺
- `Platform (Cloud)`：做大

---

## 3. 当前定位

当前这个教学 repo，更准确的定位是：

> `Core with a thin local shell`

也就是：

- 主体仍然处在 `Core` 阶段
- 已经有一个比较浅的 `CLI shell`
- 这个 shell 的主要作用是：
  - 验证内核能力
  - 暴露 runtime 问题
  - 承载实验
  - 作为教学入口

它还不是成熟意义上的 `Local Product`。

所以现在最重要的不是继续加壳，而是把 core 再收紧。

---

## 4. 核心模块（第一性原理版）

从第一性原理看，Agent OS 的核心模块可以压成 5+2：

### 4.1 五个核心模块

#### 1. Runtime Kernel

回答的问题：

> agent 一轮是怎么运行的？

包含：

- message flow
- model step
- tool orchestration
- lifecycle
- continuation / retry / completion
- event emission

#### 2. Context & State

回答的问题：

> 当前运行态如何延续？

包含：

- context assembly
- active context
- transcript
- compaction
- resume
- session/workspace state
- short-term memory

#### 3. Memory

回答的问题：

> 跨回合、跨会话的长期知识如何存取？

包含：

- long-term memory runtime
- passive retrieve / passive write
- active `mem_*`
- backend / adapter

#### 4. Capabilities

回答的问题：

> 系统能做什么？

包含：

- tools
- skills
- MCP
- future agent delegation

#### 5. Governance

回答的问题：

> 系统在什么边界内行动？

包含：

- permissions
- policy limits
- resource/path validation
- hooks
- denial / audit

### 4.2 两个外围层

#### 6. Adapters / Product Shells

回答的问题：

> 系统通过什么形态暴露？

包含：

- CLI shell
- service shell
- channel shell
- automation shell

#### 7. Infrastructure

回答的问题：

> 系统依赖什么底层资源？

包含：

- model providers
- auth
- files
- stores
- queues
- telemetry plumbing

---

## 5. v7+ 渐进式 Roadmap

从 `v7` 开始，建议不再按“加功能”来推进，而是按“补系统层”来推进。  
这样更符合教学 repo 的节奏，也更适合后面演进成真正有潜力的 `Agent OS`。

总原则：

- 每个阶段只解决一个主问题
- 每个阶段都要有清晰的验证方案
- 每个阶段都要有一个学生能理解的核心价值
- 不跳阶段，不追求一步到位

---

## 6. v7: Runtime Kernel

### 阶段目标

- 把当前“能跑的 loop”升级成“正式 runtime kernel”
- 给后续所有模块提供稳定挂点

### 包含内容

#### 1. 生命周期正式化

把 loop 显式拆成阶段，例如：

- `turn_start`
- `context_prepare`
- `pre_model`
- `model_step`
- `tool_dispatch`
- `tool_result`
- `turn_complete`
- `turn_persist`

#### 2. 运行语义正式化

明确下面这些概念：

- `continuation`
- `retry`
- `completion`
- `abort`
- `failure`

#### 3. 统一事件模型

先形成基础事件类型，例如：

- `assistant_delta`
- `tool_call_started`
- `tool_call_finished`
- `memory_retrieved`
- `turn_finished`
- `turn_failed`

#### 4. CLI 与 kernel 继续解耦

让 CLI 更像调用 kernel，而不是继续长成执行核心。

### 验证方案

#### 验证 1：生命周期可追踪

一轮运行必须能输出稳定 phase trace。

#### 验证 2：同一 kernel 跑两类 turn

至少验证：

- 普通交互 turn
- 带工具调用的 turn

#### 验证 3：异常语义明确

手动制造：

- tool fail
- model fail
- abort

确认事件和阶段落点正确。

### 核心价值

- 把“代码实现”提升成“内核抽象”
- 这是 Agent OS 最基础的一层

### 教学价值

学生可以从这里第一次真正理解：

- agent loop 不是 while 循环
- 而是一个有正式生命周期的 runtime

---

## 7. v7.x: Context & State

### 阶段目标

- 把短期上下文、会话连续性、transcript 提升成正式层

### 包含内容

#### 1. 抽出 `Context & State`

统一收纳：

- active context
- transcript
- summary
- compact boundary
- session/workspace state

#### 2. 定义三层上下文

明确：

- `active_context`
- `compressed_context`
- `full_transcript`

#### 3. 短期上下文治理升级

先至少做到：

- 轻量裁剪
- 正式 compact

#### 4. resume / restore 语义清晰化

区分：

- 恢复 session
- 恢复 active context
- 恢复 transcript 可见历史

### 验证方案

#### 验证 1：长会话不炸

构造长对话，compact 后还能继续工作。

#### 验证 2：恢复一致

退出再恢复，确认：

- active context 正确
- transcript 可回看
- 状态不乱

#### 验证 3：边界可解释

能够清楚展示：

- 什么还在 active context
- 什么进入 compressed summary
- 什么只留在 transcript

### 核心价值

- 让系统真正具备连续工作的能力

### 教学价值

学生能理解：

- 短期记忆不是“总结一下”
- 而是上下文状态管理

---

## 8. v8: Governance

### 阶段目标

- 把权限、边界、策略、hooks 正式化成治理层

### 包含内容

#### 1. 抽出 `Governance`

形成统一接口：

- permissions
- policy limits
- resource validation
- denials
- audit hooks

#### 2. 工具权限统一入口

工具不再各自散着判断，统一经过 governance。

#### 3. memory / tool / shell 接治理层

让不同能力都能经过统一边界检查。

#### 4. hooks 归位

hooks 不再只是“哪里方便就插哪里”，而是治理/生命周期的一部分。

### 验证方案

#### 验证 1：权限拒绝一致

同样规则，对不同工具表现一致。

#### 验证 2：边界可审计

每次拒绝、限制、放行都有明确事件。

#### 验证 3：hook 顺序稳定

关键 hook 触发顺序可预测。

### 核心价值

- 让系统不只是“能做事”，还知道“什么时候不能做”

### 教学价值

学生能理解：

- 权限和策略不是附属功能
- 而是 runtime 的正式层

---

## 9. v8.x: Capabilities

### 阶段目标

- 把 tools / skills / MCP / memory tools 收敛成统一 capability runtime

### 包含内容

#### 1. 定义 capability model

至少统一这些维度：

- 能力描述
- 输入输出
- 生命周期
- 权限边界

#### 2. tool / skill / MCP 统一接入口

通过统一 registry / dispatcher 调用。

#### 3. memory capability 归位

把主动 `mem_*` 纳入 capability 体系。

#### 4. 能力发现与选择

为后面支持：

- capability listing
- capability filtering
- capability policy

做准备。

### 验证方案

#### 验证 1：不同能力走同一调度面

tool/skill/MCP 至少部分共用同一 registry。

#### 验证 2：统一事件与权限

不同 capability 都能走统一治理和事件流。

#### 验证 3：能力可替换

同类能力替换，不改 kernel 主逻辑。

### 核心价值

- 把分散能力变成正式子系统

### 教学价值

学生能理解：

- tool、skill、MCP 不是三摊东西
- 而是 capability 的不同形态

---

## 10. v9: Memory 深化

### 阶段目标

- 让长期 memory runtime 真正和 kernel / context / governance 咬合

### 包含内容

#### 1. Memory 生命周期归位

明确 memory 在 loop 哪些阶段发生：

- passive retrieve
- active memory calls
- passive write
- post-turn update

#### 2. 与 `Context & State` 区分清楚

正式划清：

- short-context
- long-memory

#### 3. backend / adapter 协议继续收敛

不是简单“可切换”，而是边界更稳。

#### 4. memory 事件和治理并入统一体系

memory retrieval / write 进入 event / governance。

### 验证方案

#### 验证 1：同一任务跨会话延续

长期记忆真正发挥作用。

#### 验证 2：短期/长期不串层

compact 和 memory backend 各司其职。

#### 验证 3：不同 backend 可交换

同一 runtime 接不同 backend，行为边界清楚。

### 核心价值

- 把 memory 从“功能”升级成“正式子系统”

### 教学价值

学生能学到：

- 长期记忆怎么和 runtime 内核配合
- 而不是把 memory 当外挂数据库

---

## 11. v9.x: Product (Local)

### 阶段目标

- 开始把本地产品壳做得更完整，但仍然不反向污染 core

### 包含内容

#### 1. CLI shell 与 kernel 完全分层

CLI 只负责：

- 输入
- 渲染
- 交互控制

#### 2. 更好的本地调试体验

- trace view
- session inspect
- memory inspect
- capability inspect

#### 3. 恢复与调试工作流

把 local 使用路径真正跑顺。

### 验证方案

#### 验证 1：学生能用

不只是作者自己能跑明白。

#### 验证 2：问题可定位

从 CLI 能看清：

- 当前 phase
- 当前 context
- 当前 memory
- 当前 capability 调用

#### 验证 3：内核不反向耦合

改 CLI 不需要改 kernel。

### 核心价值

- 用产品壳压实 core
- 但仍保持 shell 薄

### 教学价值

这一步最接近“kernel + shell”的心智。

---

## 12. v10+: Platform 预备

### 阶段目标

- 为 platform 做基础，而不是直接跳去做大平台

### 包含内容

#### 1. adapter/shell 抽象稳定

- local CLI
- service shell
- automation shell
- channel shell

#### 2. 基础设施抽象

- session store
- memory store
- task store
- event bus
- telemetry pipeline

#### 3. 平台预研能力

- remote session
- multi-tenant
- org policy
- cloud observability

### 验证方案

#### 验证 1：同一 kernel 跑本地和服务模式

#### 验证 2：session/memory store 可替换

#### 验证 3：event model 足够支撑远程壳

### 核心价值

- 为平台化铺路
- 不牺牲已经打磨好的 core

### 教学价值

学生能看到：

- 一个本地 agent runtime 如何演进成平台

---

## 8. 当前阶段的 Gap

按我们现在的状态，最大的 gap 不是长期 memory backend，而是这几块：

1. `Runtime Kernel`
2. `Context & State`
3. `Governance`
4. `Observability / Recovery`

更准确地说：

- 长期记忆 runtime 已经形成主线
- 通用 loop 主干已经有雏形
- 但还没有完全收敛成正式内核
- 短期上下文治理和会话连续性明显偏弱
- 治理层和观测/恢复还没形成正式层

---

## 9. 当前阶段的优先级

建议的优先级顺序：

### 第一优先级

1. `Runtime Kernel` 正式化
2. `Context & State` 补强
3. `Governance` 正式化

### 第二优先级

1. `Capability Runtime` 收敛
2. `Observability / Recovery`
3. `CLI shell` 与 kernel 边界清晰化

### 第三优先级

1. `Product (Local)` 完整打磨
2. `Platform (Cloud)` 方向预研

---

## 10. 现在不该过早做的事

在当前阶段，建议避免：

- 过早把 coding 特化写进 core
- 过早把 CLI 壳写成事实上的内核
- 过早固定角色模型（main/worker/background/orchestrator）
- 过早切到 cloud/platform 主线
- 过早把 UI / runtime / memory 死绑

尤其“角色模型”这一点，当前更合理的是：

- 先定义 loop 语义
- 先定义 capability profile
- 先定义 persistence / governance 边界

具体角色名可以后置。

---

## 11. 我们现在最应该坚持的原则

### 原则 1：先 Core，再 Product，再 Platform

不跳阶段。

### 原则 2：内核抽象优先于产品壳

shell 可以帮助验证内核，但不能取代内核。

### 原则 3：短期上下文和长期记忆分开设计

不要把 compaction、resume、session continuity 和 long-term memory 混为一谈。

### 原则 4：治理层必须正式化

permissions / policy / resource boundaries / hooks 都应该逐步收敛成一层。

### 原则 5：平台早期不固定具体角色编制

先定义运行模式，再让角色后置生长出来。

---

## 12. 一句话总结

当前 repo 的最佳路线不是：

- 继续堆产品壳
- 或者直接冲平台

而是：

> 继续把 `Core` 做扎实，同时保留一个足够轻的本地 shell 来验证和暴露问题；等 runtime kernel、context/state、governance 这些关键层收敛后，再进入 `Local Product`，最后才是 `Cloud Platform`。
