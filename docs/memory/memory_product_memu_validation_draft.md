# MemU 调研报告（草稿）

## 1. 组件定位与能力边界

### 1.1 组件定位
MemU 是一个面向 Agent 的记忆组件，核心提供两类能力：
- `memorize`：从历史对话中抽取并写入记忆条目
- `retrieve`：根据用户当前查询从记忆中检索相关条目

它的职责是“存与查”，不负责直接执行任务，也不负责最终回答生成。

### 1.2 核心概念（先把名词讲清楚）
#### item（记忆条目）
- `item` 是 MemU 里最小的记忆单位。
- 它不是整段聊天记录，而是从对话里抽出来的一条“可复用信息”。
- 例子：
  - `用户讨厌香菜`
  - `用户订票偏好靠窗`
  - `用户下周要做机器学习分享`

#### type（记忆性质）
- `type` 描述这条 item 的性质。
- 默认 type（MemU 默认）：`profile / event / knowledge / behavior`
  - `profile`：稳定信息（身份、偏好、关系）
  - `event`：具体发生过的事
  - `knowledge`：知识性结论或事实
  - `behavior`：习惯或行为模式

#### category（记忆主题）
- `category` 描述这条 item 属于哪个主题篮子。
- 默认 category（MemU 默认 10 类）：
  - `personal_info / preferences / relationships / activities / goals / experiences / knowledge / opinions / habits / work_life`

一句话区分：
- `item`：记了什么
- `type`：这条记忆是什么性质
- `category`：这条记忆属于哪个主题

可配置性：
- `memory_types`、`memory_categories` 都可自定义。
- 新增 type 建议配对应 `memory_type_prompts`，否则抽取稳定性会下降。

### 1.3 整体流程（写入 + 检索）
MemU 的整体流程分两条链路：

#### 写入链路（memorize）
1. 输入原始对话（messages）
2. 抽取 item（结构化记忆条目）
3. 给每条 item 标注 type
4. 给每条 item 归类 category
5. 持久化存储

#### 检索链路（retrieve）
1. 先判断是否需要检索（`route_intention`）
2. 若需要，先召回 category
3. 再在相关 category 下召回 item
4. 返回命中项（categories/items）

两条链路的关系：
- 写入负责“把对话整理成可检索记忆”
- 检索负责“在需要时取回记忆”

### 1.4 能力边界
本次调研关注长期记忆链路的三个核心能力：
1. 检索触发正确性：该检索时是否能触发检索
2. 召回有效性：触发后是否能命中应召回信息
3. 召回纯度：命中内容是否夹杂无关信息

不在本次范围：UI、工具执行能力、端到端任务完成度。

---

## 2. 效果验证

### 2.1 Case 与查询集
- 对话基准：`tests/research/memory/data/agent_memory_case13_shared.md`（Case 13，62 轮）
- 查询集：同文件中的 `触发查询 (Query)-1..8`
- 输出：`backups/memu/runs/memu_rich_demo_daily_habits_output_after_user_edit.txt`

### 2.2 结果总览（直接看表）

| Query | needs_retrieval | items_hit | 现象 |
|---|---:|---:|---|
| Query-1 | False | 0 | 该检索未触发 |
| Query-2 | True | 8 | 有效命中，但有噪声 |
| Query-3 | False | 0 | 该检索未触发 |
| Query-4 | False | 0 | 该检索未触发 |
| Query-5 | True | 8 | 有效命中，但有噪声 |
| Query-6 | False | 0 | 该检索未触发 |
| Query-7 | True | 0 | 触发后空召回 |
| Query-8 | True | 0 | 触发后空召回 |

### 2.3 结果读法（简版）
我们主要看三件事：
1. 该检索时是否触发（`needs_retrieval`）
2. 触发后是否有有效命中（`items_hit`）
3. 命中内容是否有噪声（人工看命中条目）

汇总指标：
- 检索触发率：4/8 = 50%
- 有效命中率（`items_hit>0`）：2/8 = 25%
- 触发后空召回率（在触发样本中）：2/4 = 50%

### 2.4 典型样例
成功样例（Query-2：咖啡习惯）：
- 命中到“从冰美式换成拿铁”“因胃不适而调整”
- 同时混入了非核心条目（如机票偏好）

失败样例 A（Query-1：点餐避雷）：
- `needs_retrieval=False`
- 直接导致 `items_hit=0`

失败样例 B（Query-8：按习惯找钥匙）：
- `needs_retrieval=True`
- 但 `items_hit=0`

结论：该组件在真实表达下同时存在“触发不稳”和“触发后命中不稳”两类问题。

### 2.5 测试输出原文（完整）

```text
[CONFIG] model=MiniMax-M2.1 base_url=https://api.minimaxi.com/v1 provider=minimaxi
[BENCHMARK] path=/Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_benchmark_v6_full.md
[BENCHMARK] case=auto | parsed_messages=73
[INPUT FILE] /var/folders/kq/txd4v7zx7qz3p6rdhfsm4d980000gn/T/memu_rich_real_y8pxtjwp/rich_conversation.json

=== INPUT DIALOGUE (FULL) ===
01. [2026-02-26T08:00:00Z] (user) 帮我打开Chrome、Slack和VSCode。
02. [2026-02-26T08:00:01Z] (assistant) 好的，已为您启动Chrome、Slack和Visual Studio Code。
03. [2026-02-26T08:00:02Z] (user) 在Chrome里搜索一下“今天天气怎么样”。
04. [2026-02-26T08:00:03Z] (assistant) 搜索结果显示，今天晴，28度，微风。
05. [2026-02-26T08:00:04Z] (user) 好的。现在切换到Slack，给“项目群”发个消息，说“需求文档已更新”。
06. [2026-02-26T08:00:05Z] (assistant) 消息已发送至“项目群”。
07. [2026-02-26T08:00:06Z] (user) 很好。现在切换到VSCode，打开项目文件夹里的`app.py`文件。
08. [2026-02-26T08:00:07Z] (assistant) 好的，已在VSCode中打开`app.py`。
09. [2026-02-26T08:00:08Z] (user) 向下滚动100行。
10. [2026-02-26T08:00:09Z] (assistant) 已向下滚动100行。
11. [2026-02-26T08:00:10Z] (user) 帮我把当前窗口的所有代码都复制一下。
12. [2026-02-26T08:00:11Z] (user) 嗨，在吗？
13. [2026-02-26T08:00:12Z] (assistant) 在的，怎么了？
14. [2026-02-26T08:00:13Z] (user) 没啥，就是刚换了工作，有点兴奋又有点慌，想找人说说话。
15. [2026-02-26T08:00:14Z] (assistant) 换新工作是大事！恭喜你。是什么样的工作呀？
16. [2026-02-26T08:00:15Z] (user) 一家叫"星云科技"的公司，做AI机器人相关的项目，我在里面做产品经理，我叫李明。
17. [2026-02-26T08:00:16Z] (assistant) 李明你好！AI机器人，听起来就很酷，星云科技是做什么方向的机器人？
18. [2026-02-26T08:00:17Z] (user) 主要是工业场景的自动化，说起来挺复杂的，以后有机会再聊。你最近怎么样？
19. [2026-02-26T08:00:18Z] (assistant) 我挺好的，谢谢关心。你刚入职，有没有什么不适应的地方？
20. [2026-02-26T08:00:19Z] (user) 还好，同事都挺好的。就是任务量有点大，上来就给我压了个新项目。
21. [2026-02-26T08:00:20Z] (assistant) 新人嘛，往往都是这样，先扛住，等熟悉了就好了。
22. [2026-02-26T08:00:21Z] (user) 是这个道理。对了，你知道最近有什么好看的剧吗？我想下班回家放松一下。
23. [2026-02-26T08:00:22Z] (assistant) 最近《繁花》口碑很好，是王家卫导演的，讲上海九十年代的商战故事，画面很有质感。
24. [2026-02-26T08:00:23Z] (user) 哦？王家卫的剧？那画面肯定很美，我加到片单里了。
25. [2026-02-26T08:00:24Z] (assistant) 对，每一帧都像电影，你应该会喜欢。
26. [2026-02-26T08:00:25Z] (user) 好。我先去忙了，下班再聊。
27. [2026-02-26T08:00:26Z] (assistant) 好的，下班见！
28. [2026-02-26T08:00:27Z] (user) 我回来了，累死了。今天中午点外卖踩雷了，心情还没缓过来。
29. [2026-02-26T08:00:28Z] (assistant) 哎，怎么了？
30. [2026-02-26T08:00:29Z] (user) 点了碗牛肉粉，结果老板给我放了一大把香菜，我最讨厌那个味道了，闻到就反胃，整碗都没吃。
31. [2026-02-26T08:00:30Z] (assistant) 这也太倒霉了，白白浪费了一顿饭。以后点餐一定要在备注里写清楚。
32. [2026-02-26T08:00:31Z] (user) 对，我已经长记性了。不说这个了，我回家看了会儿我家猫，心情好多了。
33. [2026-02-26T08:00:32Z] (assistant) 你养猫啊？什么品种的？
34. [2026-02-26T08:00:33Z] (user) 布偶猫，我给它取名叫"奶油"，因为它毛茸茸的，颜色也是奶白色的，看着就想揉。
35. [2026-02-26T08:00:34Z] (assistant) 奶油！这名字太贴切了，布偶猫的毛真的很像奶油的质感。
36. [2026-02-26T08:00:35Z] (user) 哈哈，就是这个感觉。它最近好像有点无聊，我想给它买个新玩具。
37. [2026-02-26T08:00:36Z] (assistant) 猫咪都喜欢有新鲜感的东西，可以试试电动的逗猫棒，或者那种有小球在轨道里滚的玩具，布偶猫一般都很喜欢追。
38. [2026-02-26T08:00:37Z] (user) 好主意，我去看看。
39. [2026-02-26T08:00:38Z] (assistant) 好的，希望奶油喜欢。
40. [2026-02-26T08:00:39Z] (user) 说起来，我下周要在公司内部做个技术分享，还没想好讲什么，你帮我出出主意？
41. [2026-02-26T08:00:40Z] (assistant) 你在AI公司做产品，可以讲的角度很多。比如从产品视角看AI落地的难点，或者某个具体的技术方向的科普？
42. [2026-02-26T08:00:41Z] (user) 我最近在研究机器学习相关的东西，要不就讲这个？感觉大家都挺感兴趣的。
43. [2026-02-26T08:00:42Z] (assistant) 机器学习这个主题很好，既有深度又有广度，受众也广。定了的话，我可以帮你整理一些资料。
44. [2026-02-26T08:00:43Z] (user) 好，就定这个了。谢谢。
45. [2026-02-26T08:00:44Z] (assistant) 没问题，等你准备的时候跟我说。
46. [2026-02-26T08:00:45Z] (user) 嗯。对了，我女朋友叫小雨，下个月生日，我完全不知道送什么好。
47. [2026-02-26T08:00:46Z] (assistant) 送女朋友礼物确实是个难题。小雨平时有什么特别的爱好吗？
48. [2026-02-26T08:00:47Z] (user) 她好像什么都还好，不太挑。
49. [2026-02-26T08:00:48Z] (assistant) 那可以从体验类礼物入手，比如一次精致的下午茶、一场她喜欢的演唱会，或者一次旅行，都比实物更有记忆点。
50. [2026-02-26T08:00:49Z] (user) 旅行！我之前就说要带她去云南玩，一直没成行，要不借这个机会？
51. [2026-02-26T08:00:50Z] (assistant) 这个主意太好了，云南风景美，而且现在去天气也舒服，肯定是个大惊喜。
52. [2026-02-26T08:00:51Z] (user) 行，我去查查机票。我订票有个习惯，就是必须选靠窗的座位，喜欢看窗外的云，感觉很解压。
53. [2026-02-26T08:00:52Z] (assistant) 这个习惯很好，靠窗的视野确实不一样。
54. [2026-02-26T08:00:53Z] (user) 对。不过说起来，我上个月刚从北京搬到上海，人生地不熟的，还在适应。
55. [2026-02-26T08:00:54Z] (assistant) 哦，北京到上海，变化挺大的。气候、饮食、生活节奏都不一样，慢慢来。
56. [2026-02-26T08:00:55Z] (user) 气候好多了，没那么干燥。就是饮食还在摸索，上海的口味偏甜，我还不太习惯。
57. [2026-02-26T08:00:56Z] (assistant) 慢慢就习惯了，而且上海各地的菜系都有，总能找到合适的。
58. [2026-02-26T08:00:57Z] (user) 也是。对了，我最近喝咖啡的习惯也改了，以前早上必须一杯冰美式，现在喝完胃不舒服，换成拿铁了。
59. [2026-02-26T08:00:58Z] (assistant) 身体在提醒你了，拿铁因为加了奶，确实对肠胃更友好。
60. [2026-02-26T08:00:59Z] (user) 对，而且喝起来也没那么苦，我反而觉得还挺好喝的。
61. [2026-02-26T08:01:00Z] (assistant) 那就找到新的日常了，挺好的。
62. [2026-02-26T08:01:01Z] (user) 哈哈。好了，我要开始准备分享会了。我这里有份用户行为数据（user_data.csv），我想先分析一下，看看大家对哪些功能更感兴趣，好在分享会上举例子。
63. [2026-02-26T08:01:02Z] (assistant) 这个思路很好，有数据支撑的分享会会更有说服力。
64. [2026-02-26T08:01:03Z] (user) 我习惯用Python来做这类分析，你帮我写个读取和分析的脚本框架吧。
65. [2026-02-26T08:01:04Z] (assistant) 没问题，用Pandas读取CSV，然后用Matplotlib做可视化，这是最常用的组合。框架代码如下：`import pandas as pd; import matplotlib.pyplot as plt; df = pd.read_csv(\'user_data.csv\'); print(df.describe())` 你可以在这个基础上继续完善。
66. [2026-02-26T08:01:05Z] (user) 很好，我来完善一下。
67. [2026-02-26T08:01:06Z] (assistant) 好的，有问题随时问我。
68. [2026-02-26T08:01:07Z] (user) 好了，代码跑完了，数据挺有意思的。我到家了，顺手把钥匙挂在厨房门后的挂钩上了。
69. [2026-02-26T08:01:08Z] (assistant) 好的，钥匙在厨房门后的挂钩上，记住了。
70. [2026-02-26T08:01:09Z] (user) 我现在打开电脑，开了Chrome、Slack和VSCode，在VSCode里打开了`app.py`，准备继续写代码。
71. [2026-02-26T08:01:10Z] (assistant) 好的，当前在VSCode里看`app.py`。
72. [2026-02-26T08:01:11Z] (user) 嗯，先在Slack里回一下消息。
73. [2026-02-26T08:01:12Z] (assistant) 好的。

=== MEMORIZE RESULT ===
items: 29
categories: 5
  item1: [profile] The user's name is Li Ming
  item2: [profile] The user works as a product manager at Nebula Technology
  item3: [profile] The user enjoys watching TV shows to relax after work
  item4: [behavior] The user uses Chrome, Slack, and VSCode as their regular work tools for software development tasks
  item5: [behavior] The user enjoys watching TV dramas and films, particularly those with high visual quality such as director Wong Kar-wai's works
  item6: [behavior] When feeling emotionally unsettled, the user proactively reaches out to someone to chat and seek social interaction
  item7: [behavior] After work, the user likes to relax by watching TV shows or dramas
  item8: [event] The user recently changed jobs and joined "星云科技" (Nebula Technology) as a product manager working on AI robot projects
  item9: [event] Upon starting at the new company, the user was assigned a new project with a heavy workload
  item10: [profile] The user dislikes cilantro and feels nauseous when smelling it
  item11: [profile] The user has a Ragdoll cat named "Nai You"
  item12: [profile] The user works as a product manager at an AI company
  item13: [profile] The user prefers window seats when booking flights
  item14: [profile] The user switched from iced Americano to latte because iced coffee causes stomach discomfort
  item15: [behavior] The user looks at their cat to feel better when feeling down or unhappy
  item16: [behavior] The user always chooses window seats when booking flights because they like looking at clouds outside the window and find it relaxing
  item17: [behavior] The user switched from drinking iced Americano to latte in the morning because iced Americano upset their stomach
  item18: [event] The user ordered beef noodles for lunch today but found the dish had too much cilantro, which the user hates, resulting in not being able to eat the meal
  item19: [event] The user went home and spent time with their Ragdoll cat named "奶油" (Cream), which improved their mood
  item20: [event] The user has a technical sharing session at their company next week, and they decided to present on machine learning
  item21: [event] The user's girlfriend Xiaoyu has a birthday next month, and the user plans to take her on a trip to Yunnan as a gift
  item22: [event] The user moved from Beijing to Shanghai last month and is still adjusting to the new environment
  item23: [profile] The user prefers using Python for data analysis
  item24: [behavior] The user typically uses Python for data analysis tasks
  item25: [behavior] When arriving home, the user habitually hangs their keys on the hook behind the kitchen door
  item26: [behavior] When working, the user opens Chrome, Slack, and VSCode, and typically checks Slack messages before starting to code
  item27: [event] The user is preparing for a presentation (分享会) and has user behavior data (user_data.csv) to analyze
  item28: [event] The user ran the analysis code and found the data interesting
  item29: [event] The user arrived home and hung their keys on a hook behind the kitchen door

=== RETRIEVE CASE 1/8: Query-1 ===

=== RETRIEVE REQUEST ===
method: rag
where: {"user_id": "u_real_demo_001"}
queries:
  1. {"role": "user", "content": {"text": "我中午想吃煎饼，帮我下个单。"}}

=== RETRIEVE RESULT ===
needs_retrieval: False
categories hit: 0
items hit: 0

=== RETRIEVE CASE 2/8: Query-2 ===

=== RETRIEVE REQUEST ===
method: rag
where: {"user_id": "u_real_demo_001"}
queries:
  1. {"role": "user", "content": {"text": "我早上准备买杯咖啡，按我最近习惯你建议点啥？"}}

=== RETRIEVE RESULT ===
needs_retrieval: True
categories hit: 5
items hit: 8
  hit1: [profile] The user switched from iced Americano to latte because iced coffee causes stomach discomfort
  hit2: [behavior] The user switched from drinking iced Americano to latte in the morning because iced Americano upset their stomach
  hit3: [profile] The user prefers window seats when booking flights
  hit4: [event] The user is preparing for a presentation (分享会) and has user behavior data (user_data.csv) to analyze
  hit5: [profile] The user's name is Li Ming
  hit6: [behavior] After work, the user likes to relax by watching TV shows or dramas
  hit7: [event] The user's girlfriend Xiaoyu has a birthday next month, and the user plans to take her on a trip to Yunnan as a gift
  hit8: [event] The user recently changed jobs and joined "星云科技" (Nebula Technology) as a product manager working on AI robot projects

=== RETRIEVE CASE 3/8: Query-3 ===

=== RETRIEVE REQUEST ===
method: rag
where: {"user_id": "u_real_demo_001"}
queries:
  1. {"role": "user", "content": {"text": "我昨天被我家猫挠了一下，怎么处理比较稳妥。"}}

=== RETRIEVE RESULT ===
needs_retrieval: False
categories hit: 0
items hit: 0

=== RETRIEVE CASE 4/8: Query-4 ===

=== RETRIEVE REQUEST ===
method: rag
where: {"user_id": "u_real_demo_001"}
queries:
  1. {"role": "user", "content": {"text": "我想跳槽，先按我的背景给我起一版简历大纲我看看看。"}}

=== RETRIEVE RESULT ===
needs_retrieval: False
categories hit: 0
items hit: 0

=== RETRIEVE CASE 5/8: Query-5 ===

=== RETRIEVE REQUEST ===
method: rag
where: {"user_id": "u_real_demo_001"}
queries:
  1. {"role": "user", "content": {"text": "下周分享会我还没想好开场，按我定过的方向给个题目和提纲。"}}

=== RETRIEVE RESULT ===
needs_retrieval: True
categories hit: 5
items hit: 8
  hit1: [event] The user is preparing for a presentation (分享会) and has user behavior data (user_data.csv) to analyze
  hit2: [event] The user has a technical sharing session at their company next week, and they decided to present on machine learning
  hit3: [profile] The user's name is Li Ming
  hit4: [event] The user's girlfriend Xiaoyu has a birthday next month, and the user plans to take her on a trip to Yunnan as a gift
  hit5: [behavior] After work, the user likes to relax by watching TV shows or dramas
  hit6: [event] The user recently changed jobs and joined "星云科技" (Nebula Technology) as a product manager working on AI robot projects
  hit7: [profile] The user works as a product manager at an AI company
  hit8: [event] Upon starting at the new company, the user was assigned a new project with a heavy workload

=== RETRIEVE CASE 6/8: Query-6 ===

=== RETRIEVE REQUEST ===
method: rag
where: {"user_id": "u_real_demo_001"}
queries:
  1. {"role": "user", "content": {"text": "我明天去杭州，帮我列个订票要点清单，尤其座位怎么选。"}}

=== RETRIEVE RESULT ===
needs_retrieval: False
categories hit: 0
items hit: 0

=== RETRIEVE CASE 7/8: Query-7 ===

=== RETRIEVE REQUEST ===
method: rag
where: {"user_id": "u_real_demo_001"}
queries:
  1. {"role": "user", "content": {"text": "我电脑重装了，先把我平时开工常用的软件清单列给我。"}}

=== RETRIEVE RESULT ===
needs_retrieval: True
categories hit: 5
items hit: 0

=== RETRIEVE CASE 8/8: Query-8 ===

=== RETRIEVE REQUEST ===
method: rag
where: {"user_id": "u_real_demo_001"}
queries:
  1. {"role": "user", "content": {"text": "我现在要出门，钥匙找不到了，你帮我按我平时习惯排查一下。"}}

=== RETRIEVE RESULT ===
needs_retrieval: True
categories hit: 5
items hit: 0
```

---

## 3. 机制解释与根因分析

### 3.1 触发判定机制
MemU 在正式检索前先走 `route_intention`，让 LLM 判断是否需要检索。

关键路径：
- `retrieve()` 入口：`/tmp/memU/src/memu/app/retrieve.py:42`
- route 判定：`/tmp/memU/src/memu/app/retrieve.py:241`
- 判定函数：`/tmp/memU/src/memu/app/retrieve.py:746`

该设计的直接影响：
- 一旦判定 `needs_retrieval=False`，后续检索链路不会执行。

### 3.2 召回执行机制
当且仅当 `needs_retrieval=True` 时，才进入 category/item 召回。

关键路径：
- 跳过条件：`/tmp/memU/src/memu/app/retrieve.py:261`
- 继续召回与充分性判断：`/tmp/memU/src/memu/app/retrieve.py:289`

### 3.3 与本次结果的对应关系
- Query-1/3/4/6：主要问题是 route 误判（未进入召回）
- Query-7/8：进入召回后无命中（召回链路有效性不足）
- Query-2/5：有命中但含噪声（排序与筛选纯度不足）

---

## 4. 工程结论与采用建议

### 4.1 结论
在本次 Case 13 生活化验证中，MemU 的主要短板不是“不会存”，而是：
- 检索触发稳定性不足
- 触发后命中与纯度稳定性不足

### 4.2 采用建议
- 可将 MemU 作为“记忆流水线原型/教学底座”
- 不建议在当前默认配置下直接作为“高可靠长期记忆引擎”
- 若要进入生产，应先解决：
  - 触发判定可控性
  - 触发后空召回问题
  - 召回噪声治理

---

## 5. 证据索引

### 5.1 测试资产
- 共享基准：`tests/research/memory/data/agent_memory_case13_shared.md`
- 测试脚本：`tests/research/memory/run_memu_rich_demo_real.py`

### 5.2 输出记录
- 本次输出：`backups/memu/runs/memu_rich_demo_daily_habits_output_after_user_edit.txt`

### 5.3 源码路径（MemU）
- `retrieve` 入口：`/tmp/memU/src/memu/app/retrieve.py:42`
- route 判定：`/tmp/memU/src/memu/app/retrieve.py:241`
- 判定函数：`/tmp/memU/src/memu/app/retrieve.py:746`
- 跳过召回条件：`/tmp/memU/src/memu/app/retrieve.py:261`
