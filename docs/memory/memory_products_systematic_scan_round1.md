# Memory 系统化调研（Round 1）

目标：按指定顺序，对 10 个 memory 相关项目做同一套流程：
1. 拉代码（源码可得性）
2. 读实现（关键模块与流程）
3. 最小验证（本机可执行性）
4. 形成结论（适用性、风险、下一步）

本轮范围：
- Mem0
- OpenClaw Memory
- Claude-mem
- SimpleMem
- EverMemOS
- Zep
- Supermemory
- Letta / MemGPT
- OpenViking
- memos

---

## 0. 统一验证协议（本轮实际执行）

- 代码获取：`git clone --depth 1 <repo>`
- 静态定位：`rg` 检索 memory 核心文件、README、API/SDK 接口
- 运行验证（最小 smoke）：
  - Python 项目：尝试核心模块 import
  - Go 项目：尝试最小 `go test`（若本机有 Go）
  - TS/Bun 项目：仅做源码级验证（本轮未安装全量依赖）

本机真实运行结果（节选）：
- `mem0` import 失败：`PackageNotFoundError: No package metadata was found for mem0ai`
- `SimpleMem` import 失败：`ModuleNotFoundError: No module named 'openai'`
- `EverMemOS` import 失败：`ModuleNotFoundError: No module named 'jieba'`
- `letta` import 失败：`ModuleNotFoundError: No module named 'yaml'`
- `OpenViking` import 失败：`ModuleNotFoundError: No module named 'fastapi'`
- `zep` integration import 失败：`ZepDependencyError: AutoGen dependencies not found`
- `memos` Go 验证失败：`go: command not found`

说明：本轮“运行验证”以可执行性探测为主，不代表项目不可用，只表示当前机器缺少其运行依赖。

---

## 1) Mem0

- 仓库：`https://github.com/mem0ai/mem0`
- 本地 commit：`93c7203`
- 关键实现入口：
  - `mem0/memory/main.py`（`Memory.add / search`）
  - `mem0/client/main.py`（client SDK）
  - `mem0/memory/graph_memory.py`（图记忆）

### 原理（基于源码）
- 统一 `Memory` 对象聚合了：LLM 抽取、embedding、vector store、可选 graph store。
- 写入：`add(...)` 侧重“从消息中抽取记忆并结构化存储”。
- 检索：`search(...)` 走向量检索（可带 filters），可叠加 graph 侧能力。
- 特征：存储后端与模型层可替换（工厂模式）。

### 最小验证
- 源码成功拉取。
- 运行探测：核心模块 import 失败（环境缺包/未安装项目元数据）。

### 结论
- 可作为“可插拔后端 + SDK 友好”的长期记忆基座。
- 下一轮若做深测，需要单独建虚拟环境并按其官方安装路径装全依赖。

---

## 2) OpenClaw Memory

- 仓库：`https://github.com/openclaw/openclaw`
- 本地 commit：`84a88b2`
- 关键实现入口：
  - `src/agents/memory-search.ts`
  - `src/auto-reply/reply/memory-flush.ts`
  - `docs/concepts/memory.md`

### 原理（基于源码）
- 内存模型是“文件 + 可选向量索引”双轨：
  - 文件侧：`MEMORY.md` + `memory/*.md`
  - 检索侧：memory search（SQLite 索引 + embedding provider）
- `memory_flush` 机制在 compaction 前触发，提示模型将“可长期保留信息”写入 memory 文件。
- `memory_search` 配置支持 provider/fallback/chunking/时序衰减等参数。

### 最小验证
- 源码成功拉取。
- 本轮未跑 TS 测试（未安装 pnpm/bun 依赖树），做了源码级流程验证。

### 结论
- 偏“工程可控”的产品方案：文件可审计，检索可配置。
- 非“自动抽取为主”的黑盒记忆，而是“可控落盘 + 检索增强”。

---

## 3) Claude-mem

- 仓库：`https://github.com/thedotmack/claude-mem`
- 本地 commit：`ecb09df`
- 关键实现入口：
  - `src/services/worker/SearchManager.ts`
  - `src/services/sqlite/Database.ts`
  - `src/servers/mcp-server.ts`

### 原理（基于源码）
- 架构分层明显：
  - worker（搜索编排）
  - SQLite（结构化 observation/session）
  - Chroma（语义检索）
  - MCP server（对外工具协议包装）
- 检索策略：SQLite 过滤 + Chroma 语义 + timeline 拼接，强调 token-efficient 的分层检索（先 search 再 timeline 再详情）。
- 数据模型是 observation 驱动，不是直接 message 原文索引。

### 最小验证
- 源码成功拉取。
- 本轮未跑 bun test（依赖未安装），做了核心链路静态验证。

### 结论
- 在“可用性工程”上很成熟，尤其是 observation 与分层检索设计。
- 适合作为“插件型长期记忆服务”的参考。

---

## 4) SimpleMem

- 仓库：`https://github.com/aiming-lab/SimpleMem`
- 本地 commit：`7da777f`
- 关键实现入口：
  - `core/memory_builder.py`
  - `core/hybrid_retriever.py`
  - `cross/README.md`

### 原理（基于源码）
- 三阶段主线：
  - Stage1 语义压缩（memory unit 构建）
  - Stage2 在线语义合并（去冗余）
  - Stage3 意图感知检索（semantic/keyword/structured 混合）
- 近期开启 cross-session 能力，支持 MCP 工具化接口。

### 最小验证
- 源码成功拉取。
- 运行探测：缺 `openai` 依赖，无法直接 import 核心模块。

### 结论
- 学术风格很强，pipeline 设计完整。
- 适合做“压缩+检索联动”教学样本，但部署依赖较重。

---

## 5) EverMemOS

- 仓库：`https://github.com/EverMind-AI/EverMemOS`
- 本地 commit：`1f2f083`
- 关键实现入口：
  - `src/agentic_layer/memory_manager.py`
  - `demo/simple_demo.py`
  - `docs/STARTER_KIT.md`

### 原理（基于源码）
- 明确声明 Encoding / Consolidation / Retrieval 三段流程。
- 数据与基础设施偏“生产后端化”：MongoDB + Elasticsearch + Milvus + Redis。
- API 风格清晰：`/api/v1/memories`（写入）+ `/api/v1/memories/search`（检索）。

### 最小验证
- 源码成功拉取。
- 运行探测：缺 `jieba` 等依赖，未做全栈启动验证。

### 结论
- 偏“后端平台型 memory system”，适合服务化部署，不适合轻量本地即插即用。

---

## 6) Zep

- 仓库：`https://github.com/getzep/zep`
- 本地 commit：`1e8bb6d`
- 关键实现入口：
  - `README.md`（Graphiti/temporal KG）
  - `integrations/python/zep_autogen/src/zep_autogen/memory.py`
  - `examples/typescript/memory/memory_example.ts`

### 原理（基于源码）
- 核心是 temporal graph memory：关系带 `valid_at / invalid_at` 时间语义。
- 集成层向外暴露 Memory 接口（如 AutoGen 适配），支持 query 后把 memory context 注入系统消息。
- 与传统“向量库只存 chunk”不同，强调关系与时间演化。

### 最小验证
- 源码成功拉取。
- 运行探测：缺 AutoGen 相关依赖，导入集成模块失败。

### 结论
- 强项是“时间感知关系记忆”，适合长期演化场景。
- 本地快速复现实验门槛高于纯文件/纯向量方案。

---

## 7) Supermemory

- 仓库：`https://github.com/supermemoryai/supermemory`
- 本地 commit：`3a36a67`
- 关键实现入口：
  - `packages/lib/api.ts`
  - `packages/tools/src/shared/memory-client.ts`
  - `packages/tools/src/claude-memory.ts`

### 原理（基于源码）
- 强 API 产品化：`/v3/documents`、`/v3/search` 等接口定义完整。
- 工具侧有“对外适配器”思路（例如 Claude memory tool），将 memory 抽象成统一操作（view/create/replace/insert/delete）。
- 注重多端接入（web/extension/raycast/MCP）。

### 最小验证
- 源码成功拉取。
- 本轮未跑依赖安装与集成测试（monorepo 依赖体量较大），完成了接口与工具链静态核对。

### 结论
- 明显偏“产品层 memory API 平台”，不是单纯算法库。
- 适合做“工程接入”样本，不适合直接对比学术 benchmark pipeline。

---

## 8) Letta / MemGPT

- 仓库：`https://github.com/letta-ai/letta`
- 本地 commit：`1b2aa98`
- 关键实现入口：
  - `README.md`
  - `letta/agents/letta_agent_v3.py`
  - `letta/schemas/memory.py`

### 原理（基于源码）
- 明确“stateful agent”定位：有内存块、对话记忆裁剪、archival memory 检索工具。
- 当上下文受限时，会触发消息隐藏/压缩，并保留可检索的长期记忆通道。
- 在 agent loop 内把 memory 作为一级对象，而非外挂缓存。

### 最小验证
- 源码成功拉取。
- 运行探测：缺 `yaml` 等依赖，未完成本机可执行。

### 结论
- 设计理念和 MemGPT 一致：把 memory 当 agent runtime 基础设施。
- 实现复杂度高，适合做“完整体系”参考，不适合轻量复制。

---

## 9) OpenViking

- 仓库：`https://github.com/volcengine/OpenViking`
- 本地 commit：`fac6068`
- 关键实现入口：
  - `README.md`
  - `openviking/session/compressor.py`
  - `openviking/session/memory_extractor.py`

### 原理（基于源码）
- 主张“文件系统范式”：`viking://` 统一管理 memory/resource/skill。
- session 结束触发 memory self-iteration：抽取候选记忆、去重、合并、建立 memory↔resource/skill 关系。
- 内置会话压缩 + 长期记忆抽取 + 向量化入库队列。

### 最小验证
- 源码成功拉取。
- 运行探测：缺 `fastapi` 依赖，核心模块 import 失败。

### 结论
- 架构表达非常完整，适合教学“统一上下文文件系统 + 记忆演化”。
- 实际部署依赖较多，需要专门环境。

---

## 10) memos

- 仓库：`https://github.com/usememos/memos`
- 本地 commit：`664b8c5`
- 关键实现入口：
  - `README.md`
  - `server/router/mcp/tools_memo.go`

### 原理（基于源码）
- 本质是知识笔记系统（notes/wiki），不是 agent 长期记忆引擎。
- 有 MCP 搜索工具，但能力中心是 memo 内容管理与全文搜索，不是“记忆抽取-更新-逐出”闭环。

### 最小验证
- 源码成功拉取。
- Go 运行验证失败：本机无 `go`。

### 结论
- 可作为“外部知识库”或 memory backend 的一部分。
- 不建议直接当作完整 agent memory system 对标 mem0/Letta/OpenViking。

---

## 汇总结论（本轮）

### A. 源码可得性
- 10/10 均可获取并完成核心文件定位。

### B. 可运行性（本机）
- 0/10 完成“全功能端到端验证”。
- 主要阻塞是环境依赖（Python 包、Go 工具链、Node/Bun 依赖树、外部服务）。

### C. 从“教学可解释性”看，当前优先级建议
1. OpenClaw Memory（文件+检索+flush，工程直观）
2. Mem0（SDK 直观，生态广）
3. OpenViking（统一文件系统范式，概念完整）
4. Letta（体系最完整，但复杂）
5. Zep（时间图谱强，但门槛高）
6. SimpleMem / EverMemOS（偏研究或后端平台）
7. Supermemory（产品 API 强）
8. Claude-mem（插件化参考强）
9. memos（偏知识库，不是完整 memory 引擎）

---

## 下一轮建议（可直接执行）

- 先做 3 个深测：`Mem0 -> OpenClaw Memory -> OpenViking`
- 每个项目固定产出 4 件：
  1. 最小可运行脚本（写入 + 查询）
  2. 一份真实输入输出日志（不截断）
  3. 失败案例与边界（误召回、漏召回、冲突）
  4. 与统一 Case13 的对比分数（同口径）

