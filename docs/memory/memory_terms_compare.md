# Memory 原生术语对照（不要拿 MemU 套所有系统）

这页只做一件事：把每个系统自己的“名词体系”和“可配置边界”讲清楚。  
`item/type/category` 是 **MemU 的原生结构**，不是通用标准。

## 1. 各系统原生对象模型（Native Model）

| 系统 | 原生记忆对象（它自己怎么叫） | 组织方式（它自己怎么分） | 用户可配置边界 |
|---|---|---|---|
| MemU | `item` | `type` + `category` + relations | **强可配**：`memory_types` / `memory_categories` 可配；新增 type 通常要配对应 prompt |
| Mem0 | `memory`（文本记忆项） | 以 action 生命周期管理：`ADD/UPDATE/DELETE`；检索靠 scope + metadata/filter | **中可配**：metadata/filter/rerank/后端可配；没有 MemU 式固定 `type/category` 双层 |
| OpenClaw Memory | Markdown 记忆片段（`snippet/chunk`） | 文件是事实源（`MEMORY.md` + `memory/*.md`），检索返回原文片段 | **弱到中**：主要靠文件组织与检索参数；无内建结构化类型系统 |
| Claude-mem | `observation` | observation schema（title/narrative/facts/concepts/type 等）+ SQLite/Chroma 路由 | **工程可配**：可通过 mode/prompt/schema 调整；不是运行时简单改几项配置 |
| SimpleMem | `memory entry` | entry 字段组织（`lossless_restatement/topic/keywords/timestamp/location/...`） | **中可配**：字段框架相对固定，策略和 prompt 可调，但不是显式 type/category 体系 |
| OpenViking | `memory file`（`viking://.../memories/...`） | 目录/文件分层（如 profile/preferences/entities/events）+ 索引检索 | **工程可配**：可改策略和结构，但默认是文件分层模型，不是 item-type-category 模型 |

## 2. 一句话防混淆

- MemU 是“对象模型驱动”（item/type/category）。
- Mem0 是“动作生命周期驱动”（ADD/UPDATE/DELETE）。
- OpenClaw 是“文件事实源驱动”（Markdown 片段检索）。
- Claude-mem 是“observation 驱动”（先 observation 再检索）。
- SimpleMem 是“entry 字段驱动”（结构化 entry）。
- OpenViking 是“memory file + 路径空间驱动”（viking:// 分层）。

## 3. 比较时应该对齐什么

横向比较不要问“有没有 type/category”，而是问：
1. 这个系统最小记忆对象叫什么？
2. 它按什么机制组织和检索？
3. 用户能改哪些层（配置层、prompt 层、代码层）？
