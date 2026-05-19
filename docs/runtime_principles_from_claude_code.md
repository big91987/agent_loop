# 通用 Agent Runtime 设计原则：从 Claude Code 吸收什么，不照搬什么

## 背景

Claude Code 是一个很强的产品级 agent runtime，但它的强项建立在一组很明确的前提上：

- 以单主 agent 为中心
- 明显面向 coding / repo / terminal / file edits 场景
- 长会话、长上下文、长任务连续性是核心问题
- subagent 更像增强能力，而不是系统的对等核心角色

这套设计在 coding 场景里非常合理，也很成熟。  
但我们的目标不是做 Claude Code 的简化复刻，而是做一个更通用、更可迁移、能支撑多场景的 agent runtime。

所以更合理的做法不是照抄，而是：

- 吸收它做得很好的工程经验
- 保持我们自己的核心抽象场景无关
- 明确什么值得借鉴，什么不应该继承

---

## 一句话结论

Claude Code 是一个非常优秀的 `coding-first`、`single-main-agent`、产品级 runtime；  
我们应该吸收它在短期上下文治理、会话连续性、工具化与异常恢复上的工程经验，但我们的总设计必须保持：

- 场景中立
- 能力解耦
- 多角色可扩展
- 长短记忆分离

而不是围绕 coding 主 loop 固化。

---

## Claude Code 值得吸收的部分

### 1. 短期上下文治理

Claude Code 最值得学的，不是某个单独的 summary，而是它对短期上下文的分层处理思路：

- `snip`
- `microcompact`
- `autocompact`
- `reactive compact`
- `session memory compact`

它体现的是一个重要原则：

- 不要把短期记忆只当成“一次总结”
- 应该把上下文治理当成持续运行时机制

这对我们后续最有价值的启发是：

- context management 应该分阶段
- compact 不只是“超长时兜底”，而是正常 runtime 的一部分
- 失败后要有 reactive recovery 路径

### 2. 会话连续性（session continuity）

Claude Code 在这块做得非常成熟，主要体现在：

- transcript persistence
- compact boundary
- preserved segment
- resume
- session memory `summary.md`

这说明它不是只关心“这一轮怎么答”，而是在认真处理：

- 会话压缩后怎么继续
- 会话恢复时怎么尽量连续
- active context 和 full history 怎么分层

对我们的直接启发是：

- `session` 不能只是消息列表
- 需要正式定义 active context、summary、full transcript 的关系
- `resume` 和 `restore` 需要明确语义边界

### 3. runtime 能力统一

Claude Code 把这些能力放进了比较统一的 runtime 里：

- tools
- skills
- MCP
- subagent runtime
- hooks

它的价值不在于“功能多”，而在于这些能力不是散着挂，而是纳入同一运行时体系。

对我们的启发是：

- tool runtime 应该是正式层
- skill runtime 应该是正式层
- MCP 不该只是外挂
- hooks 应该成为 loop 生命周期的一部分

### 4. 失败路径优先思维

Claude Code 对失败路径的重视，明显高于很多同类系统：

- prompt too long
- output too long
- compact 后恢复
- transcript consistency
- continuation / retry

这背后体现的是一个很重要的工程原则：

- 不只设计 happy path
- 要把失败路径当一等公民

这对我们后续演进非常关键，因为通用 agent runtime 一旦跨场景，失败路径只会更多，不会更少。

---

## Claude Code 不应该直接照搬的部分

### 1. coding-first 的世界观

Claude Code 的很多设计天然围绕这些对象展开：

- 文件系统
- repo
- Git
- terminal
- 工程命令
- 项目规则文件

这套世界观在 coding agent 里是优势，但如果我们直接继承，后面系统会不自觉把：

- `workspace`
- `repo state`
- `file edits`
- `project instructions`

当成默认中心。

这不适合我们后续要支持的更广泛场景，例如：

- personal assistant
- research agent
- workflow agent
- domain-specific task agent
- orchestrator / coordinator

### 2. 单主 agent 中心化过强

Claude Code 的整体设计里，主 loop 是明显的系统中心。

subagent 存在，但更多是：

- 补充能力
- 受控执行
- sidechain runtime

而不是与主 agent 对等的核心角色。

这对 Claude Code 本身很合理，但不适合作为我们的总蓝图。  
我们更需要的是：

- main loop 只是某种 loop
- worker loop、background loop、memory loop、planner loop 可以是其他 loop
- 多种角色共享 runtime kernel，但不一定共享同一种 loop 语义

### 3. 过重的 runtime 耦合

Claude Code 的很多能力是强耦合的：

- query
- compaction
- transcript
- UI
- tools
- session memory
- CLAUDE.md

对成熟产品来说，这种耦合是工程换体验的结果。  
但对我们当前要做的通用架构来说，这样会过早锁死：

- 扩展方式
- 抽象边界
- 跨场景迁移能力

所以我们应该坚持：

- loop 生命周期清晰
- memory runtime 可替换
- tool runtime 可替换
- skill runtime 可替换
- backend / adapter 可替换
- scene-specific policy 可替换

### 4. 把短期上下文和长期记忆混成一层

Claude Code 给我们的一个提醒是：

- 它的短期上下文治理非常强
- 但它的长期记忆更偏 rules / session memory / transcript continuity

这说明：

- 短期上下文不等于长期记忆
- session continuity 不等于通用 long-term memory runtime

所以我们后续应该明确分开：

- 短期记忆：`context management`
- 长期记忆：`persistent memory runtime`

---

## 我们后续应该坚持的设计原则

### 原则 1：核心抽象场景无关

核心 runtime 只应该关心这些通用问题：

- message flow
- context assembly
- tool orchestration
- memory hooks
- skill hooks
- state persistence
- agent coordination

不要让 `coding` 成为默认前提。

### 原则 2：能力层插件化

我们已经在走这条路线，而且应该继续坚持：

- memory backend / adapter
- skill system
- MCP
- tool sets
- scene-specific policy

这条路线的价值在于：

- 它不要求所有场景共用一套业务心智
- 只要求共享 runtime kernel 和扩展点

### 原则 3：主 loop 只是一个特例，不是唯一中心

理想状态下，后续不同场景可以有不同 loop 变体，例如：

- coding assistant loop
- personal assistant loop
- orchestrator loop
- background maintenance loop
- memory extraction loop

它们应该：

- 共享 runtime kernel
- 共享基础能力层
- 共享持久化和治理机制

但不必共享完全相同的 loop 语义。

### 原则 4：短期记忆与长期记忆分开设计

后续设计里要明确区分：

- 短期记忆：active context、compaction、resume、session continuity
- 长期记忆：profile、history、policy、persistent memory objects

这两者可以协作，但不要混成一锅。

### 原则 5：治理层是正式层，不是附属逻辑

Claude Code 给我们的一个重要启发是：

- permissions
- policy limits
- hooks
- path/resource validation

这些不只是零散判断，而应该是一层正式治理机制。

对我们来说，这意味着后面要逐步把这些从 loop 细节里抽出来，形成可替换、可观测、可扩展的治理层。

---

## 对我们当前架构的直接含义

### 应继续保留的方向

- `runtime / adapter / backend` 主线
- memory 双通道设计
- skill 的可替换注入机制
- workspace / session 这些通用持久化层

### 应优先加强的部分

- 短期上下文治理
- session continuity
- compact boundary / resume 语义
- agent runtime 抽象
- 多 loop / 多角色模型
- 治理层正式化

### 应避免的方向

- 过早把 coding 特化写进核心架构
- 过早把主 loop 神化成唯一中心
- 过早把 UI / runtime / memory 死绑在一起
- 过早为了某一种产品形态牺牲泛化性

---

## 推荐的对标策略

对 Claude Code，建议采用下面这种学习方式：

### 学它的

- 短期上下文治理思路
- session continuity 工程
- tool / skill / MCP 的 runtime 一体化
- 失败路径设计
- 治理层的重要性

### 不学它的

- coding-first 世界观
- 单主 agent 中心化默认设定
- 过重的 runtime 耦合
- 把产品壳和运行时深度绑定的方式

---

## 最终判断

Claude Code 是一个非常优秀的参考对象，但它更适合作为：

- `优秀样本`
- `工程标杆`
- `局部能力参考`

而不是我们的总蓝图。

我们的目标应该始终保持清楚：

- 做通用 agent runtime
- 保持核心抽象中性
- 吸收成熟系统的优秀部分
- 不被单一场景的成功范式绑住

这也是后续版本演化时最值得坚持的总原则。

---

## Phase 定义与演进路线

我们后续的演进路线，建议明确分成 3 个 phase：

1. `Core`
2. `Local Product`
3. `Cloud Platform`

这条路线的核心原则是：

- 先做对
- 再做顺
- 最后做大

也就是：

- `Core`：把抽象做对
- `Local Product`：把体验做顺
- `Cloud Platform`：把系统做大

### Phase 1: Core

目标：

- 定义通用 agent runtime 的最小正确抽象
- 不被具体产品形态绑架
- 保持场景中立

重点模块：

- `Runtime Kernel`
- `Context & State`
- `Memory`
- `Capabilities`
- `Governance`

这个阶段关注的是：

- loop 生命周期
- context assembly
- short memory / long memory 分层
- capability runtime
- governance 正式化
- state persistence
- event model

这个阶段**不以产品完整性为目标**，而是以内核正确性为目标。

### Phase 2: Local Product

目标：

- 用一个本地可交互壳子把 core 压实
- 在真实使用中暴露 runtime 抽象的问题
- 建立稳定、连续、可恢复的本地体验

重点问题：

- session continuity
- transcript / resume
- compact boundary
- 错误恢复
- capability discoverability
- memory 注入效果
- 权限/治理的真实摩擦

这个阶段的重点不是“做平台”，而是验证：

- core 抽象是否真的可用
- runtime 是否能承受持续交互

### Phase 3: Cloud Platform

目标：

- 把已经验证过的 core 和 local runtime 放大成平台能力
- 支撑多入口、多渠道、多角色、多租户的运行形态

重点问题：

- service shell
- channel shell
- automation shell
- remote session
- org / policy
- observability
- distributed state
- adapter / integration scaling

这个阶段不该太早进入。  
只有当：

- core 稳定
- local product 跑顺
- 基本 runtime 语义收敛

之后，再进入 platform 才健康。

---

## 我们当前所处阶段

当前这个教学 repo，更准确的定位是：

> `Core with a thin local shell`

也就是：

- 主体仍然是 `Core`
- 目前已经有一个比较浅的 `CLI shell`
- 这个 shell 的主要作用是：
  - 验证内核能力
  - 承载实验
  - 承载教学
  - 暴露 runtime 问题

它还不是成熟意义上的 `Local Product`。

这意味着：

- 现在的主工作仍然应该是 `Core` 补强
- 不应该过早把产品壳逻辑写进内核
- 也不应该现在就把精力切去做 `Cloud Platform`

---

## 当前阶段的 Roadmap

### P1. Runtime Kernel 正式化

目标：

- 把已有 loop 从“可运行实现”提升成“正式 runtime kernel”

重点工作：

- 明确 loop 生命周期阶段
- 明确 continuation / retry / completion 语义
- 明确统一事件模型
- 把核心执行逻辑从具体 shell 中抽离

### P2. Context & State 补强

目标：

- 让短期上下文治理和会话连续性成为正式层

重点工作：

- transcript 正式化
- compact boundary 语义
- active context / summary / full history 关系定义
- session continuity 设计
- short-context compaction 分阶段化

### P3. Governance 正式化

目标：

- 把权限、策略、边界控制从散落逻辑变成正式层

重点工作：

- permissions
- policy limits
- resource/path validation
- denial / audit
- hooks 归位到治理层

### P4. Capability Runtime 收敛

目标：

- 把 tools / skills / MCP / memory 收敛成统一 capability 体系

重点工作：

- capability model
- capability lifecycle
- 统一注入/调用语义
- adapter / runtime 边界进一步清晰

### P5. Local Product 预备

目标：

- 在不扭曲 core 的前提下，把本地壳子做得更能暴露真实问题

重点工作：

- CLI shell 和 runtime kernel 边界清晰化
- 真实 session 使用路径收紧
- 更好的 debug / trace / restore 体验

### P6. Platform 预研（不是立即落地）

目标：

- 只做 platform 方向预研，不急于进入实现主线

关注点：

- adapter/shell 设计
- service / channel 形态
- remote session
- org policy
- observability at scale

这里可以借鉴 `OpenClaw`，但不应现在就切到平台阶段。

---

## 当前最优先的事情

按优先级排序，当前最值得做的是：

1. `Runtime Kernel` 正式化
2. `Context & State` 补强
3. `Governance` 正式化
4. `Capability Runtime` 收敛
5. `Local Product` 壳层验证

可以暂缓的是：

- Cloud Platform 级能力
- 过重的 UI/product 打磨
- 过早固定角色模型
- 过早固定多 agent 编制
