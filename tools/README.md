# Tools

`agent_loop` 的工具定义目录。  
目标是把每个工具的职责、参数 schema、描述文案独立维护，避免集中在一个大文件里难以演进。

## 目录结构

- 基类：`/Users/admin/work/agent_loop/core/tool_base.py`
  - `BaseTool`：有真实 `handler` 执行逻辑的工具（例如 `calculate`）
  - `MetadataOnlyTool`：仅声明 schema/描述、不执行逻辑的工具基类（当前未使用）
- 注册：`/Users/admin/work/agent_loop/tools/registry.py`
  - `get_default_tools()`：给 v2 loop 用
- 单工具文件：`/Users/admin/work/agent_loop/tools/*_tool.py`

## 通用输入输出约定

- 输入：所有工具输入都通过 `Dict[str, object]` 接收，并在 `parameters` 中声明 JSON Schema（OpenAI tools 风格）。
- 输出：最终输出都转成字符串放到 tool message 的 `content` 里。
- 异常：tool 内部抛出的异常会在 loop 层被捕获并包装成 `Tool execution error: ...` 返回给模型。
- 描述：`description` 由每个工具派生类自己维护，不在注册器里硬编码。
- 描述来源：已对齐参考实现 `/Users/admin/work/pi-mono/packages/coding-agent/src/core/tools/` 的说明风格（summary/principle/usage/fault-tolerance），并映射到当前 Python 版可用参数。

## 工具总览

| Tool | 类型 | 文件 |
|---|---|---|
| `calculate` | 本地执行 | `/Users/admin/work/agent_loop/tools/calculate_tool.py` |
| `get_current_time` | 本地执行 | `/Users/admin/work/agent_loop/tools/get_current_time_tool.py` |
| `read` | 本地执行 | `/Users/admin/work/agent_loop/tools/read_tool.py` |
| `write` | 本地执行 | `/Users/admin/work/agent_loop/tools/write_tool.py` |
| `edit` | 本地执行 | `/Users/admin/work/agent_loop/tools/edit_tool.py` |
| `grep` | 本地执行 | `/Users/admin/work/agent_loop/tools/grep_tool.py` |
| `find` | 本地执行 | `/Users/admin/work/agent_loop/tools/find_tool.py` |
| `ls` | 本地执行 | `/Users/admin/work/agent_loop/tools/ls_tool.py` |

## v2/v3 使用边界

- `v2`：仅使用教学工具 `calculate`、`get_current_time`。
- `v3`：使用 CLI 工具集 `read/write/edit/grep/find/ls`。

## 详细说明

### `calculate`

- 作用：安全计算四则和幂运算表达式，用于简单数值推理。
- 输入：
  - `expression` (`string`, required)：算术表达式，如 `(2+3)*4`
- 输出：
  - 成功：计算结果字符串，如 `20`
  - 失败：参数缺失或语法不被允许时抛异常
- 约束：
  - 只允许白名单 AST 节点（`BinOp`、`UnaryOp`、`Constant` 等）
  - 不允许函数调用、属性访问、名称引用等高风险语法

### `get_current_time`

- 作用：返回当前 UTC 时间，ISO-8601 格式。
- 输入：无必填参数。
- 输出：如 `2026-02-10T12:34:56.123456+00:00`

### `read`（本地）

- 作用：读取文件内容，支持分页与大小限制。
- 输入：
  - `path` (`string`, required)
  - `cwd` (`string`, optional)
  - `offset` (`integer`, optional)
  - `limit` (`integer`, optional)
  - `max_lines` (`integer`, optional)
  - `max_bytes` (`integer`, optional)
- 输出：
  - 本地 handler 返回的文本内容或分页提示文本

### `write`（本地）

- 作用：将完整文本写入目标文件。
- 输入：
  - `path` (`string`, required)
  - `content` (`string`, required)
  - `cwd` (`string`, optional)
- 输出：
  - 本地 handler 返回写入结果（路径、写入字节数、状态信息）

### `edit`（本地）

- 作用：对文件内容执行单次文本替换。
- 输入：
  - `path` (`string`, required)
  - `old_text` (`string`, required)
  - `new_text` (`string`, required)
  - `cwd` (`string`, optional)
- 输出：
  - 本地 handler 返回替换结果（替换次数、状态信息）

### `grep`（本地）

- 作用：在文件/目录中按正则搜索文本。
- 输入：
  - `pattern` (`string`, required)
  - `path` (`string`, required)
  - `cwd` (`string`, optional)
  - `limit` (`integer`, optional)
  - `context` (`integer`, optional)
- 输出：
  - 本地 handler 返回匹配行列表与命中统计

### `find`（本地）

- 作用：按 glob 模式查找文件路径。
- 输入：
  - `pattern` (`string`, required)
  - `path` (`string`, required)
  - `cwd` (`string`, optional)
- 输出：
  - 本地 handler 返回匹配文件列表

### `ls`（本地）

- 作用：列目录内容。
- 输入：
  - `path` (`string`, optional)
  - `cwd` (`string`, optional)
- 输出：
  - 本地 handler 返回目录条目列表

## 如何新增一个工具

1. 在 `/Users/admin/work/agent_loop/tools/` 新增 `xxx_tool.py`。
2. 继承合适基类：
   - 需要本地执行逻辑 -> `BaseTool`
   - 只提供 schema（无本地执行）-> `MetadataOnlyTool`
3. 实现 `name`、`description`、`parameters`，以及（如需要）`handler`。
4. 挂载到目标 loop：
   - v2 工具：在 `/Users/admin/work/agent_loop/tools/registry.py` 的 `get_default_tools()` 中注册
   - v3 工具：在 `/Users/admin/work/agent_loop/loops/agent_loop_v3_tools.py` 中直接加入工具列表
5. 在本 README 的“工具总览”和“详细说明”补充文档。

## 说明

工具定义和注册已完全收敛到 `tools/` 目录，`core/` 中不再维护工具注册入口文件。
