# 长期记忆设计说明（教学版）

本文聚焦“长期记忆（Long-term Memory）”，用于统一我们之前对 Mem0、Letta/MemGPT、Zep/Graphiti、SimpleMem、Supermemory、EverMemOS、MemU、OpenViking、Claude-mem 以及 OpenClaw/oc/cc 的调研结论。

## 1. 先讲清边界

- 短期记忆：解决“这次会话能不能跑完”（上下文窗口、压缩、回填）。
- 长期记忆：解决“下次还能不能记住”（跨会话复用、更新、冲突治理）。

对教学仓库来说，v6.1 已覆盖短期记忆；v6.2 主要引入长期记忆闭环。

## 2. 长期记忆的对象模型（建议教学标准）

建议按对象分 5 类：

- `Policy`：规则与约束（如“默认中文回答、不要推测”）
- `Profile`：用户偏好（如“偏好表格、喜欢先结论后细节”）
- `Fact`：稳定事实（如“项目 API 基址、组织结构、常量”）
- `Episode`：关键经历（如“某次排障过程与结论”）
- `Procedure`：可复用方法（如“发布 SOP、排障 checklist”）

按动态性看：

- 静态：`Policy`、部分 `Profile`
- 半动态：`Fact`
- 动态：`Episode`、`Procedure`

## 3. 主流方案对比（长期记忆视角）

| 系统 | 核心思路 | 擅长 | 弱项/代价 | 适合场景 |
|---|---|---|---|---|
| Mem0 | 抽取-存储-检索-更新（CRUD）服务化 | Fact/Profile 自动治理、接口清晰 | 抽取错误会污染；Policy 仍需外层治理 | 助手/客服/CRM |
| MemU | 三层文件化记忆（Resource/Item/Category）+ agentic memory 管理 | 文件透明、可审计、跨模型共享友好 | 产品化形态较重；策略细节与评测公开度有限 | 教学与工程过渡、文件范式记忆 |
| Letta/MemGPT | working/core/archival 分层 | 长周期代理、层次清晰 | 系统复杂度和运维成本高 | 长运行自主代理 |
| Zep/Graphiti | 时序图谱记忆 + 图检索 | 关系/时序推理强 | 建设与维护复杂 | 关系密集任务 |
| SimpleMem | 压缩提炼 + 检索回填 | 成本友好、实现相对轻 | 复杂关系治理较弱 | 成本敏感产品 |
| Supermemory | API 化记忆层 + 关系更新 | 接入快、工程落地快 | 深层策略依赖外层编排 | 需要快速接入记忆能力 |
| EverMemOS | Memory OS（编码/巩固/检索） | 长期治理体系完整 | 体系重，上手门槛高 | 企业级长期知识系统 |
| OpenViking | 上下文数据库（memory/resources/skills 统一为文件系统路径） | 目录层级检索、可观测路径、分层加载（L0/L1/L2） | 生态仍在发展，社区资料相对少 | 需要“上下文可观测+层级加载”的 agent 系统 |
| Claude-mem | Claude Code 场景的 observation 记忆层 | 自动捕获会话观察、压缩与按需检索（MCP） | 生态绑定 Claude Code，通用迁移成本存在 | Claude Code 长会话连续性增强 |
| OpenClaw（当前） | 文件记忆 + 检索增强（含 QMD/Hybrid） | 工程可控、可审计、可渐进增强 | 仍需策略层定义抽取与更新规则 | 个人助手/网关式 agent |

## 4. 长期记忆组件应提供的标准能力

最小接口建议：

- `add(memory_item)`
- `search(query, scope, top_k)`
- `update(memory_id, patch)`
- `delete(memory_id)`
- `list(filter)`

治理接口建议：

- `resolve_conflict(old, new)`
- `evict(policy)`（按时效、置信度、冲突状态）
- `link(a, b, relation)`（可选，关系图谱方向）

## 5. 在 agent loop 中的标准位置

建议固定两段，不依赖模型“自发想起来”：

1. 回合前（读）  
`user_query -> memory.search -> top-k 注入 system/context`

2. 回合后（写）  
`turn_result -> memory extraction -> add/update/delete`

这样能保证稳定性和可观测性；后续再增加“模型自主调用 memory tool”作为增强。

## 6. 对本仓库 v6.2 的建议（教学优先）

### 6.2 第一阶段（先做清晰闭环）

- 存储先用文件（透明可审计）：
  - `memory/long/policy.jsonl`
  - `memory/long/profile.jsonl`
  - `memory/long/fact.jsonl`
  - `memory/long/procedure.jsonl`
- 检索先做关键词/规则打分（不先引入向量库）
- 写入先做“候选 + 可确认”模式，降低污染风险

### 6.2 第二阶段（再做增强）

- 接入 embedding + hybrid search
- 加冲突合并与逐出策略
- 增加跨 session 的 scope（global/project/session）

## 7. 一句话结论

教学仓库里，长期记忆最重要的不是“先上最复杂框架”，而是先把以下链路做稳：

`可读的记忆对象 -> 可解释的检索注入 -> 可回滚的更新治理`

这条链路跑通后，再替换后端（例如向量库/QMD/图谱）成本最低。

## 8. 这次补充调研（MemU / OpenViking / Claude-mem）

### 8.1 MemU（偏“文件化 + agentic memory”）

- 结构主张：`Resource -> Item -> Category` 三层记忆，并强调文件可读性（markdown/text-first）。
- 检索主张：同时支持 embedding 检索与“直接语义读取”（非纯向量范式）。
- 教学价值：和我们当前“文件透明可维护”方向一致，适合作为长期记忆入门案例。
- 采用建议：可借鉴它的三层对象建模，但实现上先保持轻量（本地 jsonl/md + 简单检索）。

### 8.2 OpenViking（偏“上下文数据库”）

- 核心主张：将 memory/resources/skills 统一为“文件系统路径空间”（如 `viking://`）。
- 检索主张：目录层级检索 + 语义检索，支持分层加载（L0/L1/L2）减少一次性注入。
- 可观测性：强调检索轨迹可视化，方便调试“为什么命中/没命中”。
- 采用建议：其“分层加载 + 路径可观测”理念对 v6.2 之后演进很有价值，可作为后续增强方向。

### 8.3 Claude-mem（偏“Claude Code observation memory”）

- 核心主张：将开发过程中的 observation（决策、上下文、结果）结构化持久化，供后续回合和跨会话复用。
- 检索主张：通过 MCP 工具（如 search/get_observations）按需召回，不把全部历史一次性塞进窗口。
- 教学价值：非常适合讲“渐进披露”的长期记忆注入策略，和我们 v5 skill/mcp 体系衔接自然。
- 采用建议：可借鉴它的 observation 粒度与按需检索方式，但保持存储透明（本地 md/jsonl）便于教学与审计。

## 9. 参考链接（长期记忆专题）

- MemU: https://github.com/NeuralInternet/memu
- OpenViking: https://www.openviking.ai/
- OpenViking (PyPI): https://pypi.org/project/openviking/
- Claude-mem (GitHub): https://github.com/thedotmack/claude-mem
- Claude-mem (Docs): https://docs.claude-mem.ai/introduction
