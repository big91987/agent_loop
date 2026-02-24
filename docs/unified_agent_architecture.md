# Unified Agent Architecture (CC + OpenClaw)

## 1. 背景与目标

当前我们有两类形态：

- `CC 形态`：交互式 CLI（被动触发，用户输入一轮跑一轮）
- `OpenClaw 形态`：常驻自治服务（被动监听外部调用，也可主动处理任务）

目标不是维护两套系统，而是统一为：

- 一个核心执行内核（Kernel）
- 两个外壳（CLI 壳 + Service/A2A 壳）

---

## 2. 统一结论

统一方式：`Kernel + Ports + Adapters`

- `Kernel`：统一 Agent 执行逻辑（loop、tool 调度、policy、状态机）
- `Ports`：统一输入输出接口（任务输入、事件输出、会话存储、任务存储）
- `Adapters`：不同入口壳（CLI、HTTP/A2A、Webhook、Queue）

这意味着：

- CLI 和 Service 共用同一套推理/工具/技能/MCP 能力
- 入口协议变化不影响核心执行逻辑
- 行为一致性更高，减少双实现偏差

---

## 3. 分层架构

### 3.1 Kernel 层（统一核心）

核心职责：

- 回合循环与停止条件
- tool call 执行闭环（本地工具、MCP、Skill、未来 A2A 代理工具）
- 策略控制（超时、重试、预算、权限）
- 统一事件模型（thinking/tool_call/tool_result/final）

建议接口（示意）：

```text
run_turn(session_id, input_message, options) -> TurnResult + Events
run_task(task_id, objective, options) -> TaskResult + Events
```

### 3.2 Ports 层（统一契约）

关键端口：

- `InputPort`: 接收请求（user turn / API call / queue event）
- `OutputPort`: 输出事件（stream/final/log）
- `SessionStore`: 会话读写
- `TaskStore`: 任务生命周期管理
- `EventBus`: 发布订阅进度与状态

### 3.3 Adapter 层（多入口壳）

- `CLI Adapter`: 解析命令与用户输入，调用 Kernel
- `Service Adapter`: 暴露 HTTP/A2A/Webhook 接口，调用 Kernel

---

## 4. Kernel 是否常驻

结论：`Kernel 逻辑不强依赖常驻`，`Runtime 资源可常驻`。

两种运行方式都支持：

- 非常驻（函数式按次执行）
  - 优点：简单、隔离强
  - 缺点：冷启动成本高、连接复用差
- 常驻（服务进程托管）
  - 优点：复用连接/缓存，适合自治与高并发
  - 缺点：需要并发隔离、资源回收、稳定性治理

推荐混合方案：

- `Kernel` 设计为可重入、无状态偏好
- `Runtime`（MCP 连接池、缓存、worker）由常驻服务托管

---

## 5. 统一后形态映射

### 5.1 CC 形态（CLI）

- 由 CLI Adapter 提供交互体验
- 通过同一 Kernel 执行 `run_turn`
- 可选接入本地 SessionStore 做恢复

### 5.2 OpenClaw 形态（Service）

- 由 Service Adapter 提供 API/A2A 监听
- 后台 worker 驱动 `run_task`
- 通过 TaskStore + EventBus 提供异步生命周期

---

## 6. 与 A2A 的关系

A2A 不替代 Kernel；A2A 是 Adapter/协议层能力。

- 对主编排器来说，可将远端 agent 封装为一个“代理工具”
- 底层由 A2A 完成发现、调用、任务跟踪、结果回传

映射：

- `tool_call(delegate_xxx)` -> Adapter 发 A2A `message/task`
- `tool_result` <- Adapter 回填 A2A 任务结果

---

## 7. 最小落地路线（建议）

1. 抽出统一 `AgentKernel`（先复用 v3/v4/v4.1/v5 核心 loop 逻辑）
2. CLI 仅保留命令解析和渲染，改为调用 Kernel
3. 增加 `SessionStore/TaskStore` 抽象和本地实现
4. 增加 `agentd` 常驻服务（HTTP 基础接口）
5. 在服务层新增 A2A Adapter（Agent Card + message/task endpoints）

---

## 8. 当前项目对应建议

当前 repo 已有：

- 多版本 loop（v1-v5）
- 本地工具闭环
- MCP（v4/v4.1）
- Skill 渐进披露（v5）

下一步关键是：

- 把 loop 能力沉淀到统一 Kernel
- 把 CLI 从“执行核心”降为“输入输出壳”
- 增加常驻服务壳，进入自治可调用形态

