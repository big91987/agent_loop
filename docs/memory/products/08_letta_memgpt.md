# Letta / MemGPT 调研报告（Case13 实测版）

## 0. README/论文亮点（先看这个）
- `Stateful agent memory`：记忆是 agent runtime 的一部分，不是外挂插件。
- `memory blocks + archival memory`：运行态记忆和档案记忆并存。
- `context pressure handling`：强调上下文压力下的记忆调度。

亮点 -> 本文章节：
- stateful 架构 -> `1. 组件定位与对象模型`
- 双层记忆对象 -> `3. 原理（抽取/存储/检索/注入）`
- 检索有效性 -> `4. Case13 效果验证`

## 1. 组件定位与对象模型
- 仓库: `https://github.com/letta-ai/letta`
- 本地代码: `/tmp/memory_scan_round2/letta`
- 本轮验证脚本: `/Users/admin/work/agent_loop/tests/research/memory/run_letta_case13_real.py`

核心对象（Letta 原生）：
- `agent`：带运行态状态与记忆能力的智能体对象。
- `archival memory`：长期记忆档案（可检索）。
- `passage`：档案层最小存储单元（本轮把 case13 每条消息写成 passage）。

## 2. 怎么用（最小调用）
本轮走 REST 方式：
1. 启动 Letta server
2. 创建 `archive`
3. 把 case13 对话逐条写入 passages
4. 用 case13 的 8 条查询逐条检索

完整实测输出原文：
- `/Users/admin/work/agent_loop/backups/memory/letta_case13_output.txt`

## 3. 原理（抽取/存储/检索/注入）
- 抽取：本轮不做额外 LLM 抽取，直接把原始对话写入 archival passage（保留原文）。
- 存储：写入 PostgreSQL + pgvector（脚本输出里的 `STORAGE SHAPE` 可见）。
- 检索：按 query 对 archive 做 `search`，返回命中的 passages。
- 注入：Letta 在完整 agent loop 中会把检索结果回注上下文；本轮脚本只验证“存 + 检索”模块。

## 4. Case13 效果验证
数据集：
- `/Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md`

结果（来自真实输出原文）：

| Query | items_hit | 结论 |
|---|---:|---|
| Query-1 | 0 | 未召回 |
| Query-2 | 0 | 未召回 |
| Query-3 | 0 | 未召回 |
| Query-4 | 0 | 未召回 |
| Query-5 | 0 | 未召回 |
| Query-6 | 0 | 未召回 |
| Query-7 | 0 | 未召回 |
| Query-8 | 0 | 未召回 |

关键证据（原文）在：
- `/Users/admin/work/agent_loop/backups/memory/letta_case13_output.txt`
  - `=== RETRIEVE CASE 1/8 ... === RETRIEVE RESULT === []`
  - `...`
  - `=== RETRIEVE CASE 8/8 ... === RETRIEVE RESULT === []`

## 5. 结论（只讲原理和效果）
- 组件形态上，Letta 的 memory 体系是完整且工程化的（stateful + archival）。
- 在本轮 Case13 脚本路径下，检索效果为 `0/8`（全部未命中）。
- 教学结论：Letta 值得用于“体系化 memory runtime”教学；但在特定检索链路下，需要进一步验证检索配置/索引策略后再做效果判断。
