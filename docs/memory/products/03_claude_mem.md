# Claude-mem 深度调研报告（Case13 真实验证）

## 0. README/论文亮点（先看这个）

基于 Claude-mem README 与源码，memory 相关主张可归纳为：
- `Observation-first`：先形成 observation，再入库
- `Dual-store`：SQLite 主存 + Chroma 语义检索
- `Worker orchestration`：抽取、解析、检索均由 worker 编排
- `Schema constraints`：prompt + parser 双约束

本文后续映射：
- 定位与接口对应 `1`
- 机制对应 `2`
- 论文主张与实测对齐对应 `3`

术语先读：
- `docs/memory/memory_terms_compare.md`（本系统对应：最小单位=`observation`，类型通过 mode/prompt 工程可配）

## 1. 组件定位与最小调用

Claude-mem 是“结构化 observation 记忆层”，不是单纯向量召回器。

最小调用链：
1. `SessionStore.storeObservation(...)`
2. `SearchOrchestrator.search(...)`

本次 Case13 输出：
- `backups/memory/claude_mem_case13_output.txt`

### 1.1 本系统术语与对象模型（Claude-mem 原生）

- 最小对象名词：`observation`
- 结构字段：`type/title/narrative/facts/concepts/...`
- 主存：SQLite（observations）
- 语义层：Chroma

说明：Claude-mem 的核心名词是 `observation`，不是 MemU 风格的 `item/type/category` 双层。

### 1.2 围绕模型管理记忆（Claude-mem）

典型交互节奏：
1. 模型交互事件先被转成 `observation`，再入 SQLite。
2. 新一轮模型推理前，`SearchOrchestrator` 按 query 选择 sqlite/chroma 路由检索 observation。
3. 命中 observation 回注到模型上下文，辅助当前回答。

关键点：Claude-mem 是“observation 驱动”链路，先结构化观察，再做检索回填。

## 2. 机制（How）

### 2.1 抽取
- 模型按 observation prompt 生成结构化内容。
- parser 负责约束和解析，再落 SQLite。

### 2.2 存储
- SQLite 是主事实库（observations）。
- Chroma 是语义检索层。

### 2.3 检索
- filter-only 时可走 sqlite。
- query 检索时优先 Chroma（输出里可见 `usedChroma/strategy`）。

## 3. 测试验证（论文主张 ↔ 实测结果对齐）

### 3.1 目标1：原理可观测性

| 主张 | 可观测信号 | 实测 | 结论 |
|---|---|---|---|
| observation 已入库 | `FILTER-ONLY` 返回 observations | 非空，含 `memory_session_id/title/narrative` | 入库链路成立 |
| 双存储可路由 | query 返回 `usedChroma/strategy` | Query-1..8 为 `usedChroma=true, strategy=chroma` | 检索路由成立 |
| 编排层可观测 | 每轮 query 输出完整检索对象 | 每轮都有 `results.observations` | 链路可观测 |

### 3.2 目标2：Case13 提取了什么、怎么存

存储形态：
- SQLite 文件：`claude-mem-case13.db`（运行目录下）
- observation 字段：`memory_session_id/title/narrative/...`

从本轮输出可见的 observation 内容主要集中在会话后段（例如 VSCode/app.py、钥匙位置、Slack 回消息等）。

### 3.3 目标3：抽取/检索效果 + 不足分析

抽取效果：
- observation 写入成功，结构字段完整。

检索效果：
- Query-1..8 都有返回，且走 Chroma。
- 但结果区分度不足：不同 query 返回的 observation 高度相似，偏向会话尾部内容。

不足原因（本轮可见）：
- 当前返回窗口偏向最近 observation，长程主题（如早段身份/偏好）在 top 结果中不够稳定。
- 说明“能检索”与“检索到最相关记忆”是两件事，后者仍需精排/权重策略优化。

## 4. 学生证据清单（已摘好）

原始输出：
- `backups/memory/claude_mem_case13_output.txt`

关键证据：
- 输入与库路径：`=== CLAUDE-MEM CASE13 INPUT ===`（含 `dbPath`, `withChroma=true`）
- 入库证据：`=== CLAUDE-MEM FILTER-ONLY CHECK ===` + `results.observations`
- Chroma 路由证据：
  - Query-1..8 中 `usedChroma=true`
  - `strategy=chroma`
  - `fellBack=false`
- 结果样例：
  - `当前在VSCode里看 app.py`
  - `钥匙在厨房门后的挂钩上`
  - `先在Slack里回一下消息`

## 5. 最终判断（针对 Case13）

- 原理链路：通了（observation 抽取 -> SQLite 持久化 -> Chroma 检索）。
- 抽取质量：中等偏上（结构化入库稳定）。
- 检索质量：中等（能召回，但 query 区分度和长程相关性有明显优化空间）。

教学定位：
- 适合讲“结构化 observation + 双存储路由”范式。
- 也适合讲“语义检索路由成功 ≠ 最终结果相关性最佳”。
