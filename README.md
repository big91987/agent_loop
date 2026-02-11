# Python Agent Loop Teaching Suite

教学目标：用最小代码从 `v1`（纯对话）走到 `v2`（教学用基础工具）、`v3`（本地 CLI 工具），再到 `v4`（MCP）和 `v5`（Skill）。

## 目录

- `config.json`: 公共模型配置（OpenAI 风格）
- `cli.py`: 教学 CLI 入口
- `core/`: 配置、客户端抽象、工具定义
- `tools/`: 工具定义（每个 tool 一个文件）
- `backups_sync_v1v2/`: 重构前同步版备份
- `loops/agent_loop_v1_basic.py`: v1 基础 loop
- `loops/agent_loop_v2_tools.py`: v2 工具 loop
- `loops/agent_loop_v3_tools.py`: v3 本地工具 loop
- `tests/`: v1/v2 测试

## 配置

`config.json` 字段：
- `provider`: 供应商标识（教学版仅做信息保留）
- `model_name`: 模型名
- `base_url`: OpenAI-compatible API 地址
- `api_key`: 可选，直接填写 API Key（教学环境可用，生产不建议）
- `api_key_env`: API Key 环境变量名（可选，默认 `OPENAI_API_KEY`）
- `timeout_seconds`: 请求超时
- `default_loop_version`: 默认 loop（`v1`、`v2` 或 `v3`）
- `mcp_servers`: MCP 服务配置列表（v4）
- `skills_dir`: Skill 根目录（v5）

## 运行 CLI

```bash
cd /Users/admin/work/agent_loop
python3 cli.py --config ./config.json --loop v1
python3 cli.py --config ./config.json --loop v1 --debug
python3 cli.py --config ./config.json --loop v3
python3 cli.py --config ./config.json --loop v3 --debug --log-dir ./logs
```

交互命令：
- `/loop v1|v2|v3|v4|v5`
- `/state`
- `/quit`
- `/mcp list|on|off|refresh`（仅 v4/v5）
- `/skill list|use <name>|off`（仅 v5）

## 日志

- 每次启动 CLI 会创建一个新的日志文件，文件名带时间戳：`session_YYYYMMDD_HHMMSS.log`
- 默认目录：`./logs`
- 可通过 `--log-dir` 指定日志目录
- 启动时至少写入一条 startup 记录
- 无论是否开启 `--debug`，请求/响应 debug payload 都会写入同一个日志文件

## 运行测试

```bash
cd /Users/admin/work/agent_loop
bash ./run-tests.sh
```

## 版本说明

### v1
- 基于 `BaseAgentLoop` 的 async 类实现（`V1BasicLoop`）
- 单轮：`user -> llm -> assistant`
- 不处理 tools
- 流程图：见 `docs/loop_flows_mermaid.md`

![v1 flow](./docs/diagrams/v1.svg)

### v2
- 基于 `BaseAgentLoop` 的 async 类实现（`V2ToolsLoop`）
- 使用教学用基础工具（`calculate`、`get_current_time`）进行 tool 调用闭环
- 工具集合在 `loops/agent_loop_v2_tools.py` 内确定（CLI 不注入）
- 流程：`user -> assistant(tool_call) -> execute tool -> toolResult -> assistant(final)`
- 适用场景：教学演示、最小闭环验证，不涉及文件系统改动
- 流程图：见 `docs/loop_flows_mermaid.md`

![v2 flow](./docs/diagrams/v2.svg)

### v3
- 基于 `BaseAgentLoop` 的 async 类实现（`V3ToolsLoop`）
- tool 后端为 `tools/` 内本地 handler
- 支持 CLI 工具：`read/write/edit/grep/find/ls`
- 工具集合在 `loops/agent_loop_v3_tools.py` 内确定（CLI 不注入）
- 适用场景：本地文件读写、代码检索、目录浏览、命令执行
- 与 v2 的机制差异：
  - 默认注入 `cwd`（模型不传也可在当前目录执行 CLI 工具）
  - 工具类型从教学工具切换为文件/命令工具，强调真实工程操作链路
- 流程图：见 `docs/loop_flows_mermaid.md`

![v3 flow](./docs/diagrams/v3.svg)

### v4
- 基于 `V3ToolsLoop` 扩展（`V4MCPToolsLoop`）
- 增加 MCP Server 对接，动态发现并调用 MCP tools
- CLI 支持：`/mcp list|on|off|refresh`

v4 依赖的 `mcp_client` 原理（stdio）：
- `core/mcp_client.py` 通过子进程启动 MCP server（`command + args`）。
- agent 作为 MCP client，通过子进程的 `stdin/stdout` 进行协议通信（JSON-RPC 帧，`Content-Length` 头）。
- 基本调用链路：`initialize -> tools/list`（发现工具）和 `initialize -> tools/call`（执行工具）。
- 当前实现是教学版：按请求启动子进程并通信；后续工程化可升级为长连接复用。

v4 示例 server（stdio）：
- 示例文件：`examples/mcp_server.py`
- 示例工具：`calculate`、`get_current_time`（与 v2 教学工具一致）
- 可在 `config.json` 配置：

```json
{
  "mcp_servers": [
    {
      "name": "demo",
      "command": "python3",
      "args": ["./examples/mcp_server.py"],
      "env": {},
      "timeout_seconds": 30
    }
  ]
}
```

### v5
- 基于 `V4MCPToolsLoop` 扩展（`V5SkillToolsLoop`）
- 增加 Skill 加载与激活，技能内容注入 system prompt
- CLI 支持：`/skill list|use <name>|off`

## TODO（基于 PRD 的实现计划）

| 阶段 | 目标 | 关键内容 | 状态 |
|---|---|---|---|
| v1 | 最小可运行 loop | 单轮对话：`user -> llm -> assistant`，无 tools | 已完成 |
| v2 | 教学工具闭环 | `calculate/get_current_time` 的 tool_call 执行与回填 | 已完成 |
| v3 | CLI 工具闭环 | `read/write/edit/grep/find/ls` 本地执行与回填 | 已完成 |
| v4 | MCP 支持 | 对接 MCP Server，动态发现并调用 MCP tools | 进行中 |
| v5 | Skill 支持 | 加载技能目录，支持激活 skill 注入 system prompt | 进行中 |
| v6 | 队列/中断等工程机制 | 消息队列、中断控制、运行时拆分 | 待实现 |

## 文档

- MCP 原理与实现说明：`docs/mcp_principles.md`
