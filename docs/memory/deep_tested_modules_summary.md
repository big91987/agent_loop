# 已深测记忆模块总览（教学汇总）

## 1. 这份文档干什么

这份文档只汇总“我们已经做过真实脚本验证”的 memory 模块，不讲泛泛概念。  
目标是回答三个问题：
1. 这个模块最核心的机制是什么。  
2. 它的真实优势在哪里。  
3. 在 Case13 这种长对话场景里，它的主要短板和边界是什么。  

---

## 2. 覆盖范围与完成度

| 模块 | 实测状态 | 说明 |
|---|---|---|
| MemU | 已深测 | 跑过真实 memorize/retrieve，输出完整日志 |
| Mem0 | 已深测 | Case13 真实验证完成 |
| OpenClaw Memory | 已深测 | Case13 真实验证完成 |
| Claude-mem | 已深测 | Case13 真实验证完成 |
| SimpleMem | 已深测 | Case13 真实验证完成 |
| OpenViking | 已深测 | Case13 真实验证完成 |
| Letta / MemGPT | 已深测（当前配置效果弱） | 脚本跑通，但本轮检索命中差 |
| memos | 已深测（当前策略效果弱） | 脚本跑通，但关键词 contains 检索弱 |
| EverMemOS | 部分完成 | 机制和链路已深挖，Case13 全量结果仍在调优阶段 |

未纳入本汇总主结论：
- Zep（依赖未齐）
- Supermemory（凭证缺失）

---

## 3. 核心机制与优势总表（重点，讲人话版）

| 模块 | 对象模型/核心名词（讲人话） | 核心机制（讲人话） | 最大优势（讲人话） | 主要短板（当前实测） | 适用场景 |
|---|---|---|---|---|---|
| MemU | `resource/item/category`：先有资源，再抽成记忆条目，再归到主题类目。 | 先把对话拆成结构化记忆条目，再按“要不要查记忆、查到够不够”分层检索。 | 最像“可治理记忆系统”：分类清楚、流程完整、可配项多。 | 配置和调参复杂；某些 query 会被 route 阶段误判成“不需要检索”。 | 中大型 agent，重视长期记忆质量和治理能力。 |
| Mem0 | `memory + event + scope`：记忆项有生命周期动作（增/改/删），且有作用域。 | 先抽事实，再对记忆做动作（新增/更新/删除），检索时按 user/agent/run 作用域查。 | 接入快、效果稳，适合“先把长期记忆跑起来”。 | 如果不设计 metadata，容易“能召回但不够干净”。 | 快速把业务 agent 从无记忆升级到有长期记忆。 |
| OpenClaw Memory | `MEMORY.md + memory/*.md + snippet`：记忆本体是 Markdown，检索返回片段。 | 把记忆当 Markdown 文件维护，再做片段检索。 | 最容易人工维护和审计，产品可解释性强。 | 容易宽召回，结果常带无关上下文。 | 个人助手、开发工具，强调“人可以直接改记忆”。 |
| Claude-mem | `observation`：每条记忆是结构化观察对象，落 SQLite/Chroma。 | 先把对话整理成 observation，再落 SQLite/Chroma 双存储检索。 | 结构化和工程复杂度平衡好，链路清晰。 | 当前实测中，查询区分度一般，偏向近期内容。 | 需要结构化记忆、又不想系统过重的助手产品。 |
| SimpleMem | `memory entry`：字段化条目（topic/keywords/time 等）作为最小单位。 | 先过滤低价值内容，再把高价值内容原子化为 entry，最后检索。 | 抽取质量高，条目可读性非常好，教学价值高。 | 本轮检索偏宽，精排优势还没被强证据证明。 | 教学/研究场景，强调“先抽好，再检索”。 |
| OpenViking | `viking://.../memories/*`：记忆是路径空间下的文件对象。 | 会话提交后自动抽取成 memory 文件，放进统一 `viking://` 路径空间。 | “抽取+存储+检索”一体化，路径化组织直观。 | 根目录检索时结果偏宽，需要更细粒度约束。 | 想把 memory 当“上下文数据库”统一管理的系统。 |
| Letta / MemGPT | `agent state + archival passages`：运行态记忆 + 档案态记忆双层。 | 记忆是 agent runtime 内建能力（运行态 + 档案态双层）。 | 架构上最接近“原生有记忆的 agent”。 | 本轮 case13 检索命中差（0/8），配置仍需深调。 | 强调 agent runtime 一体化的长期项目。 |
| memos | `memo`：一条 memo 就是一条记忆文本笔记。 | 把记忆当笔记存下来，靠文本过滤检索。 | 部署简单、改起来方便、审计成本低。 | 对自然语言 query 检索弱，单独用很难当“智能记忆引擎”。 | 适合作为外部记忆仓，不适合单独承担记忆推理。 |
| EverMemOS | `MemCell -> episode/event_log/foresight/profile`：先形成记忆段，再抽多类对象。 | 先判定“是否到分段边界”，产出 MemCell 后再做多类型抽取与检索。 | 最大亮点是“何时写入”有一级控制，不是每条消息都盲存。 | 全量 Case13 仍在调优；触发策略和耗时需要继续打磨。 | 生产级记忆中台，前提是基础设施和链路配置齐全。 |

---

## 4. 已验证出的共性结论（跨模块）

1. 抽取得好，不代表检索一定好。  
- SimpleMem、OpenViking 都验证了“抽取覆盖高”，但检索层仍可能宽召回。  

2. “对象模型清晰度”决定工程可治理性。  
- MemU/Mem0/Claude-mem 这类结构化模型更容易做策略治理。  
- OpenClaw/memos 这类文本源模型更容易人工编辑，但精检索依赖上层工程。  

3. 检索效果最容易被低估的环节是“query 处理”。  
- 不做 query rewrite / route / sufficiency，很多系统会出现“能搜到但不精准”或“直接 0 命中”。  

4. 记忆系统评估应先看触发机制，再看召回分数。  
- EverMemOS 这类有 boundary 的系统，若没触发 memcell，后面指标没有解释力。  

---

## 5. 从教学角度的推荐分层

建议按三层教学：

1. 入门层（先理解记忆是什么）  
- OpenClaw Memory + memos  
- 重点：可编辑事实源、存储与检索的基本关系。  

2. 工程层（可控长期记忆）  
- Mem0 + Claude-mem  
- 重点：结构化对象、scope、检索路由、可观测性。  

3. 进阶层（机制导向与中台化）  
- MemU + SimpleMem + OpenViking + EverMemOS  
- 重点：抽取策略、对象体系、检索编排、系统边界条件。  

---

## 6. 对你当前 repo 的直接建议

1. 把 Case13 作为统一回归基准保留。  
2. 每个模块报告统一保留三块证据：  
- 抽取结果原文  
- 存储形态（文件/DB/集合）  
- Query-1..8 命中原文  
3. 在总览里区分“机制跑通”和“效果优秀”，避免混为一谈。  

---

## 7. 参考报告（已完成）

- `/Users/admin/work/agent_loop/docs/memory/memory_product_memu.md`
- `/Users/admin/work/agent_loop/docs/memory/products/01_mem0.md`
- `/Users/admin/work/agent_loop/docs/memory/products/02_openclaw_memory.md`
- `/Users/admin/work/agent_loop/docs/memory/products/03_claude_mem.md`
- `/Users/admin/work/agent_loop/docs/memory/products/04_simplemem.md`
- `/Users/admin/work/agent_loop/docs/memory/products/05_evermemos.md`
- `/Users/admin/work/agent_loop/docs/memory/products/08_letta_memgpt.md`
- `/Users/admin/work/agent_loop/docs/memory/products/09_openviking.md`
- `/Users/admin/work/agent_loop/docs/memory/products/10_memos.md`
