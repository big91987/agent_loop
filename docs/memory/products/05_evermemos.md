# EverMemOS 深度调研报告（主机制版）

## -1. 先讲最核心名词：MemCell（必须先懂）

`MemCell` 是 EverMemOS 的“记忆原子单元”，可以把它理解为：
- 一段已经被系统判定为“可独立成段”的对话片段；
- 后续所有结构化记忆（episode / event_log / foresight / profile）的上游输入。

它解决的问题是：
- 不让系统对每条消息都立刻抽取，避免碎片化与噪声爆炸；
- 先按“边界”把对话切成有语义完整度的块，再做抽取与检索。

它在链路中的位置是：
`原始消息流 -> 边界检测 -> MemCell -> 多类记忆抽取 -> 存储/检索`

如果没有产出 `MemCell`：
- 后面的 episode/event_log/foresight 通常都不会产出；
- 你看到的“召回为空”往往是上游没触发，不是下游检索器先天失效。

---

## 0. 先看结论（给学生的主线）

EverMemOS 的核心不是“检索更花哨”，而是这三件事组合在一起：
1. 先把对话切成“可管理单元”`MemCell`（边界检测）。  
2. 再把 `MemCell` 转成多种记忆对象（`episode / event_log / foresight / profile`）。  
3. 最后按问题复杂度选择检索策略（轻量检索或 agentic 检索）。  

它的最大亮点是：把“记忆写入是否触发”作为一级机制（boundary），而不是所有消息无脑入库。  
你这次 case13 结果为 0，正是因为这个一级机制没有被触发。

---

## 1. 产品最大的机制与亮点（What / Why）

## 1.1 What：它是什么

EverMemOS 是“记忆管线系统”，不是单纯向量库。
它维护的是一条完整链路：
`对话流 -> MemCell -> 结构化记忆对象 -> 检索 -> 回注模型`。

## 1.2 Why：它和普通 RAG 的关键差异

- 普通做法常见问题：原始对话直接切片入库，噪声高、时序弱、主题边界弱。  
- EverMemOS 试图解决的点：先做边界，再抽取结构化对象，再检索。  
- 这让系统更像“记忆操作系统”，而不是“向量检索插件”。

## 1.3 最大亮点（教学版一句话）

**亮点不是“检索多强”，而是“什么时候写入、写成什么对象、再怎么取回”这三步被明确工程化了。**

---

## 2. 机制全景图（How）

1. 写入入口：`memorize()`。  
2. 边界判定：`extract_memcell()`（决定当前轮是否形成 MemCell）。  
3. 形成 MemCell 后才继续抽取：  
- `episode`（必做）  
- `foresight`、`event_log`（assistant 场景）  
- `profile`（画像更新链路）  
4. 持久化与索引：Mongo + ES/Milvus。  
5. 检索层：`keyword / vector / hybrid / rrf / agentic`。

---

## 3. 你的 case13 为什么“看起来没效果”

## 3.1 现象

- `total_extracted=0`
- `episodic/event_log/foresight` 为空
- query 命中为 0

## 3.2 根因（主要机制层）

本次脚本是“一次性喂 62 条到 `new_raw_data_list`，history 为空”。  
而 EverMemOS 的边界机制在首轮 history 为空时默认不结束当前段（不产出 memcell）。

所以本次结果本质是：
- 不是“抽取器能力差”；  
- 是“没走到抽取触发点”。

## 3.3 教学意义

评估 EverMemOS 时第一优先级应该是：
1. 有没有产出 memcell。  
2. 产出后抽取对象是否完整。  
3. 最后才是检索命中率。  

---

## 4. 论文/README 亮点口径（去营销化）

可核验共识：
- 三段式记忆管线存在且有代码落地。  
- 评测口径在 LoCoMo 上是 `92.3x%` 区间（仓库里有 93 / 92.3 / 92.32 多种写法）。  

需要注意：
- 传播材料会强调“发布即 SOTA”；  
- 研究报告里应该统一写“口径 + 数据来源”，避免混用。

---

## 5. 源码证据（附录，给想下钻的人）

主要代码路径：
- `/tmp/memory_scan_round2/EverMemOS/src/biz_layer/mem_memorize.py`
- `/tmp/memory_scan_round2/EverMemOS/src/memory_layer/memory_manager.py`
- `/tmp/memory_scan_round2/EverMemOS/src/memory_layer/memcell_extractor/conv_memcell_extractor.py`
- `/tmp/memory_scan_round2/EverMemOS/src/agentic_layer/memory_manager.py`
- `/tmp/memory_scan_round2/EverMemOS/src/agentic_layer/agentic_utils.py`

文档路径：
- `/tmp/memory_scan_round2/EverMemOS/README.md`
- `/tmp/memory_scan_round2/EverMemOS/docs/OVERVIEW.md`
- `/tmp/memory_scan_round2/EverMemOS/evaluation/README.md`

本次 case13 运行材料：
- 脚本：`/Users/admin/work/agent_loop/tests/research/memory/run_evermemos_case13_real.py`
- 输出：`/Users/admin/work/agent_loop/backups/memory/evermemos_case13_output.txt`
