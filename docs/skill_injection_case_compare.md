# Skill 注入对比（成功案例）

本文基于 3 组已跑通的真实日志，比较 deepagents / opencode / pi-mono 在 Skill 场景下的“注入方式 + 映射 + 执行流程”。

## 1. 样本与产物

- deepagents 成功样本  
  - `/Users/admin/work/agent_loop/logs/deepagents_ppt_result_20260214_155422.json`
  - `/Users/admin/work/agent_loop/logs/deepagents_ppt_raw_calls_20260214_155422.json`
- opencode 成功样本（CLI 主链路）  
  - `/Users/admin/work/agent_loop/logs/oc_cli_ppt_step_summary_20260214.json`
  - `/Users/admin/work/agent_loop/logs/oc_cli_ppt_step_table_20260214.md`
- pi-mono 成功样本  
  - `/Users/admin/work/agent_loop/logs/pi_mono_ppt_result_20260214_172522.json`
  - `/Users/admin/work/agent_loop/logs/pi_mono_ppt_raw_calls_20260214_172522.json`
  - `/Users/admin/work/agent_loop/logs/pi_mono_ppt_events_20260214_172522.json`

### 1.1 关键轮“完整 OpenAI 请求体”文件（原样抽取）

- deepagents  
  - `/Users/admin/work/agent_loop/logs/skill_payload_samples/deepagents_call1_request.json`
  - `/Users/admin/work/agent_loop/logs/skill_payload_samples/deepagents_call2_request.json`
- pi-mono  
  - `/Users/admin/work/agent_loop/logs/skill_payload_samples/pi_mono_call1_request_body.json`
  - `/Users/admin/work/agent_loop/logs/skill_payload_samples/pi_mono_call2_request_body.json`
- opencode（SDK 探针链路，OpenAI 格式）  
  - `/Users/admin/work/agent_loop/logs/skill_payload_samples/opencode_real_case_call1_request_body.json`
  - `/Users/admin/work/agent_loop/logs/skill_payload_samples/opencode_real_case_call2_request_body.json`

## 2. 注入与映射对照

| 维度 | deepagents | opencode (CLI 成功链路) | pi-mono |
|---|---|---|---|
| 初始注入位置 | `system` + `tools` 双通道 | 主要是 `tools`（`skill` 工具） | 主要是 `system`（`<available_skills>` 元数据） |
| 模型首轮看到什么 | Skills 目录、可用 skill 列表、`skill` 工具描述 | `skill` 工具描述（包含可加载 skill 信息） | system 中 `<available_skills>`（name/location/description）+ 通用工具 |
| 命中动作（触发） | assistant 发 `tool_call: skill(name=\"pptx\")` | assistant 发 `tool_call: skill(name=\"pptx\")` | assistant 发 `tool_call: read(path=\".../SKILL.md\")` |
| Skill 正文如何进入上下文 | `tool` 消息注入 `<skill name=\"pptx\">...</skill>` | `tool` 消息注入 `<skill_content name=\"pptx\">...</skill_content>` | `read` 工具返回 `SKILL.md` 文本进入 `tool` 消息 |
| 后续执行工具 | `glob/ls/read_file/write_file/edit_file/execute` | `read/bash/write/edit/...`（按任务） | `read/bash/write/edit` |
| 工程映射关键词 | `skill` 作为显式 function tool；正文经 tool_result 注入 | `skill` 作为显式 function tool；正文经 tool_result 注入 | 不额外 skill tool；靠 `read(SKILL.md)` 完成正文加载 |

## 2.1 真实消息体片段（给学生看的“怎么注入”）

下面都来自真实日志，做了截断（`...`）以便阅读。

### A) deepagents（OpenAI 请求体）

来源：`/Users/admin/work/agent_loop/logs/deepagents_ppt_raw_calls_20260214_155422.json`

1) call#1 首轮完整请求体（关键字段保留）：

```json
{
  "model": "MiniMax-M2.1",
  "stream": false,
  "tools": [
    { "type": "function", "function": { "name": "write_todos", "description": "..." } },
    {
      "type": "function",
      "function": {
        "name": "skill",
        "description": "Load a skill by name. Skills provide specialized capabilities and domain knowledge.\n\nHow to invoke:\n- Use the `name` parameter with the skill name (e.g., name=\"web-research\")\n\nExamples:\n- name=\"web-research\" — load the web-research skill into the current context\n- name=\"code-review\" — invoke the code-review skill\n\nSkills are loaded into the current conversation context for you to follow.",
        "parameters": {
          "properties": {
            "name": {
              "description": "The name of the skill to load.",
              "type": "string"
            }
          },
          "required": ["name"],
          "type": "object"
        }
      }
    },
    { "type": "function", "function": { "name": "ls", "description": "..." } },
    { "type": "function", "function": { "name": "read_file", "description": "..." } }
  ],
  "messages": [
    {
      "role": "system",
      "content": [
        { "type": "text", "text": "In order to complete the objective that the user asks of you, you have access to a number of standard tools. ..." },
        {
          "type": "text",
          "text": "## Skills System\n\nYou have access to a skills library that provides specialized capabilities and domain knowledge.\n\n**Skills Skills**: `/Users/admin/.claude/skills` (higher priority)\n\n**Available Skills:**\n\n- **pptx**: Presentation creation, editing, and analysis. When Claude needs to work with presentations (.pptx files) for: (1) Creating new presentations, (2) Modifying or editing content, (3) Working with layouts, (4) Adding comments or speaker notes, or any other presentation tasks (License: Proprietary. LICENSE.txt has complete terms)\n- **skill-lookup**: Activates when the user asks about Agent Skills, wants to find reusable AI capabilities, needs to install skills, or mentions skills for Claude. Use for discovering, retrieving, and installing skills.\n\n**How to Use Skills (Progressive Disclosure):**\n\nSkills follow a **progressive disclosure** pattern - you see their name and description above, but only load full instructions when needed:\n\n1. **Recognize when a skill applies**: Check if the user's task matches a skill's description\n2. **Load the skill's full instructions**: Call the `skill` tool with the skill name (e.g., `name=\"web-research\"`)\n3. **Follow the skill's instructions**: Once loaded, the skill's full instructions appear in your context with\nstep-by-step workflows, best practices, and examples\n4. **Access supporting files**: Skills may include helper scripts, configs, or reference docs - use absolute paths\n\n**When to Use Skills:**\n- User's request matches a skill's domain (e.g., \"research X\" -> web-research skill)\n- You need specialized knowledge or structured workflows\n- A skill provides proven patterns for complex tasks\n\n**Executing Skill Scripts:**\nSkills may contain Python scripts or other executable files. Always use absolute paths from the skill list.\n\n**Example Workflow:**\n\nUser: \"Can you research the latest developments in quantum computing?\"\n\n1. Check available skills -> See \"web-research\" skill\n2. Call the `skill` tool with `name=\"web-research\"` to load full instructions\n3. Follow the skill's research workflow (search -> organize -> synthesize)\n4. Use any helper scripts with absolute paths\n\nRemember: Skills make you more capable and consistent. When in doubt, check if a skill exists for the task!"
        }
      ]
    },
    {
      "role": "user",
      "content": "任务：生成一个2页的美国大选主题PPT..."
    }
  ]
}
```

2) call#2 请求体（已出现 assistant tool_call + tool_result 回注入）：

```json
{
  "model": "MiniMax-M2.1",
  "tools": [ "...同上..." ],
  "messages": [
    { "role": "system", "content": [ "（同上：完整 Skills System 文本，含 Available Skills 与 Load-the-skill instructions）" ] },
    { "role": "user", "content": "任务：生成一个2页的美国大选主题PPT..." },
    {
      "role": "assistant",
      "tool_calls": [
        {
          "type": "function",
          "id": "call_function_qghyx9cssxmz_1",
          "function": { "name": "skill", "arguments": "{\"name\": \"pptx\"}" }
        }
      ]
    },
    {
      "role": "tool",
      "content": "<skill name=\"pptx\"> # PPTX creation, editing, and analysis ... </skill>"
    }
  ]
}
```

3) call#3 请求体（模型开始从 skill 进入文件探索）：

```json
{
  "model": "MiniMax-M2.1",
  "tools": [ "...同 call#1..." ],
  "messages": [
    { "role": "system", "content": [ "...含 Skills System 与 Available Skills..." ] },
    { "role": "user", "content": "任务：生成一个2页的美国大选主题PPT..." },
    {
      "role": "assistant",
      "tool_calls": [
        {
          "type": "function",
          "id": "call_function_qghyx9cssxmz_1",
          "function": { "name": "skill", "arguments": "{\"name\": \"pptx\"}" }
        }
      ]
    },
    {
      "role": "tool",
      "content": "<skill name=\"pptx\"> ...完整 skill 正文... </skill>"
    },
    {
      "role": "assistant",
      "tool_calls": [
        {
          "type": "function",
          "id": "call_function_ylibki9qovnp_1",
          "function": { "name": "glob", "arguments": "{\"pattern\": \"**/html2pptx.md\"}" }
        }
      ]
    },
    {
      "role": "tool",
      "content": "[]"
    }
  ]
}
```

4) call#4 请求体（继续定位 skill 目录）：

```json
{
  "model": "MiniMax-M2.1",
  "tools": [ "...同 call#1..." ],
  "messages": [
    { "role": "system", "content": [ "...含 Skills System 与 Available Skills..." ] },
    { "role": "user", "content": "任务：生成一个2页的美国大选主题PPT..." },
    { "role": "assistant", "tool_calls": [ { "function": { "name": "skill", "arguments": "{\"name\":\"pptx\"}" } } ] },
    { "role": "tool", "content": "<skill name=\"pptx\"> ... </skill>" },
    { "role": "assistant", "tool_calls": [ { "function": { "name": "glob", "arguments": "{\"pattern\":\"**/html2pptx.md\"}" } } ] },
    { "role": "tool", "content": "[]" },
    {
      "role": "assistant",
      "tool_calls": [
        {
          "type": "function",
          "id": "call_function_azyh5g8z9r3k_1",
          "function": {
            "name": "ls",
            "arguments": "{\"path\": \"/Users/admin/.claude/skills/pptx\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "content": "[\"/Users/admin/.claude/skills/pptx/LICENSE.txt\", \"/Users/admin/.claude/skills/pptx/SKILL.md\", ...]"
    }
  ]
}
```

### B) pi-mono（OpenAI 请求体）

来源：`/Users/admin/work/agent_loop/logs/pi_mono_ppt_raw_calls_20260214_172522.json`

1) 首轮完整请求体（关键字段保留）：

```json
{
  "model": "MiniMax-M2.1",
  "tools": [
    { "type": "function", "function": { "name": "read", "description": "..." } },
    { "type": "function", "function": { "name": "bash", "description": "..." } },
    { "type": "function", "function": { "name": "edit", "description": "..." } },
    { "type": "function", "function": { "name": "write", "description": "..." } }
  ],
  "messages": [
    {
      "role": "system",
      "content": "You are an expert coding assistant ... <available_skills> ... <name>pptx</name> ... <location>/Users/admin/.claude/skills/pptx/SKILL.md</location> ... </available_skills> ..."
    },
    {
      "role": "user",
      "content": "请使用 skills 中的 pptx 指令来完成任务..."
    }
  ]
}
```

2) 第 2 轮请求体（assistant 调 read + tool 返回 SKILL 正文）：

```json
{
  "model": "MiniMax-M2.1",
  "tools": [ "...同上..." ],
  "messages": [
    { "role": "system", "content": "...<available_skills>...pptx...</available_skills>..." },
    { "role": "user", "content": "请使用 skills 中的 pptx 指令来完成任务..." },
    {
      "role": "assistant",
      "tool_calls": [
        {
          "id": "call_function_nl5y0jd784cl_1",
          "type": "function",
          "function": {
            "name": "read",
            "arguments": "{\"path\":\"/Users/admin/.claude/skills/pptx/SKILL.md\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_function_nl5y0jd784cl_1",
      "content": "--- name: pptx description: \"Presentation creation...\" --- # PPTX creation, editing, and analysis ..."
    }
  ]
}
```

### C) opencode

1) OpenAI 请求体（真实案例输入，完整 request body 关键字段）

来源：`/Users/admin/work/agent_loop/logs/opencode_ppt_raw_calls_20260214_190116.json`

```json
{
  "model": "MiniMax-M2.1",
  "temperature": 0.1,
  "tool_choice": "auto",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "skill",
        "description": "Load a specialized skill that provides domain-specific instructions and workflows.\n\nWhen you recognize that a task matches one of the available skills listed below, use this tool to load the full skill instructions.\n\nThe skill will inject detailed instructions, workflows, and access to bundled resources (scripts, references, templates) into the conversation context.\n\nTool output includes a `<skill_content name=\"...\">` block with the loaded content.\n\nThe following skills provide specialized sets of instructions for particular tasks\nInvoke this tool to load a skill when a task matches one of the available skills listed below:\n\n<available_skills>\n  <skill>\n    <name>pptx</name>\n    <description>Presentation creation, editing, and analysis. When Claude needs to work with presentations (.pptx files) for: (1) Creating new presentations, (2) Modifying or editing content, (3) Working with layouts, (4) Adding comments or speaker notes, or any other presentation tasks</description>\n    <location>file:///Users/admin/.claude/skills/pptx/SKILL.md</location>\n  </skill>\n  <skill>\n    <name>skill-lookup</name>\n    <description>Activates when the user asks about Agent Skills, wants to find reusable AI capabilities, needs to install skills, or mentions skills for Claude. Use for discovering, retrieving, and installing skills.</description>\n    <location>file:///Users/admin/.claude/skills/skill-lookup/SKILL.md</location>\n  </skill>\n</available_skills>",
        "parameters": {
          "$schema": "http://json-schema.org/draft-07/schema#",
          "type": "object",
          "properties": { "name": { "type": "string" } },
          "required": ["name"],
          "additionalProperties": false
        }
      }
    },
    { "type": "function", "function": { "name": "bash", "description": "..." } }
  ],
  "messages": [
    { "role": "user", "content": "请帮我做一个 2 页的美国大选中文 PPT。\n请在 /Users/admin/work/agent_loop 里完成，并生成可打开的 .pptx 文件。\n输出文件固定为: /Users/admin/work/agent_loop/outputs/opencode_us_election_20260214_190116.pptx\n生成后请自行检查文件是否存在。\n最后仅回复绝对路径。" }
  ]
}
```

2) 下一轮请求体（assistant tool_call + tool_result 已回填）：

```json
{
  "model": "MiniMax-M2.1",
  "tools": [ "同上（skill,bash）" ],
  "messages": [
    { "role": "user", "content": "请帮我做一个 2 页的美国大选中文 PPT。..." },
    {
      "role": "assistant",
      "content": "...",
      "tool_calls": [
        {
          "id": "call_function_aenkoe1yy2wq_1",
          "type": "function",
          "function": { "name": "skill", "arguments": "{\"name\":\"pptx\"}" }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_function_aenkoe1yy2wq_1",
      "content": "No context found for instance"
    }
  ]
}
```

3) CLI 成功链路里，`skill` 的真实输出形态（事件流）：

来源：`/Users/admin/work/agent_loop/logs/oc_cli_ppt_step_summary_20260214.json`

```json
{
  "tool": "skill",
  "status": "completed",
  "output": "<skill_content name=\"pptx\">\n# Skill: pptx\n# PPTX creation, editing, and analysis\n..."
}
```

要点：opencode 的“注入载体”仍是 tool 结果；成功链路里它是 `<skill_content ...>`，与 deepagents 的 `<skill ...>` 类似，都是把正文经 tool 通道送回模型上下文。

## 2.2 Skill 原文 vs 注入后（教学对比）

目标：让学生看到“原始 `SKILL.md`”和“进入模型消息后的形态”差异。

### 原始 `SKILL.md`（header 完整，正文节选）

来源：`/Users/admin/.claude/skills/pptx/SKILL.md`

```md
---
name: pptx
description: "Presentation creation, editing, and analysis. When Claude needs to work with presentations (.pptx files) for: (1) Creating new presentations, (2) Modifying or editing content, (3) Working with layouts, (4) Adding comments or speaker notes, or any other presentation tasks"
license: Proprietary. LICENSE.txt has complete terms
---

# PPTX creation, editing, and analysis

## Overview

A user may ask you to create, edit, or analyze the contents of a .pptx file. ...
```

### 注入后 A：pi-mono（通过 `read` 返回，OpenAI `tool` 消息）

来源：`/Users/admin/work/agent_loop/logs/skill_payload_samples/pi_mono_call2_request_body.json`

```json
{
  "role": "tool",
  "tool_call_id": "call_function_nl5y0jd784cl_1",
  "content": "---\nname: pptx\ndescription: \"Presentation creation, editing, and analysis. When Claude needs to work with presentations (.pptx files) for: (1) Creating new presentations, (2) Modifying or editing content, (3) Working with layouts, (4) Adding comments or speaker notes, or any other presentation tasks\"\nlicense: Proprietary. LICENSE.txt has complete terms\n---\n\n# PPTX creation, editing, and analysis\n\n## Overview\n\nA user may ask you to create, edit, or analyze the contents of a .pptx file. ..."
}
```

### 注入后 B：deepagents（通过 `skill` 工具返回，OpenAI `tool` 消息）

来源：`/Users/admin/work/agent_loop/logs/skill_payload_samples/deepagents_call2_request.json`

```json
{
  "role": "tool",
  "content": "<skill name=\"pptx\">\n# PPTX creation, editing, and analysis\n## Overview\nA user may ask you to create, edit, or analyze the contents of a .pptx file. ...\n</skill>"
}
```

### 注入后 C：opencode（通过 `skill` 工具返回，CLI 事件中的 tool output）

来源：`/Users/admin/work/agent_loop/logs/oc_cli_ppt_step_summary_20260214.json`

```json
{
  "tool": "skill",
  "status": "completed",
  "output": "<skill_content name=\"pptx\">\n# Skill: pptx\n# PPTX creation, editing, and analysis\n## Overview\nA user may ask you to create, edit, or analyze the contents of a .pptx file. ...\n</skill_content>"
}
```

### deepagents 多轮演进（call#1 ~ call#8）

来源：`/Users/admin/work/agent_loop/logs/deepagents_ppt_raw_calls_20260214_155422.json`

| 轮次 | `messages` 角色序列 | 本轮新增 assistant tool_call | 本轮新增 tool_result（头部） |
|---|---|---|---|
| call#1 | `system -> user` | 无 | 无 |
| call#2 | `system -> user -> assistant -> tool` | `skill {"name":"pptx"}` | `<skill name="pptx"> # PPTX creation, editing, and analysis ...` |
| call#3 | `... -> assistant -> tool` | `glob {"pattern":"**/html2pptx.md"}` | `[]` |
| call#4 | `... -> assistant -> tool` | `ls {"path":"/Users/admin/.claude/skills/pptx"}` | `['/Users/admin/.claude/skills/pptx/LICENSE.txt', '/Users/admin/.claude/skills/pptx/SKILL.md', ...]` |
| call#5 | `... -> assistant -> tool` | `read_file {"file_path":"/Users/admin/.claude/skills/pptx/html2pptx.md"}` | `1  # HTML to PowerPoint Guide ...` |
| call#6 | `... -> assistant -> tool` | `read_file {"file_path":".../html2pptx.md","offset":100}` | `101 ...` |
| call#7 | `... -> assistant -> tool` | `read_file {"file_path":".../html2pptx.md","offset":200}` | `201 ...` |
| call#8 | `... -> assistant -> tool` | `execute {"command":"mkdir -p /Users/admin/work/agent_loop/outputs"}` | `<no output> [Command succeeded with exit code 0]` |

教学观察点：
- call#2 是“skill 正文进入上下文”的关键拐点。  
- call#3 起模型开始把 skill 指南转为具体工具链（发现文件 -> 读文档 -> 执行命令）。  
- `messages` 每轮追加，前一轮的 `assistant/tool` 会完整进入下一轮请求体。

## 3. 三者流程表（成功链路）

### 3.1 deepagents（18 次模型调用）

| 步骤 | 发生位置 | 关键动作 |
|---|---|---|
| 1 | call#1 | system 已带 Skills 元信息 + tools 含 `skill`，模型先返回 `tool_call: skill(pptx)` |
| 2 | call#2 | 请求消息中出现 `assistant(skill)` + `tool(<skill ...全文...>)`，随后进入文件探索 |
| 3 | 中间轮 | 连续调用 `glob/ls/read_file` 读取 `SKILL.md/html2pptx.md` 与工程文件 |
| 4 | 中间轮 | `write_file/edit_file/execute` 迭代生成脚本与 PPT |
| 5 | 末轮 | `execute(ls -la *.pptx)` 校验后收敛，输出绝对路径 |

### 3.2 opencode（CLI 成功链路，38 steps）

| 步骤 | 发生位置 | 关键动作 |
|---|---|---|
| 1 | step#1 | `tool: skill` 成功，状态里返回 `<skill_content name=\"pptx\">...` |
| 2 | step#2 | 读取 `html2pptx.md`，按 skill 指南切到 html2pptx 工作流 |
| 3 | 中间 steps | 大量 `write/edit/bash` 迭代修正 HTML 校验错误 |
| 4 | step#37 | `bash` 生成 PPT 成功 |
| 5 | step#38 | `bash ls -lh` 校验文件，最后文本只返回绝对路径 |

### 3.3 pi-mono（7 次模型调用）

| 步骤 | 发生位置 | 关键动作 |
|---|---|---|
| 1 | call#1 | system 内已有 `<available_skills>`，模型先发 `tool_call: read(.../pptx/SKILL.md)` |
| 2 | call#2 | 请求消息中出现 `tool` 返回的 `SKILL.md` 全文 |
| 3 | call#3 | 模型继续 `read(.../html2pptx.md)` 深读子文档 |
| 4 | call#4~6 | 进入 `bash/write/bash` 执行链，生成并运行脚本 |
| 5 | call#7 | 再次 `bash ls -lh` 校验后，最终回答绝对路径 |

## 4. 结论（教学版）

- deepagents: 双通道（system + tool）最“显式”，模型很容易命中 skill。  
- opencode: 强工具化（skill tool），语义清楚，流程可观测性强。  
- pi-mono: 元信息先放 system，正文按需 read，体现“渐进披露”最直接。  

同一个 skill（pptx）在三者中的本质差异不是“有没有 skill”，而是“Skill 正文通过哪条消息通道进入模型上下文”。

## 4.1 大白话总结

- deepagents：先在 system 里告诉模型有哪些 skill；`skill` 工具主要是“加载按钮”。模型知道有 `pptx` 后，调用 `skill(name)` 把正文拉进上下文。  
- opencode：把 skill 清单直接写在 `skill` 工具说明里。模型看工具说明就知道有啥 skill，然后调用 `skill(name)` 加载正文。  
- pi-mono：system 里给 skill 清单和路径，但没有独立 `skill` 工具；模型用 `read` 去读 `SKILL.md`，把正文读进上下文后再执行。  

一句话：一个偏“system 告知 + 工具加载”（deepagents），一个偏“工具自带目录 + 工具加载”（opencode），一个偏“system 告知 + read 文件加载”（pi-mono）。

## 4.2 哪种更接近 Claude

更接近 Claude 风格的是 **deepagents**（其次是 pi-mono）。

原因（简版）：
- Claude 的 skill 使用方式是“先给可用 skill 元信息，再按需加载正文（progressive disclosure）”。  
- deepagents 同时体现了这两点：system 提供可用 skills，命中时通过 `skill(name)` 单独加载。  
- pi-mono 也有“先元信息后按需加载”，但它用的是通用 `read` 文件，不是专门的 `skill` 加载动作。  
- opencode 能力很强，但把 skill 目录主要塞在 tool description 里，这点和 Claude 的呈现习惯不完全一致。  

## 5. 备注

- opencode 的“OpenAI 报文级”抓包在另一次 SDK probe 中出现过 `skill -> No context found for instance`，这属于探针环境上下文不完整，不影响上述 CLI 成功链路结论。  
  - 参考：`/Users/admin/work/agent_loop/logs/opencode_ppt_raw_calls_20260214_170709.json`
