# 记忆系统调研（大白话版）

这份文档只做一件事：  
把“记忆系统到底是啥、各家在干嘛、该怎么选”讲清楚。

---

## 1. 先说人话：记忆系统在解决什么问题

LLM 自己只记得“当前窗口里的内容”。  
窗口一满，前面说过的话就会变得不可靠，或者直接丢。

所以记忆系统本质是在补三件事：

1. 该记什么（抽取）
2. 记到哪里（存储）
3. 什么时候再拿出来（检索 + 注入）

一句话：  
`把“会忘”的模型，变成“有连续性”的 agent。`

---

## 2. 一个记忆系统最少要提供哪些能力

最小闭环是 6 步：

1. `extract`：从对话/工具结果里抽出可复用信息
2. `store`：落盘或入库
3. `index`：让后续能查到
4. `retrieve`：按 query 召回
5. `inject`：把召回结果塞回当前上下文
6. `update/evict`：更新冲突信息、淘汰旧信息

如果一个系统只做了“保存日志”，那还不叫完整记忆系统。

---

## 3. 记忆内容分哪几类（教学建议）

用 5 类最清楚：

- `Policy`：规则（比如“默认中文，别瞎编”）
- `Profile`：偏好（比如“先结论后细节”）
- `Fact`：事实（比如“API 地址是什么”）
- `Episode`：经历（比如“上次怎么修好的”）
- `Procedure`：方法（比如“发布 SOP”）

实操里常合并成 3 层：

- 规则层：`Policy + Profile`
- 知识层：`Fact + Episode`
- 方法层：`Procedure`

---

## 4. 主流系统到底在做什么（大白话对比）

| 系统 | 主要原理（大白话） | 提供的核心功能 | 优势 | 劣势 |
|---|---|---|---|---|
| Claude Code / OpenCode / Codex（这类 code agent） | 主要靠规则文件（`CLAUDE.md` / `AGENTS.md`）维持长期记忆 | 规则注入、会话连续、上下文压缩 | 简单、稳定、可审计 | 自动抽取事实/偏好能力弱，更多靠人维护 |
| OpenClaw | 固定注入 + 按需检索（`MEMORY.md` + memory tools） | memory 检索、flush、compaction | 工程可控，教学友好 | 默认抽取质量依赖提示词与索引 |
| Claude-mem | 把开发过程变成 observation，然后按需检索回填（MCP） | observation 捕获、压缩、search/get_observations | 对 Claude Code 场景非常顺手，渐进披露省 token | 生态绑定强，跨框架迁移有成本 |
| Mem0 | 标准“抽取-检索-更新”流水线服务 | add/search/update/delete、策略化更新 | 接口清晰，产品接入快 | 抽取错会污染，规则治理要外补 |
| Letta / MemGPT | 分层记忆（working/core/archival） | 分层记忆管理、memory CRUD、迁移与召回 | 体系完整，适合长期自治 agent | 实现和运维都偏重 |
| Zep / Graphiti | 把记忆做成时序图谱 | 图检索、关系推理、时间演化 | 多跳关系和时序问题强 | 系统复杂，维护成本高 |
| SimpleMem / Supermemory | 轻量记忆服务路线 | 压缩、检索、更新、重排（Supermemory 还做关系更新） | 上手快、接入快 | 深层推理和复杂治理能力有限 |
| EverMemOS | Memory OS 路线（编码-巩固-检索） | 分层治理、生命周期管理 | 企业级长期运行思路完整 | 太重，不适合教学起步 |
| OpenViking | 把 memory/resources/skills 统一成“上下文文件系统” | 分层加载（L0/L1/L2）、可观测检索轨迹 | 可解释性强，调试友好 | 生态早期，成熟度还在增长 |

---

## 5. 哪类系统适合你（直接给结论）

### 5.1 教学仓库 / 先跑通

优先：规则文件 + 轻量检索  
建议：`OpenClaw 风格` 或 `Mem0 风格的轻量版本`

原因：  
能解释、能调试、能迭代，不会一上来就被复杂度拖死。

### 5.2 代码助手（cc/oc/codex 类）

优先：`Policy/Profile + 项目 Fact`  
做法：规则文件为主，自动抽取为辅

原因：  
代码场景里“稳定规则”和“项目事实”比“花哨记忆”更值钱。

### 5.3 个人通用助手

优先：`Profile + Fact + Episode`  
做法：固定回合检索 + 逐步自动抽取

原因：  
用户最在意的是“你记不记得我”，不是“你用了什么 fancy 架构”。

---

## 6. 常见误区（最容易踩坑）

### 误区 1：把“日志落盘”当“记忆系统”

只存不检索、不更新，就是历史记录，不是记忆闭环。

### 误区 2：一上来做全自动抽取

早期最容易污染。  
建议先用“候选记忆 + 人工确认”过渡。

### 误区 3：不区分短期和长期

短期负责当前任务跑通，长期负责跨会话延续。  
两者混在一起，系统很快失控。

### 误区 4：以为“模型会自己记住”

模型不会长期记住，必须靠外部存储 + 检索注入机制。

---

## 7. 对本仓库的落地建议（v6.2）

按这个顺序最稳：

1. 先做可解释长期记忆：`policy/profile/fact/procedure` 文件化
2. 再做固定检索注入：每轮 pre-turn 检索 top-k 注入
3. 再做 post-turn 更新：抽取候选 -> 更新/冲突处理
4. 最后做自动治理：逐出、去重、关系链接、质量评测

一句话：  
`先把闭环跑稳，再追求智能化。`

---

## 8. 参考（入门够用）

- Claude Code Memory: <https://docs.anthropic.com/en/docs/claude-code/memory>
- OpenClaw Memory: <https://docs.openclaw.ai/concepts/memory>
- Claude-mem: <https://github.com/thedotmack/claude-mem>
- Mem0 Docs: <https://docs.mem0.ai/>
- Letta / MemGPT: <https://docs.letta.com/guides/agents/architectures/memgpt>
- Zep Graphiti: <https://github.com/getzep/graphiti>
- OpenViking: <https://www.openviking.ai/>
- Supermemory Docs: <https://docs.supermemory.ai/>
