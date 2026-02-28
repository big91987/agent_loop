---
name: memory-research-method
description: Component-agnostic methodology for evaluating memory systems using concept-first explanation, standardized case design, raw-result-first reporting, and root-cause analysis.
---

# Memory Research Method

Use this skill when comparing or validating any memory system for teaching or engineering decisions.

## Goal

Produce reports that are:
- easy for students to understand
- reproducible for engineers
- directly useful for product decisions

## Core Rule

Always use this order:
1. Concepts first (define terms clearly with examples)
2. Mechanism next (end-to-end flow)
3. Raw results first (show real output, not only summary)
4. Root-cause mapping (link behavior to code path)
5. Decision-oriented conclusion

## Mechanism-First Writing Rule (hard requirement)

Do not write mechanism sections as "call sequence + file path list".
For each component, you must explain mechanism in this fixed order:
1. Extraction: how raw dialogue becomes memory items
2. Storage: how items are persisted/updated/scoped
3. Retrieval: how query becomes recalled items/ranked items
4. Loop injection: how recalled memory is injected back into agent context (if applicable)

For each mechanism step, always include:
- Input objects
- Processing logic
- Output objects
- Failure modes
- One minimal example

Code paths are evidence only. They cannot replace mechanism explanation.

## Mandatory Evidence Rule (Open-source)

If the target is open-source, do not write a conclusion from docs alone.
You must do both:
1. Read the actual code path for the mechanism you are evaluating
2. Run a real test set (or reproducible minimal benchmark) and attach raw output

No "final assessment" is allowed without these two evidence types.

## Collaboration Escalation Rule (must follow)

If you cannot complete a required validation in the current environment, do **not** downgrade to a shallow conclusion.
You must immediately:
1. State the exact blocker (command + exact error).
2. State what has already been verified and what remains unverified.
3. Ask the user for targeted help to unblock (credentials/network/dependency/toolchain/runtime permissions).
4. Resume full-depth validation after unblock, using the same benchmark and output format.

Examples of blockers that require escalation:
- API/network/DNS failures
- missing runtime dependencies that cannot be installed in-session
- missing local services (DB/vector store)
- filesystem/permission restrictions

## Concept Model (must explain first)

For any memory system, first define its own core concepts in plain language (do not assume shared naming across products).
Common concept slots to map:
- smallest memory unit (e.g. item/record/node)
- memory semantics (e.g. type/tag/schema)
- grouping/indexing layer (e.g. category/namespace/collection)
- retrieval scope (user/session/workspace/project)

And explicitly answer:
- what each term means
- how they differ
- one concrete example per term
- whether defaults exist
- whether they are configurable

## Evaluation Workflow

### Step 1: Define evaluation targets

Use exactly three targets:
- trigger correctness: should retrieval be triggered?
- recall effectiveness: after trigger, does it hit expected memory?
- recall purity: does it include irrelevant memory?

Additionally, for each product, define 1-3 **sellpoint probes**:
- each probe must map to a product-claimed differentiator (from docs/code)
- each probe must be executable (not just conceptual)
- each probe must produce side-by-side output (baseline vs probe condition)

### Step 2: Build test cases

Case design rules:
- use realistic daily-language tasks, not "exam-style memory questions"
- each case item is: `Query-N + Expected Recall-N`
- keep case structure uniform across components

Recommended coverage:
- food preference
- routine/habit
- relationship/pet
- work identity/plan
- travel/seat preference
- tool usage and object location

### Step 3: Run and collect full raw output

Never only provide a link.
In report body, include raw output blocks directly.

Minimum fields to extract per query:
- `needs_retrieval`
- `items_hit`
- top hits text (if any)

### Step 4: Summarize with one standard table

Required table columns:
- Query
- Expected Recall
- needs_retrieval
- items_hit
- Match/Gap
- Noise

### Step 5: Root-cause analysis

For each failure, map to mechanism:
- not triggered -> routing layer
- triggered but empty -> retrieval execution layer
- hit with noise -> ranking/filtering layer

Attach code evidence with minimal key paths only.

### Step 6: Sellpoint-to-Evidence mapping (mandatory)

For each claimed product advantage, provide:
- Claim: what the product says it is good at
- Mechanism: how code implements that claim
- Probe Design: how we test this claim
- Observed Output: raw output snippet from the probe
- Assessment: verified / partially verified / not verified

Do not accept "feature exists in code" as proof of advantage.
The advantage must be demonstrated by probe output.

## Report Structure Template

Use this 5-section structure:
1. Component Positioning and Concept Definitions
2. Validation Results
3. Mechanism and Root-Cause Analysis
4. Engineering Conclusion and Adoption Advice
5. Evidence Index

## Writing Style Constraints

- concept-first, then mechanism, then result
- show raw output before interpretation
- avoid generic claims without query-level evidence
- prefer concise language; avoid long theoretical background
- use repo-relative paths in docs

## Quality Checklist

Before finalizing, ensure:
- [ ] product-specific core terms are defined with examples
- [ ] case format is uniform (`Query-N + Expected Recall-N`)
- [ ] raw test output is embedded in report
- [ ] summary table exists and is query-level
- [ ] conclusions are tied to observed results, not assumptions
- [ ] paths are relative, not absolute

## Shared Benchmark: Case 13 (for cross-system comparison)

This benchmark is the shared base case for evaluating memory systems across products.
Use it to compare both mechanism and effect:
- mechanism: trigger and retrieval path behavior
- effect: trigger correctness, hit quality, noise level

### Case 13 Dialogue Scope

- Source file (local copy): `research/memory-research-method/agent_memory_case13_shared.md`
- Canonical source: `tests/research/memory/data/agent_memory_case13_shared.md`
- Dialogue length: 62 turns
- Topic distribution: personal profile, preferences, habits, relationship, work plan, travel, tools, object location

### Case 13 Query Set (standardized)

Use these 8 queries as the default shared query pack:

1. `我中午想吃煎饼，帮我下个单。`
2. `给我推荐个咖啡。`
3. `我昨天被我家猫挠了一下，怎么处理比较稳妥。`
4. `我想跳槽，先按我的背景给我起一版简历大纲我看看看。`
5. `下周分享会我还没想好开场，按我定过的方向给个题目和提纲。`
6. `我明天去杭州，帮我列个订票要点清单，尤其座位怎么选。`
7. `我电脑重装了，先把我平时开工常用的软件清单列给我。`
8. `我现在要出门，钥匙找不到了，你帮我按我平时习惯排查一下。`

### Expected Recall (query-level)

1. Query-1 expected:
- user dislikes cilantro
- user tends to avoid cilantro after previous bad takeaway experience

2. Query-2 expected:
- user switched from iced Americano to latte
- reason: stomach discomfort

3. Query-3 expected:
- cat name is 奶油
- cat is ragdoll

4. Query-4 expected:
- company: 星云科技
- role: product manager
- domain/project context: AI robotics / industrial automation

5. Query-5 expected:
- internal sharing topic: machine learning

6. Query-6 expected:
- flight seat preference: window seat
- user moved from Beijing to Shanghai

7. Query-7 expected:
- common work apps: Chrome / Slack / VSCode
- current code context around app.py usage pattern

8. Query-8 expected:
- key location habit: kitchen door back hook

### Required Result Fields

For each query, always report:
- `needs_retrieval`
- `items_hit`
- top hit content
- match vs expected recall
- noise notes (if any)
