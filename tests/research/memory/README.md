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
