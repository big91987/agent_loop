# MCP 原理与教学实现说明

本文档说明 `python-agent-suite` 在 `v4` 阶段引入 MCP（Model Context Protocol）的核心原理与当前实现方式。

## 1. MCP 解决什么问题

在 agent 系统中，模型本身不会直接访问外部系统（数据库、Git、搜索、内部平台）。  
MCP 的目标是把这些外部能力标准化成“工具（tools）”，让模型通过统一协议进行发现与调用。

一句话：**MCP 是模型与外部能力之间的标准工具总线。**

## 2. 协议层概念（教学版）

MCP 常见交互（stdio 传输）：

1. `initialize`：握手，声明协议能力。
2. `tools/list`：查询服务端暴露的工具清单（名称、描述、输入 schema）。
3. `tools/call`：按工具名 + 参数执行工具，拿到返回内容。

在本项目里：
- 客户端实现：`python-agent-suite/core/mcp_client.py`
- loop 接入：`python-agent-suite/loops/agent_loop_v3_tools.py`

## 3. 本项目的接入方式

### 3.1 配置

`config.json` 中通过 `mcp_servers` 配置服务：

```json
{
  "mcp_servers": [
    {
      "name": "example",
      "command": "python3",
      "args": ["./mcp_server.py"],
      "env": {},
      "timeout_seconds": 30
    }
  ]
}
```

### 3.2 工具映射

`v3` loop 会在 MCP 启用时做两件事：

1. 调 `tools/list` 拉取 MCP 工具定义。
2. 把 MCP 工具包装成 `ToolSpec` 并并入本地工具集。

本地工具名和 MCP 工具名会区分：  
`mcp.<server_name>.<tool_name>`

### 3.3 调用链路

当模型发起工具调用：

1. loop 判断是否为本地工具或 MCP 工具。
2. 若是 MCP 工具，调用 `MCPManager.call(...)`。
3. `MCPManager` 走 `tools/call` 获取结果并回填到 tool message。

## 4. 为什么放在 v4

`v1-v3` 已经覆盖“本地工具闭环”教学主线。  
`v4` 引入 MCP，核心教学点变成：

- 工具不再写死在进程内
- 工具发现是动态的
- 调用跨进程/跨系统，需要协议、超时和错误边界

## 5. 当前实现取舍（教学优先）

为了让学生先看懂主线，本实现选择：

- 先用最小 stdio JSON-RPC 通路
- 先关注 `initialize/list/call`
- 先把内容统一回填为文本

后续工程化可逐步增强：

- 长连接复用（减少每次握手开销）
- 更完整的 MCP 错误模型
- 二进制/多模态内容块处理
- 服务能力缓存与热刷新策略

## 6. CLI 操作

在 `v3` 中可用：

- `/mcp list`：查看当前可用 MCP 工具
- `/mcp on`：启用 MCP
- `/mcp off`：关闭 MCP
- `/mcp refresh`：刷新 MCP 工具清单

## 7. 常见问题排查

1. `/mcp list` 为空  
  - 检查 `mcp_servers` 是否配置正确  
  - 检查 server 进程是否可启动  
  - 检查 `tools/list` 是否实现

2. 调用超时  
  - 提高 `timeout_seconds`  
  - 检查 server 侧是否阻塞

3. 工具名冲突/不清晰  
  - 通过 `mcp.<server>.<tool>` 命名前缀区分来源
