# Phase 01: Runtime Kernel

## 1. 文档目的

这篇文档定义 `v7` 阶段的核心工作：把当前 repo 中“能跑的 agent loop”提升成一个更正式、更稳定、更可复用的 `Runtime Kernel`。

这不是重写系统，也不是做大产品壳，而是做一件更基础的事情：

> 把已经存在的 loop 能力，从“实现主线”提升为“内核抽象”。

这篇文档要服务三类人：

- 当前直接实现这阶段的人
- 后面接手的人
- 通过这个 repo 学习 agent runtime 的学生

所以它既要足够工程化，也要足够教学化。

---

## 2. 本阶段在整体路线中的位置

整体路线是：

- `Core`
- `Product (Local)`
- `Platform (Cloud)`

而 `Phase 01 / v7` 属于 `Core` 的第一步。

如果这一步没做好，后面的问题会很快出现：

- shell 和 kernel 混在一起
- memory、tools、skills、MCP 都找不到稳定挂点
- 不同 loop 形态会开始分叉
- continuation / retry / recovery 会一直是隐式行为
- 学生看到的只是“越来越大的 if/else”，而不是可解释的 runtime

所以这一阶段的价值非常基础：

- 它不直接让产品变漂亮
- 但它决定后面系统会不会越长越乱

---

## 3. 当前问题定义

### 3.1 当前 repo 已经有什么

当前 repo 已经有：

- 多版本 loop 演进主线（`v1` 到 `v6.3`）
- tool 调用闭环
- MCP 接入
- skill 注入
- memory runtime（尤其 `v6.3`）
- workspace / session 概念
- 基础日志和调试输出

也就是说：

- 我们**不是没有 loop**
- 我们也**不是只有概念**

### 3.2 当前真正缺的是什么

当前真正缺的不是“能不能继续跑”，而是：

- 缺正式 lifecycle
- 缺正式 runtime 语义
- 缺统一事件模型
- 缺 shell 与 kernel 的更清晰边界
- 缺可承载后续多种 loop 形态的 kernel 抽象

所以这里说的 “缺 Runtime Kernel”，不是说系统没有 loop，而是说：

> 还没有把已有 loop 抽象成一个正式的、可复用的、可承载多场景的执行内核。

---

## 4. 本阶段目标

## 4.1 总目标

把当前已有 loop 抽成一个正式的 `Runtime Kernel`，让它回答下面这个问题：

> 一轮 agent 运行，在系统里到底是如何推进的？

## 4.2 子目标

### 目标 A：正式定义生命周期

至少明确这些阶段：

- `turn_start`
- `context_prepare`
- `pre_model`
- `model_step`
- `tool_dispatch`
- `tool_result`
- `turn_complete`
- `turn_persist`

### 目标 B：正式定义运行语义

至少明确这些概念：

- `continuation`
- `retry`
- `completion`
- `abort`
- `failure`

### 目标 C：正式定义事件模型

至少产出一组基础 runtime events，供：

- shell
- memory
- governance
- observability

统一消费。

### 目标 D：把 kernel 从具体 shell 中继续抽离

让 CLI 成为：

- 输入/输出壳

而不是：

- 事实上的执行内核

---

## 5. 范围与非目标

## 5.1 本阶段包含什么

本阶段包含：

- 生命周期建模
- runtime 语义建模
- 统一事件模型
- kernel API 收紧
- shell/kernel 边界进一步清晰

## 5.2 本阶段不包含什么

本阶段不包含：

- 重做 memory runtime
- 大改 CLI 体验
- 新增 cloud platform 能力
- 固定多角色模型
- 做复杂 UI
- 大规模能力体系重写

尤其不做：

- “为了看起来像产品”而继续往 CLI 里堆逻辑
- “为了平台化”提前引入 service/cloud 复杂度

---

## 6. 借鉴来源：应该吸收什么

这阶段不是凭空设计，我们明确借鉴两个方向。

## 6.1 从 Claude Code 吸收什么

### 吸收点 1：生命周期意识

Claude Code 最大的启发不是某个具体 API，而是：

- 它把 loop 视为正式 runtime
- 各种行为都有阶段感和失败语义

我们这一阶段要借的是这个意识：

- runtime 不是“大 while 循环”
- 而是有正式 phase 的系统

### 吸收点 2：continuation / retry / recovery 的正式语义

Claude Code 在这些方面更成熟：

- 输出没完如何继续
- 压缩后如何继续
- 错误后如何重试
- transcript/continuity 如何不断裂

我们这一阶段不照搬实现，但要把这些概念正式化。

### 吸收点 3：主 loop 工程质量

Claude Code 的主 loop 更像一个真正的 runtime kernel，而不是单纯调用链。

这一阶段我们要学习的是：

- 如何从“实现能跑”升级到“架构可解释”

## 6.2 从 OpenClaw 吸收什么

### 吸收点 1：shell / kernel 分离意识

OpenClaw 给我们的启发不在底层 agent 推理，而在：

- 外层 orchestrator/shell 和内层 agent execution 可以分离

这和我们后面想做的：

- core -> product(local) -> platform(cloud)

是同向的。

### 吸收点 2：外层拥有 session 和运行语义

OpenClaw 的价值之一在于：

- session ownership
- queue semantics
- event bridge

虽然这一阶段我们不做平台，但要建立这种意识：

- shell 不该吞掉 kernel
- kernel 也不该假装自己就是产品壳

### 吸收点 3：事件桥接思维

OpenClaw 很强调：

- agent 内部事件
- 外部系统事件

之间的桥接。

这提醒我们：

- 事件模型不能只为当前 CLI 服务
- 以后也要能给别的 shell / adapter 用

---

## 7. 本阶段的架构设计

## 7.1 核心抽象

这一阶段建议把 runtime kernel 至少收敛成下面三个对象：

### 1. `RuntimeRequest`

描述一轮运行输入，例如：

- session_id
- user input
- runtime options
- mode
- workspace context

### 2. `RuntimeResult`

描述一轮运行的最终结果，例如：

- final messages
- stop reason
- usage summary
- persisted state references

### 3. `RuntimeEvent`

描述运行中产生的事件，例如：

- assistant delta
- tool start/end
- memory retrieved
- turn completed
- turn failed

---

## 7.2 生命周期建议

建议用显式 phase，而不是隐式流程。

最小 phase 集合建议为：

1. `turn_start`
2. `state_load`
3. `context_prepare`
4. `pre_model`
5. `model_step`
6. `tool_dispatch`
7. `tool_result`
8. `post_model`
9. `turn_complete`
10. `turn_persist`
11. `turn_end`

说明：

- 这不是说每轮都一定经过所有 phase
- 而是说 phase 应该是正式语义层
- 以后 hooks、governance、memory、tracing 都可以挂在这些点上

---

## 7.3 continuation / retry / completion 的正式定义

### `completion`

表示：

- 当前 turn 已经走到可结束状态
- 生成了 final result
- 可以进行持久化和结束事件

### `continuation`

表示：

- 当前任务没结束
- 只是需要继续推进一段

典型情况：

- tool result 回来后继续
- compact 后继续
- 模型输出被截断后继续

### `retry`

表示：

- 某一步失败
- 按明确规则重新执行该步或后续步

典型情况：

- model transient error
- compact 之后重新请求
- 可恢复错误后的有限重试

### `abort`

表示：

- 当前运行被主动终止
- 不再继续推进

### `failure`

表示：

- 当前运行进入失败结束态
- 需要产生失败事件和失败结果

---

## 7.4 事件模型建议

本阶段不追求完整，但至少要形成最小事件集合。

建议先定义：

- `turn_started`
- `context_prepared`
- `assistant_delta`
- `assistant_message_completed`
- `tool_call_started`
- `tool_call_finished`
- `tool_call_failed`
- `memory_retrieved`
- `turn_completed`
- `turn_aborted`
- `turn_failed`
- `turn_persisted`

要求：

- 事件名稳定
- 事件 payload 有最小统一字段
- shell 不直接猜 loop 内部状态
- 后续 observability 可以直接基于它扩展

---

## 7.5 shell 与 kernel 边界

本阶段要坚持一个简单原则：

### Kernel 负责

- 生命周期推进
- 调模型
- 调能力
- 发事件
- 产出结果

### CLI shell 负责

- 输入采集
- 渲染输出
- 用户交互
- 调用 kernel
- 展示 phase / event / result

也就是说：

- shell 不定义内核语义
- shell 不偷偷持有比 kernel 更多的运行状态

---

## 8. 实施计划

## 8.0 当前阶段要补哪些东西

这一阶段先不追求“大重构”，而是把现在已经存在的 loop 收紧成一个可解释、可验证、可继续演进的最小 kernel 边界。

第一批要补的东西只有 5 类：

### 1. 生命周期

- 正式 phase 集合
- turn 结束态
- stop reason

### 2. 运行对象

- `RuntimeRequest`
- `RuntimeEvent`
- `RuntimeResult`

### 3. loop 显式化

- 在 `v6.3` 上把 phase 和 event 标出来
- 让当前运行链可以被 trace 和回放理解

### 4. shell / kernel 边界

- CLI 只消费事件和结果
- loop / kernel 负责定义运行语义

### 5. 最小异常语义

- tool fail
- model fail
- abort

---

## 8.1 第一步：定义语义，不急着大改实现

先明确：

- phase list
- runtime state terms
- event names
- completion / continuation / retry / abort / failure 语义

产出：

- 一份 runtime semantics 文档
- 一份内核接口草案

## 8.2 第二步：给现有 loop 打 phase trace

先不要重构太大。  
先让现有 `v6.3` loop 能稳定输出 phase trace。

目标：

- 看清当前真实生命周期
- 发现哪些阶段现在是隐式的

## 8.3 第三步：抽最小 `RuntimeEvent`

先抽一版最小统一事件，而不是继续散着打印日志。

目标：

- shell 和 debug 不再强依赖内部实现细节

## 8.4 第四步：让 CLI 调用更明确的 kernel 入口

至少在结构上形成：

- kernel function / class
- CLI shell wrapper

不要求一步完全重构，但边界要开始清楚。

第一版可以先收成：

- `RuntimeRequest(session_id, user_input, mode, workspace_path, runtime_options)`
- `run_turn_request(request) -> RuntimeResult`

这里的重点不是一步到位，而是：

- 让结构化 request/result 先存在
- 让 CLI 有机会从“直接调字符串函数”过渡到“调 kernel 入口”

## 8.5 第五步：补最小异常语义

至少把下面三种情况做清楚：

- tool fail
- model fail
- abort

确认：

- phase 正确
- event 正确
- result 正确

---

## 8.6 本阶段第一刀的具体落点

为了保证渐进式演进，第一刀只做下面这些非常具体的事：

### 已实现

1. 新增最小 runtime 类型文件

- `RuntimePhase`
- `TurnStatus`
- `StopReason`
- `RuntimeEvent`
- `RuntimeRequest`
- `RuntimeResult`

2. 在 `V6_1` 上补最小 runtime 辅助能力

- `_new_turn_id()`
- `_emit_runtime_event(...)`
- `_emit_phase(...)`
- `run_turn_request(request)`

3. 在 `V6_3.run_turn(...)` 上做 phase / event 插桩

当前已经显式标出的 phase：

- `turn_start`
- `state_load`
- `context_prepare`
- `pre_model`
- `model_step`
- `tool_dispatch`
- `tool_result`
- `post_model`
- `turn_complete`
- `turn_persist`
- `turn_end`

当前已经显式标出的事件：

- `phase_changed`
- `assistant_delta`
- `assistant_message_completed`
- `tool_call_started`
- `tool_call_finished`
- `tool_call_failed`
- `memory_retrieved`
- `memory_persisted`
- `turn_completed`
- `turn_failed`
- `turn_aborted`

4. CLI 侧开始消费 runtime events

当前 `cli_v6_3.py` 已经能把 runtime event 渲染成：

- `[PHASE] ...`
- `[EVENT] tool_call_started ...`
- `[EVENT] memory_persisted ...`
- `[EVENT] turn_completed ...`

5. 新增一个走结构化 kernel 入口的本地壳

- `cli_v7.py`
- 它通过 `run_turn_request(RuntimeRequest(...))` 调用 loop
- 它接收 `RuntimeResult`，不再只依赖字符串结果

### 还没做完

1. 结构化 request/result 还没有成为 CLI 的唯一入口
2. terminal failure 还没有完全细分成 `tool_error` / `model_error`
3. `run_turn_request(...)` 目前是最小包装，还不是独立 kernel class
4. phase / event 还没有测试文件和固定快照

---

## 9. 验收标准

本阶段验收，不看“写了多少代码”，而看下面这些是否成立。

## 9.1 架构验收

### 标准 A
能够清楚画出 runtime 生命周期图，并且和代码行为对得上。

### 标准 B
CLI 不再承担内核语义定义，kernel 和 shell 边界更清楚。

### 标准 C
continuation / retry / completion / abort / failure 有明确文档定义，并且代码实现能对应。

## 9.2 功能验收

### 标准 D
普通 turn 可以输出稳定 phase trace。

### 标准 E
带工具调用的 turn 可以输出稳定 phase trace。

### 标准 F
至少有最小统一事件模型可供后续 shell / tracing 使用。

## 9.3 教学验收

### 标准 G
学生可以通过文档和日志回答：

- 这一轮经历了哪些 phase？
- 什么叫 continuation？
- 什么叫 retry？
- shell 和 kernel 边界在哪？

### 标准 H
学生能把当前 loop 和“正式 kernel”之间的差别讲清楚。

---

## 10. 风险与常见误区

## 风险 1：一上来大重构

如果一开始就全面重写 loop，很容易：

- 破坏现有可运行主线
- 失去对行为的可比性

更稳的方式是：

- 先定义
- 再标注
- 再抽象

## 风险 2：把 CLI 壳继续做成事实内核

如果 phase/event/状态只存在于 CLI 代码里，那这阶段就没真正完成。

## 风险 3：把 Capability / Memory / Governance 提前硬塞进 kernel

这一阶段的目标是：

- 给它们预留稳定挂点

不是：

- 一次把所有层都收完

## 风险 4：过早固定角色模型

这一阶段不要一上来写死：

- main
- worker
- background
- orchestrator

更合理的是：

- 先定义 loop 语义
- 角色后置

---

## 11. 非目标

这阶段明确不是要完成：

- 完整 local product
- cloud platform
- 正式多 agent 编制
- 完整 observability 平台
- memory 全面重构
- capability 全面统一

这些都在后面阶段处理。

---

## 12. 一句话总结

`Phase 01 / v7 Runtime Kernel` 的真正目标，不是“把 loop 再写大一点”，而是：

> 把当前已经存在的 agent loop 提升成一个有正式生命周期、正式运行语义、正式事件模型，并且和 shell 边界清楚的内核。

如果这一步做对，后面的：

- `Context & State`
- `Governance`
- `Capabilities`
- `Memory`
- `Local Product`
- `Platform`

才会有稳定的地基。
