# Zep 调研报告（Case13 状态版）

## 0. README亮点（先看这个）
- `Temporal knowledge graph`：强调关系和时序变化。
- `Graphiti`：Zep CE 强依赖 Graphiti 服务。
- `Context assembly`：面向 agent 的上下文拼装。

## 1. 组件定位与对象模型
- 仓库: `https://github.com/getzep/zep`
- 本地代码: `/tmp/memory_scan_round2/zep`
- 本轮目标: 用共享 `case13` 跑“写入 + 检索”真实链路。

核心对象（Zep CE）：
- `session`：会话级记忆容器。
- `memory/messages`：会话消息写入。
- `facts`：由 Graphiti 提取并参与检索。

## 2. 怎么用（最小调用）
典型 API 路径（v2）：
1. 创建 user / session
2. POST `/sessions/{id}/memory`
3. POST `/sessions/search`

## 3. 原理（抽取/存储/检索/注入）
- 抽取：Graphiti 负责从消息抽取事实与关系。
- 存储：PostgreSQL（Zep schema）+ Graphiti 图谱存储。
- 检索：session 搜索会走 Graphiti 检索结果拼装。
- 注入：通常由上层 agent 取回 context block 后注入提示词。

## 4. Case13 效果验证（当前状态）
- 当前环境已验证：Zep CE 服务可启动。
- 但 `case13` 写入链路未跑通：`/users` 等入口依赖 Graphiti 在线服务，当前环境无可用 Graphiti/Neo4j 实例。
- 因此本轮对 Zep 的 `case13` 结果状态是：`未完成（依赖缺失）`。

## 5. 结论
- Zep 的核心价值在“时序图谱记忆 + 关系检索”，不是纯文本记忆库。
- 没有 Graphiti，就无法得到它声明的核心记忆能力。
- 下一步要完成 case13：补齐 Graphiti + Neo4j 运行环境后重跑同一测试集。
