# DeepAgents 中间件机制说明

本文聚焦 `langchain/deepagents` 里的 middleware（中间件）机制：它是什么、在执行链路中的位置、默认做了哪些事。

## 1. 中间件是什么

中间件可以理解为“包在模型调用外层的拦截层”。  
每轮执行时，它可以：

- 注入/修改工具列表（tools）
- 注入/修改 system prompt
- 读取/更新运行时状态（state）
- 在工具调用前后做拦截与后处理

一句话：**中间件负责把工程逻辑（工具治理、上下文治理、兼容修补）从主循环中解耦。**

## 2. 执行链路（简化）

1. 收到请求：`messages + tools + state`
2. 进入 middleware 链（按顺序）
3. middleware 可修改 request（system/tools/state）
4. 调用模型
5. 模型返回 tool_calls 或文本
6. middleware 可在工具执行前后介入
7. 产生 state update（进入下一轮）

注意：  
`state` 不是“本轮文本返回值”，而是 agent 持续运行的上下文状态。

## 3. DeepAgents 默认中间件（create_deep_agent）

`deepagents.create_deep_agent(...)` 默认会组装如下中间件（主 agent）：

| 中间件 | 主要能力 | 典型工具/效果 |
|---|---|---|
| `TodoListMiddleware` | 任务分解与进度追踪 | `write_todos` |
| `FilesystemMiddleware` | 文件与命令执行能力注入 | `ls/read_file/write_file/edit_file/glob/grep/execute` |
| `SubAgentMiddleware` | 子代理编排 | `task` |
| `SummarizationMiddleware` | 上下文压缩 | 超长上下文摘要/裁剪 |
| `AnthropicPromptCachingMiddleware` | 提示缓存优化 | Anthropic 缓存策略 |
| `PatchToolCallsMiddleware` | tool call 兼容修补 | 规范化模型返回的 tool 调用 |

当你传 `skills=[...]` 时，还会额外加入：

| 中间件 | 主要能力 | 典型工具/效果 |
|---|---|---|
| `SkillsMiddleware` | skills 元数据注入 + 按需加载 | `skill` 工具 + Skills system prompt |

## 4. “改 state”是什么意思

“改 state”不是只改文本输出，而是更新下一轮可见的运行状态。  
典型例子：`write_todos` 工具返回 `Command(update={...})`，把新的 todo 列表写回 state。

常见 state 内容：
- `messages`
- `todos`
- `files`（部分 backend）
- skills 元数据等中间状态

## 5. “拦截 tool call”是什么意思

拦截发生在两类时机：

1. 工具执行前（pre-tool）
- 校验工具是否允许执行
- 重写参数
- 直接拒绝调用

2. 工具执行后（post-tool）
- 截断超长输出
- 把大输出转存文件并返回摘要
- 统一格式化结果

因此，拦截不是单纯“改返回文本”，而是对整个工具执行路径做治理。

## 6. 结合 DeepAgents 的具体例子

### 6.1 FilesystemMiddleware

- 默认注入 7 个工具：`ls/read_file/write_file/edit_file/glob/grep/execute`
- 运行时检查 backend 是否支持执行；不支持会把 `execute` 从 tools 里过滤掉
- 同时把对应工具使用规则附加到 system prompt

### 6.2 SkillsMiddleware（可选）

- 在 system prompt 注入“可用 skills 元数据 + progressive disclosure 说明”
- 同时注入 `skill` 工具
- 模型调用 `skill(name=...)` 后返回 `<skill ...>` 正文，注入当前上下文

### 6.3 SubAgentMiddleware

- 注入 `task` 工具
- system prompt 中追加“可用 subagent 类型”
- 主 agent 调 `task(...)` 时，把任务下发给子代理并回收结果

## 7. 对你当前问题的结论

1. 中间件是“执行编排层”，不是一个单独工具。  
2. 改 state 是改会话运行状态，不等于改文本输出。  
3. 拦截 tool call 可以在前后两段发生。  
4. deepagents 的这套机制，本质是通过 middleware 来做“工具注入 + prompt 注入 + 上下文治理 + 兼容修补”。

## 8. 关键源码入口（便于继续深挖）

- deepagents 组装中间件：`/Users/admin/miniconda3/envs/py312/lib/python3.12/site-packages/deepagents/graph.py`
- 文件系统中间件：`/Users/admin/miniconda3/envs/py312/lib/python3.12/site-packages/deepagents/middleware/filesystem.py`
- skills 中间件：`/Users/admin/miniconda3/envs/py312/lib/python3.12/site-packages/deepagents/middleware/skills.py`
- subagent 中间件：`/Users/admin/miniconda3/envs/py312/lib/python3.12/site-packages/deepagents/middleware/subagents.py`
- todo 中间件：`/Users/admin/miniconda3/envs/py312/lib/python3.12/site-packages/langchain/agents/middleware/todo.py`

## 9. Backend 能力矩阵（实践版）

`FilesystemMiddleware` 是否注入可执行命令能力，取决于 backend 是否实现 `SandboxBackendProtocol`。

| Backend | 文件读写 | 命令执行工具 | 工具名 | 典型用途 | 风险级别 |
|---|---|---|---|---|---|
| `StateBackend` | 内存态 | 否 | 无 | 纯教学、无落盘 | 低 |
| `FilesystemBackend` | 本地磁盘 | 否 | 无 | 本地文件操作、无命令执行 | 中 |
| `LocalShellBackend` | 本地磁盘 | 是 | `execute` | 本地开发机快速跑通端到端 | 高 |
| `CompositeBackend` | 取决于默认 backend | 取决于默认 backend | 通常 `execute`（若 default 支持） | 混合路由（部分持久化 + 部分临时） | 中到高 |
| 自定义 `BaseSandbox` 实现 | 可定制 | 是 | `execute` | 生产隔离执行（容器/沙箱） | 可控 |

关键点：
- DeepAgents 没有内置 `bash` 工具名，执行命令统一是 `execute(command=\"...\")`。
- 用 `FilesystemBackend` 时，即使 prompt 里写“运行命令”，模型也拿不到执行工具，只能停在“写文件但无法执行”。
- 用 `LocalShellBackend` 时可跑通流程，但这是“宿主机直连执行”，无隔离、无安全边界。

## 10. 我们这次实测结论

在本项目里，对同一类 PPT 任务的实测结果：

1. `FilesystemBackend`：
- 模型可完成 `skill` 加载、读写 HTML/JS 文件。
- 无 `execute`，无法执行 `node`，最终只能返回“请用户手工在终端运行”。

2. `LocalShellBackend`：
- 获得 `execute` 后，模型可执行 `node` 脚本并产出目标文件。
- 已验证可实际生成：`/Users/admin/work/agent_loop/outputs/deepagents_us_election_20260214_155422.pptx`。

结论：
- 需要端到端“自动生成文件”的任务，backend 必须提供执行能力。
- 只做“生成脚本/配置文件”的任务，`FilesystemBackend` 足够。

## 11. 常见限制与排障清单

### 11.1 工具能力不匹配

症状：
- 模型反复 `glob/ls/read_file/write_file`，但不执行命令。
- 回答里出现“没有 shell/terminal execution tool”。

排查：
- 看请求里的 `tools` 是否包含 `execute`。
- 若没有，说明 backend 不支持执行（或被 middleware 过滤）。

修复：
- 切换到 `LocalShellBackend`（开发场景）或 sandbox backend（生产场景）。

### 11.2 递归上限（GraphRecursionError）

症状：
- 报 `GraphRecursionError: Recursion limit ...`。

原因：
- 任务未收敛（常见于工具能力缺失导致“搜索循环”）。

修复顺序：
1. 先解决工具能力缺失（最常见根因）。
2. 再调大 `recursion_limit` 作为兜底，而不是首选。

### 11.3 执行超时与输出截断

`LocalShellBackend` 关键参数：
- `timeout`：单条命令超时秒数。
- `max_output_bytes`：命令输出上限，过大输出会截断。
- `inherit_env`：是否继承当前进程环境变量。

建议：
- 任务涉及 `npm install`、编译或下载时，适当增大 `timeout`。
- 如需读取大日志，增大 `max_output_bytes` 或分段输出。

### 11.4 环境解释器不一致

症状：
- 你以为是 py312，但命令实际跑到系统 Python。

建议：
- 用绝对解释器路径或确认 `which python/python3`。
- 对高一致性场景，显式使用：`/Users/admin/miniconda3/envs/py312/bin/python3`。

### 11.5 安全边界

`LocalShellBackend` 风险要点：
- 可执行任意系统命令。
- 可访问宿主机可见文件与环境变量。
- 不适合多租户/生产公网环境。

最佳实践：
- 开发/教学：可用 `LocalShellBackend` 快速验证链路。
- 生产：使用隔离沙箱 backend（容器/VM）+ 最小权限 + 人审。

### 11.6 为什么 `read_file` 一次不读完

现象：
- 模型经常连续多次调用 `read_file`，每次只读一段。

根因：
- 这是 deepagents 文件工具的默认分页策略，不是你这边 loop/CLI 的限制。
- `read_file` 工具参数里有 `offset` 和 `limit`，默认会按固定窗口读取（默认 100 行）。
- 工具描述也会提示模型优先分页读取，避免一次塞入超长内容导致上下文膨胀。

结论：
- 不是“不能一次读完”，而是“默认按段读取”。
- 如果你希望一次读更多，需要在工具调用里显式增大 `limit`，或修改工具侧默认值。
