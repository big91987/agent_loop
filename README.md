# Python Agent Loop Teaching Suite

教学目标：用最小代码从 `v1`（纯对话）走到 `v2`（教学用基础工具）、`v3`（本地 CLI 工具），再到 `v4`（MCP）、`v4.1`（MCP + resources + 多传输）、`v5`（Skill）和 `v6`（Session 基础设施）。

## 目录

- `configs/`: 配置文件目录（可放多份 profile）
- `config.json`: 兼容保留（建议使用 `configs/default.json`）
- `cli.py`: 教学 CLI 入口（v1-v5）
- `cli_v6.py`: v6 CLI 入口（session-first）
- `core/`: 配置、客户端抽象、工具定义
- `tools/`: 工具定义（每个 tool 一个文件）
- `backups_sync_v1v2/`: 重构前同步版备份
- `loops/agent_loop_v1_basic.py`: v1 基础 loop
- `loops/agent_loop_v2_tools.py`: v2 工具 loop
- `loops/agent_loop_v3_tools.py`: v3 本地工具 loop
- `loops/agent_loop_v4_1_mcp_tools.py`: v4.1 MCP 扩展 loop
- `tests/`: v1/v2 测试

## 配置

推荐使用 `configs/default.json`、`configs/v4_mcp_simple.json`、`configs/v4_1_mcp_simple.json`、`configs/v5_skill_pi_style.json` 或 `configs/v6_session.json`。

配置字段：
- `provider`: 供应商标识（教学版仅做信息保留）
- `model_name`: 模型名
- `base_url`: OpenAI-compatible API 地址
- `api_key`: 可选，直接填写 API Key（教学环境可用，生产不建议）
- `api_key_env`: API Key 环境变量名（可选，默认 `OPENAI_API_KEY`）
- `timeout_seconds`: 请求超时
- `default_loop_version`: 默认 loop（`v1`、`v2`、`v3`、`v4`、`v4.1`、`v5`）
- `mcpServers`: MCP 服务配置（对象映射：`name -> server config`）
- `mcpServers.<name>.type`: 传输类型（`stdio`、`sse`、`streamable_http`）
- `mcpServers.<name>.command/args/env`: `stdio` 传输字段
- `mcpServers.<name>.stdio_msg_format`: `stdio` 消息格式（`auto`、`line`、`content-length`，默认 `auto`）
- `mcpServers.<name>.url/message_url/headers`: `sse` 与 `streamable_http` 传输字段
- `skills_dir`: Skill 根目录（v5）

## 运行 CLI

```bash
cd /Users/admin/work/agent_loop
python3 cli.py --config ./configs/default.json --loop v1
python3 cli.py --config ./configs/default.json --loop v1 --debug
python3 cli.py --config ./configs/default.json --loop v3
python3 cli.py --config ./configs/default.json --loop v3 --debug --log-dir ./logs
python3 cli.py --config ./configs/v4_mcp_simple.json --loop v4
python3 cli.py --config ./configs/v4_1_mcp_simple.json --loop v4.1
python3 cli.py --config ./configs/v5_skill_pi_style.json --loop v5
python3 cli_v6.py --config ./configs/v6_session.json
```

交互命令：
- `/loop v1|v2|v3|v4|v4.1|v5`
- `/state`
- `/quit`
- `/mcp list|on|off|refresh`（仅 v4/v4.1/v5）
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
- MCP client 实现：`core/mcp_client.py`（保持教学版 stdio + tools）
- transport 策略：仅支持显式 `type=stdio`（不做自动推断）
- stdio 连接策略：每次请求独立启动子进程（教学简化）
- CLI 支持：`/mcp list|on|off|refresh`
- 流程图：见 `docs/loop_flows_mermaid.md`

![v4 flow](./docs/diagrams/v4.svg)

v4 依赖的 `mcp_client` 原理（stdio）：
- `core/mcp_client.py` 通过子进程启动 MCP server（`command + args`）。
- agent 作为 MCP client，通过子进程的 `stdin/stdout` 进行协议通信（JSON-RPC 帧，`Content-Length` 头）。
- 基本调用链路：`initialize -> tools/list`（发现工具）和 `initialize -> tools/call`（执行工具）。
- 当前实现是教学版：按请求启动子进程并通信；后续工程化可升级为长连接复用。

v4 示例 server（stdio）：
- 示例文件：`mcp_servers/demo/simple_server.py`
- 示例工具：`calculate`、`get_current_time`（与 v2 教学工具一致）
- 可在配置中写：

```json
{
  "mcpServers": {
    "simple": {
      "name": "simple",
      "type": "stdio",
      "command": "python3",
      "args": ["./mcp_servers/demo/simple_server.py"],
      "env": {},
      "timeout_seconds": 30
    }
  }
}
```

### v4.1
- 基于 `V4MCPToolsLoop` 扩展（`V4_1MCPToolsLoop`）
- MCP client 实现：`core/mcp_client_v4_1.py`（独立于 v4）
- transport 策略：支持自动推断（显式 `type` 优先，缺省时按 `command/url` 推断）
- stdio 连接策略：长生命周期子进程复用，CLI 退出时回收
- stdio 消息格式策略：支持 `line` / `content-length`，默认 `auto`（先 `line`，失败再 `content-length`）
- 在 v4 的 MCP tools 基础上，新增 resource 桥接工具：
  - `mcp.<server>.resource_list`
  - `mcp.<server>.resource_read`
- `resource_read` 的函数描述生成规则：
  - 优先使用 server 在 `resources/list` 返回的 resource `description`
  - 若 server 未提供 `description`，回退到工程默认（hardcode）描述
- 支持 MCP transport `type`：
  - `stdio`
  - `sse`
  - `streamable_http`
- 推荐配置：`configs/v4_1_mcp_simple.json`
- 流程图：见 `docs/loop_flows_mermaid.md`

![v4.1 flow](./docs/diagrams/v4_1.svg)

`stdio_msg_format` 示例：

```json
{
  "mcpServers": {
    "playwright": {
      "name": "playwright",
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"],
      "stdio_msg_format": "auto",
      "timeout_seconds": 120
    }
  }
}
```

`mcpServers.<name>.type` 示例：

```json
{
  "mcpServers": {
    "simple": {
      "name": "simple",
      "type": "stdio",
      "command": "python3",
      "args": ["./mcp_servers/demo/simple_server.py"]
    },
    "remote_sse": {
      "name": "remote_sse",
      "type": "sse",
      "url": "https://example.com/sse",
      "message_url": "https://example.com/messages",
      "headers": {"Authorization": "Bearer <token>"}
    },
    "remote_http": {
      "name": "remote_http",
      "type": "streamable_http",
      "url": "https://example.com/mcp",
      "headers": {"Authorization": "Bearer <token>"}
    }
  }
}
```

### v5
- 基于 `V4MCPToolsLoop` 扩展（`V5SkillToolsLoop`）
- 采用渐进式披露（pi-mono 风格）：
  - system prompt 只注入 `<available_skills>` 元信息（name/description/location）
  - 通过 `read_skill(name)` 工具按需加载 `SKILL.md` 正文
- `/skill use <name>` 仅设置“偏好技能”提示，不再把全文直接塞进 system prompt
- CLI 支持：`/skill list|use <name>|off`
- Skill 原理与实现：`docs/skill_principles.md`
- v5 注入报文片段（当前实现，简化）：

```json
{
  "model": "MiniMax-M2.5",
  "messages": [
    {
      "role": "system",
      "content": "...\n<available_skills>\n  <skill>\n    <name>pptx</name>\n    <description>...</description>\n    <location>/Users/admin/.claude/skills/pptx/SKILL.md</location>\n  </skill>\n</available_skills>"
    },
    { "role": "user", "content": "做 3 页 ppt 讲述本草纲目" }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "read_skill",
        "description": "Load full instructions for a skill by name.",
        "parameters": {
          "type": "object",
          "properties": { "name": { "type": "string" } },
          "required": ["name"],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

- v5 loop 流程图：`docs/diagrams/v5_skill_injection.svg`

![v5 skill flow](./docs/diagrams/v5_skill_injection.svg)

### v5 方案选择（主流对比）

- deepagents：skills 元信息主要在 system，`skill` 工具负责加载正文
- opencode：skills 元信息主要放在 `skill` 工具描述里，命中后返回 `<skill_content>`
- pi-mono：system 放 `<available_skills>`，命中后用 `read` 读取 `SKILL.md`

当前项目选择：**pi-mono 风格**。  
原因：教学上更直观，能清楚展示“元信息常驻 + 正文按需读取”的渐进式披露链路。

### v6（Session 基础设施）
- 新 CLI 入口：`cli_v6.py`
- 默认行为：启动即新建一个内存 session（仅当有真实用户对话后才落盘）
- 支持恢复：`--session <id>` 或交互命令 `/session use <id>`
- 恢复后会把该 session 的最近用户输入回填到 readline 历史（上下键可回放，默认 100 条，可用 --rehydrate-history 覆盖）
- 会话标题（title）：
  - 自动从首个有效用户请求生成短标题
  - `/session list` 主要展示 title，便于快速识别会话
- 交互体验（readline）：
  - 上下箭头：历史命令浏览
  - 退格编辑：终端行编辑能力
  - TAB 补全：支持 `/session`、`/mcp`、`/skill` 命令及部分参数补全
  - 历史文件：`--history-file`（默认 `./logs/cli_v6_history.txt`）
- 流式输出：
  - 默认开启 `--stream`（可用 `--no-stream` 关闭）
  - 模型文本会边到达边打印（工具调用轮保持原有执行逻辑）
- 支持查看与管理：
  - `/session list`：列出本地 sessions
  - `/session new`：新建并切换到新 session
  - `/session use <id>`：恢复指定 session
  - `/tokens`：查看当前激活窗口最近一次调用的 token，以及当前 session 累计 token
- token 统计：
  - 每轮结束自动打印 `window/session/turn` 三组 token 计数
  - 优先使用模型返回的 `usage`；若供应商未返回，自动切换到本地估算（输出 `source=estimated`）
- 存储目录：默认 `./sessions`（可用 `--sessions-dir` 覆盖）
- 文件格式：每个 session 一份 markdown，内含
  - 元数据（创建时间/更新时间/模型/loop）
  - title
  - 可恢复的 JSON messages
  - 可读 transcript

## TODO（基于 PRD 的实现计划）

| 阶段 | 目标 | 关键内容 | 状态 |
|---|---|---|---|
| v1 | 最小可运行 loop | 单轮对话：`user -> llm -> assistant`，无 tools | 已完成 |
| v2 | 教学工具闭环 | `calculate/get_current_time` 的 tool_call 执行与回填 | 已完成 |
| v3 | CLI 工具闭环 | `read/write/edit/grep/find/ls` 本地执行与回填 | 已完成 |
| v4 | MCP 支持 | 对接 MCP Server，动态发现并调用 MCP tools | 进行中 |
| v4.1 | MCP resource + transport 扩展 | 支持 resources，支持 `stdio/sse/streamable_http` | 已完成 |
| v5 | Skill 支持 | 加载技能目录，支持激活 skill 注入 system prompt | 进行中 |
| v6 | 队列/中断等工程机制 | 消息队列、中断控制、运行时拆分 | 待实现 |

## 文档

- MCP 原理与实现说明：`docs/mcp_principles.md`
- Skill 原理与实现说明：`docs/skill_principles.md`
- DeepAgents 中间件机制说明：`docs/deepagents_principles.md`
- Memory 注入与 loop 时机对比（CC / OpenCode / OpenClaw）：`docs/memory_architecture_compare.md`
- Memory 大白话综述 + 系统扫描 + Benchmark/SOTA：`docs/memory_research_overview.md`
