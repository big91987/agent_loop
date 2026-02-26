# Memory Research Scripts

本目录只放 memory 调研验证脚本。

## MemU（真实测试）

- 脚本：`run_memu_rich_demo_real.py`
- 用途：真实模型调用，从 benchmark Markdown 解析指定 Case，对话写入临时 JSON 后执行 memorize/retrieve，并打印完整输入对话、retrieve 请求、结果。
- 默认测试集：`data/agent_memory_benchmark_v6_full.md`
- 默认 Case：`auto`（自动选文件里最后一个 case；你这份当前是 `Case 12`）

运行命令：

```bash
export MINIMAX_API_KEY='...'
export ZHIPU_API_KEY='...'
conda run -n py312 python /Users/admin/work/agent_loop/tests/research/memory/run_memu_rich_demo_real.py \
  --config /Users/admin/work/agent_loop/configs/default.json \
  --benchmark-path /Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_benchmark_v6_full.md \
  --benchmark-case "auto" \
  --retrieve-query "请回忆我在这组对话里的关键偏好、工作信息和近期计划，先给结论再给细节。" \
  --embed-base-url https://open.bigmodel.cn/api/paas/v4 \
  --embed-model embedding-3
```

常用参数：

- `--benchmark-case`: 选择测试集 Case（默认 `auto`，也可显式传 `Case 1`、`Case 3` 等）
- `--benchmark-max-messages`: 限制导入轮数（默认 `80`）
- `--retrieve-query`: 指定检索问题（建议和该 Case 的“触发查询”对应）

输出归档：

- `/Users/admin/work/agent_loop/backups/memu/runs/memu_rich_demo_real_output.txt`
