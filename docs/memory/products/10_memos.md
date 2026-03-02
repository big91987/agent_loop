# memos 调研报告（Case13 实测版）

## 0. README亮点（先看这个）
- `Self-hosted`：单二进制即可部署，数据可控。
- `memo` 为核心对象：写入/管理/过滤检索。
- `MCP tools`：可作为外部知识层给 agent 调用。

亮点 -> 本文章节：
- memo 对象模型 -> `1. 组件定位与对象模型`
- API 使用方式 -> `2. 怎么用（最小调用）`
- 检索效果 -> `4. Case13 效果验证`

## 1. 组件定位与对象模型
- 仓库: `https://github.com/usememos/memos`
- 本地代码: `/tmp/memory_scan_round2/memos`
- 本轮验证脚本: `/Users/admin/work/agent_loop/tests/research/memory/run_memos_case13_real.py`

核心对象（memos 原生）：
- `memo`：最小存储单元（markdown 文本笔记）。
- `user`：作用域主体；memo 读写按用户权限隔离。
- `filter`：列表检索表达式（例如 `content.contains("...")`）。

## 2. 怎么用（最小调用）
本轮真实调用流程：
1. 启动 memos server
2. 创建首个用户（ADMIN）
3. 登录拿 `accessToken`
4. 把 case13 每条消息写为一条 memo
5. 对 case13 的 8 条查询执行检索

完整实测输出原文：
- `/Users/admin/work/agent_loop/backups/memory/memos_case13_output.txt`

## 3. 原理（抽取/存储/检索/注入）
- 抽取：不做 LLM 抽取；本轮直接保存原始对话文本。
- 存储：SQLite（`memos_prod.db`）持久化。
- 检索：`ListMemos` + filter（`content.contains(query)`）。
- 注入：memos 本身不负责注入到模型；通常由上层 agent/mcp client 把检索结果回注到 prompt。

## 4. Case13 效果验证
数据集：
- `/Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md`

实测摘要（真实输出）：
- `created_memos=62`
- Query-1..8 均 `items_hit=0`

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
- `/Users/admin/work/agent_loop/backups/memory/memos_case13_output.txt`
  - `=== MEMORIZE RESULT ===` 下 `created_memos=62`
  - `=== RETRIEVE CASE 1/8 ... items_hit=0`
  - `...`
  - `=== RETRIEVE CASE 8/8 ... items_hit=0`

## 5. 结论（只讲原理和效果）
- memos 更像“外部知识库/笔记系统”，不是完整自动化长期记忆引擎。
- 在 case13 场景下，直接用整句 query 做 `content.contains` 检索，效果为 `0/8`。
- 教学结论：memos 适合作为“可编辑、可审计、可持久化”的外部记忆存储层；若要做 agent 长期记忆，需要在上层增加抽取、重写查询、排序与注入策略。
