# Memory Research Scripts

本目录只放 memory 调研验证脚本。

## MemU（真实测试）

- 脚本：`run_memu_rich_demo_real.py`
- 用途：真实模型调用，从 benchmark Markdown 解析指定 Case，对话写入临时 JSON 后执行 memorize/retrieve，并打印完整输入对话、retrieve 请求、结果；支持单条查询和多条“日常习惯”召回 case。
- 默认测试集：`data/agent_memory_case13_shared.md`（共享 Case 13 基准）
- 默认 Case：`auto`（在共享文件里即 `Case 13`）

运行命令：

```bash
export MINIMAX_API_KEY='...'
export ZHIPU_API_KEY='...'
conda run -n py312 python /Users/admin/work/agent_loop/tests/research/memory/run_memu_rich_demo_real.py \
  --config /Users/admin/work/agent_loop/configs/default.json \
  --benchmark-path /Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md \
  --benchmark-case "auto" \
  --retrieve-query-set daily_habits \
  --embed-base-url https://open.bigmodel.cn/api/paas/v4 \
  --embed-model embedding-3
```

常用参数：

- `--benchmark-case`: 选择测试集 Case（默认 `auto`；共享文件里就是 `Case 13`）
- `--benchmark-max-messages`: 限制导入轮数（默认 `80`）
- `--retrieve-query-set`: `single` 或 `daily_habits`（后者优先读取测试集里 `触发查询 (Query)-N` 条目）
- `--retrieve-query`: 指定单条检索问题（仅 `--retrieve-query-set single` 时使用）
- `--max-retrieve-cases`: 多 case 模式下限制执行数量（默认 `0` 表示全部）
- `--print-limit`: 输出条目上限（默认 `0` 表示全部打印）

输出归档：

- `/Users/admin/work/agent_loop/backups/memu/runs/memu_rich_demo_real_output.txt`

## Mem0（真实测试）

- 脚本：`run_mem0_rich_demo_real.py`
- 用途：对齐 MemU 的 Case13 测试方式，读取同一测试集，执行 `mem0.add`（memorize）+ 多 query `mem0.search`，完整打印输入对话、memorize 请求与结果、每个 query 的检索结果。
- 默认测试集：`data/agent_memory_case13_shared.md`

运行命令：

```bash
export MINIMAX_API_KEY='...'
export ZHIPU_API_KEY='...'
/Users/admin/miniconda3/envs/py312/bin/python /Users/admin/work/agent_loop/tests/research/memory/run_mem0_rich_demo_real.py \
  --config /Users/admin/work/agent_loop/configs/default.json \
  --benchmark-path /Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md \
  --benchmark-case auto \
  --retrieve-query-set daily_habits
```

常用参数：

- `--embed-dims`: 显式指定 embedding 维度（>0 时跳过自动探测）
- `--mem0-dir`: 指定 `MEM0_DIR` 可写目录（默认在仓库 `backups/memu/mem0_runtime`）
- `--max-retrieve-cases`: 限制 query 数量，便于先跑小样
- 卖点探针默认执行：脚本会自动对比 `infer=True vs infer=False`、`metadata+filters` 的检索差异

## SimpleMem（真实测试）

- 脚本：`run_simplemem_case13_real.py`
- 用途：读取共享 Case13，执行 `add_dialogue -> finalize -> hybrid_retriever.retrieve`，打印完整输入对话、完整记忆条目、每个 query 的完整召回结果。

运行命令：

```bash
export MINIMAX_API_KEY='...'
/Users/admin/miniconda3/envs/py312/bin/python /Users/admin/work/agent_loop/tests/research/memory/run_simplemem_case13_real.py \
  --config /Users/admin/work/agent_loop/configs/default.json \
  --benchmark-path /Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md \
  --benchmark-case auto \
  --retrieve-query-set daily_habits
```

输出归档：

- `/Users/admin/work/agent_loop/backups/memory/simplemem_case13_output.txt`

## OpenViking（真实测试）

- 脚本：`run_openviking_case13_real.py`
- 用途：读取共享 Case13，执行 `session add_message -> commit_session` 完成长期记忆抽取，再对同一查询集执行 `search/find`（目标目录固定在 memories），打印完整输入、完整抽取日志、完整检索结果。

运行命令：

```bash
export MINIMAX_API_KEY='...'
export ZHIPU_API_KEY='...'
/Users/admin/miniconda3/envs/py312/bin/python /Users/admin/work/agent_loop/tests/research/memory/run_openviking_case13_real.py \
  --config /Users/admin/work/agent_loop/configs/default.json \
  --benchmark-path /Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md \
  --benchmark-case auto \
  --retrieve-query-set daily_habits
```

输出归档：

- `/Users/admin/work/agent_loop/backups/memory/openviking_case13_output.txt`

## OpenClaw Memory（模块探针）

- 脚本：`run_openclaw_memory_module_probe.sh`
- 用途：对端到端产品做 memory 子模块隔离验证，直接运行 memory 相关单测，避免被其他系统噪声干扰。

运行命令：

```bash
bash /Users/admin/work/agent_loop/tests/research/memory/run_openclaw_memory_module_probe.sh /Users/admin/work/openclaw
```

默认覆盖：
- `backend-config` / `index` / `memory-flush`
- `hybrid` / `temporal-decay` / `manager.read-file` / `qmd-scope`

Case13 统一测试（完整输出）：

```bash
cp /Users/admin/work/agent_loop/tests/research/memory/openclaw_case13_vitest.test.ts /Users/admin/work/openclaw/src/memory/case13.probe.test.ts
cd /Users/admin/work/openclaw
bun x vitest run src/memory/case13.probe.test.ts > /Users/admin/work/agent_loop/backups/memory/openclaw_case13_output.txt
```

## Claude-mem（模块探针）

- 脚本：`run_claude_mem_module_probe.sh`
- 用途：直接验证 claude-mem 的 SQLite 存储层与 search 编排层，不依赖完整插件工作流。

运行命令：

```bash
bash /Users/admin/work/agent_loop/tests/research/memory/run_claude_mem_module_probe.sh /tmp/memory_scan_round2/claude-mem
```

默认覆盖：
- `tests/sqlite/observations.test.ts`
- `tests/sqlite/summaries.test.ts`
- `tests/worker/search/search-orchestrator.test.ts`
- `tests/worker/search/result-formatter.test.ts`

Case13 统一测试（完整输出）：

```bash
cd /tmp/memory_scan_round2/claude-mem
bun /Users/admin/work/agent_loop/tests/research/memory/run_claude_mem_case13_real.ts > /Users/admin/work/agent_loop/backups/memory/claude_mem_case13_output.txt
```

## Letta / MemGPT（真实测试）

- 脚本：`run_letta_case13_real.py`
- 用途：启动本地 Letta 服务，写入 Case13 全量对话到 archival passages，再跑 Query-1..8 检索。

运行命令：

```bash
/Users/admin/miniconda3/envs/py312/bin/python /Users/admin/work/agent_loop/tests/research/memory/run_letta_case13_real.py \
  --benchmark-path /Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md \
  --benchmark-case auto \
  --retrieve-query-set daily_habits > /Users/admin/work/agent_loop/backups/memory/letta_case13_output.txt
```

## memos（真实测试）

- 脚本：`run_memos_case13_real.py`
- 用途：启动本地 memos，创建用户并登录，把 Case13 对话逐条写入 memo，再用 Query-1..8 检索。

运行命令：

```bash
/Users/admin/miniconda3/envs/py312/bin/python /Users/admin/work/agent_loop/tests/research/memory/run_memos_case13_real.py \
  --benchmark-path /Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md \
  --benchmark-case auto \
  --retrieve-query-set daily_habits > /Users/admin/work/agent_loop/backups/memory/memos_case13_output.txt
```
