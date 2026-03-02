# OpenClaw Memory 深度调研报告（Case13 真实验证）

## 0. README/论文亮点（先看这个）

基于 OpenClaw 文档与源码，memory 相关主张可归纳为：
- `Markdown-first`：`MEMORY.md` / `memory/*.md` 是事实源
- `Index as accelerator`：索引层加速检索，不替代原文
- `Compaction + flush`：在上下文管理节点触发记忆沉淀
- `Backend switch`：builtin / qmd 可切

本文后续映射：
- 定位与接口对应 `1`
- 机制对应 `2`
- 论文主张与实测对齐对应 `3`

术语先读：
- `docs/memory/memory_terms_compare.md`（本系统对应：最小单位=`snippet/chunk`，非结构化 `item/type/category`）

## 1. 组件定位与最小调用

OpenClaw 是端到端产品，memory 是其中一个模块。

最小调用链（模块侧）：
1. `getMemorySearchManager(...)`
2. `manager.search(query, ...)`
3. `manager.sync(...)`

本次 Case13 输出：
- `backups/memory/openclaw_case13_real_output.txt`

### 1.1 本系统术语与对象模型（OpenClaw 原生）

- 最小对象名词：`snippet/chunk`（检索返回片段）
- 事实源名词：`MEMORY.md`、`memory/*.md`
- 检索层名词：builtin（可切 qmd）

说明：OpenClaw memory 默认是“文件事实源 + 片段检索”，不是结构化 item/type/category 体系。

### 1.2 围绕模型管理记忆（OpenClaw）

典型交互节奏：
1. 模型/用户把长期信息写入 `MEMORY.md` 或 `memory/*.md`（或通过 flush 机制沉淀）。
2. 模型需要回忆时，调用 `memory search` 检索 snippet。
3. 检索片段回注到当前对话上下文，再继续生成。

关键点：OpenClaw 的主逻辑是“先有文件事实源，再做检索增强”，不是先抽取成结构化对象再注入。

## 2. 机制（How）

### 2.1 抽取/写入
- 以 Markdown 记忆文件为中心，不是独立结构化抽取数据库。
- `memory flush` 偏“提醒沉淀”，不是 Mem0/MemU 风格 schema 抽取。

### 2.2 存储
- source-of-truth：`MEMORY.md` 与 `memory/*.md`
- 检索层：builtin 索引（可切 qmd）

### 2.3 检索
- 本轮实测 `backend=builtin`
- `memory search --query ... --json` 返回 `results[].snippet`

## 3. 测试验证（论文主张 ↔ 实测结果对齐）

### 3.1 目标1：原理可观测性

| 主张 | 可观测信号 | 实测 | 结论 |
|---|---|---|---|
| Markdown-first | 结果以 snippet 原文片段返回 | `results[].snippet` 为对话原文块 | 主张成立 |
| 可检索 | Query-1..8 均有 `results` | 八条 query 都返回结果 | 检索链路可用 |
| 后端可观测 | status 输出 backend | 输出里 `backend: builtin` | 后端状态可观测 |

### 3.2 目标2：Case13 提取了什么、怎么存

这套实现本轮体现的是“原文片段检索”，不是结构化 item 抽取。

可见命中信息包含：
- 香菜厌恶
- 咖啡从冰美式改拿铁
- 奶油（猫）
- 钥匙挂厨房门后
- Chrome/Slack/VSCode/app.py

存储形态（本轮语义）：
- 原始记忆事实以 Markdown 为准
- 检索返回主要是块级 snippet

### 3.3 目标3：抽取/检索效果 + 不足分析

抽取效果：
- 不适用“结构化抽取评分”口径（本模块默认不是这条路线）。

检索效果：
- 能召回目标相关内容。
- 但结果噪声偏高：很多 query 返回的 top snippet 混有无关段落。

不足原因（本轮可见）：
- 原文块检索天然容易把相邻上下文一起带回。
- 缺少强结构化过滤字段，query 精排空间有限。

## 4. 学生证据清单（已摘好）

原始输出：
- `backups/memory/openclaw_case13_real_output.txt`

关键证据：
- backend 证据：`"backend": "builtin"`
- 查询执行证据：
  - `memory search --query 我中午想吃煎饼...`
  - `memory search --query 给我推荐个咖啡。`
  - ... 到 Query-8
- 命中证据：`"results": [...]`
- 片段证据（示例）：
  - 包含 `香菜` 段
  - 包含 `冰美式 -> 拿铁` 段
  - 包含 `钥匙在厨房门后的挂钩` 段

## 5. 最终判断（针对 Case13）

- 原理链路：通了（Markdown -> 索引 -> snippet 检索）。
- 抽取质量：不按结构化抽取体系评价（该模块默认不是此范式）。
- 检索质量：中等（能召回，但噪声偏高、精排不足）。

教学定位：
- 适合讲“文件源记忆 + 检索加速”范式。
- 也适合讲“原文块检索为何容易有噪声”。
