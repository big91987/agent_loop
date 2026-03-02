#!/usr/bin/env bun
import fs from "node:fs/promises";
import path from "node:path";

import { getMemorySearchManager } from "/Users/admin/work/openclaw/src/memory/index.ts";

const DEFAULT_BENCHMARK =
  "/Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md";

const QUERIES = [
  "我中午想吃煎饼，帮我下个单。",
  "给我推荐个咖啡。",
  "我昨天被我家猫挠了一下，怎么处理比较稳妥。",
  "我想跳槽，先按我的背景给我起一版简历大纲我看看看。",
  "下周分享会我还没想好开场，按我定过的方向给个题目和提纲。",
  "我明天去杭州，帮我列个订票要点清单，尤其座位怎么选。",
  "我电脑重装了，先把我平时开工常用的软件清单列给我。",
  "我现在要出门，钥匙找不到了，你帮我按我平时习惯排查一下。",
];

type Msg = { role: "user" | "assistant"; content: string };

function parseCase13Messages(markdown: string): Msg[] {
  const header = markdown.match(/^##+\s+.*\(Case\s+13\).*$/m);
  if (!header) throw new Error("Case 13 header not found");
  const start = header.index! + header[0].length;
  const tail = markdown.slice(start);
  const nextHeader = tail.search(/^##\s+/m);
  const section = nextHeader >= 0 ? tail.slice(0, nextHeader) : tail;

  const rows = section
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("|"));

  const out: Msg[] = [];
  for (const row of rows) {
    const cells = row
      .slice(1, -1)
      .split("|")
      .map((c) => c.trim());
    if (cells.length < 3) continue;
    const roleRaw = cells[1].toLowerCase();
    if (roleRaw !== "user" && roleRaw !== "agent" && roleRaw !== "assistant") continue;
    const content = cells[2];
    if (!content || content === ":---") continue;
    out.push({ role: roleRaw === "user" ? "user" : "assistant", content });
  }
  if (!out.length) throw new Error("No messages parsed from Case 13");
  return out;
}

async function main() {
  const benchmarkPath = process.argv[2] || DEFAULT_BENCHMARK;
  const text = await fs.readFile(benchmarkPath, "utf-8");
  const messages = parseCase13Messages(text);

  const runtime = path.join(
    "/Users/admin/work/agent_loop/backups/memory/openclaw_case13_runtime",
    String(Date.now()),
  );
  const workspaceDir = path.join(runtime, "workspace");
  const memoryDir = path.join(workspaceDir, "memory");
  const indexPath = path.join(runtime, "memory-main.sqlite");
  const stateDir = path.join(runtime, "state");

  await fs.mkdir(memoryDir, { recursive: true });
  await fs.mkdir(stateDir, { recursive: true });

  const lines = messages.map((m, i) => `${String(i + 1).padStart(2, "0")} [${m.role}] ${m.content}`);
  const memoryBody = `# Case13 Dialogue\n\n${lines.join("\n")}\n`;
  await fs.writeFile(path.join(memoryDir, "2026-02-13-case13.md"), memoryBody, "utf-8");

  process.env.OPENCLAW_STATE_DIR = stateDir;

  const cfg: any = {
    agents: {
      defaults: {
        workspace: workspaceDir,
        memorySearch: {
          provider: "auto",
          store: { path: indexPath, vector: { enabled: false } },
          chunking: { tokens: 800, overlap: 80 },
          sync: { watch: false, onSessionStart: false, onSearch: false, intervalMinutes: 0 },
          query: {
            maxResults: 8,
            minScore: 0,
            hybrid: {
              enabled: true,
              vectorWeight: 0.7,
              textWeight: 0.3,
              candidateMultiplier: 4,
              mmr: { enabled: false, lambda: 0.7 },
              temporalDecay: { enabled: false, halfLifeDays: 30 },
            },
          },
        },
      },
      list: [{ id: "main", default: true }],
    },
  };

  const mgrResult = await getMemorySearchManager({ cfg, agentId: "main" });
  if (!mgrResult.manager) throw new Error(`openclaw manager init failed: ${mgrResult.error || "unknown"}`);
  const manager = mgrResult.manager;
  try {
    await manager.sync?.({ reason: "case13", force: true });
    console.log("=== OPENCLAW CASE13 INPUT ===");
    console.log(JSON.stringify({ benchmarkPath, messageCount: messages.length }, null, 2));
    console.log("=== OPENCLAW MEMORY STATUS ===");
    console.log(JSON.stringify(manager.status(), null, 2));

    for (let i = 0; i < QUERIES.length; i++) {
      const q = QUERIES[i];
      const result = await manager.search(q, { maxResults: 8, minScore: 0 });
      console.log(`=== OPENCLAW QUERY ${i + 1} ===`);
      console.log(JSON.stringify({ query: q, result }, null, 2));
    }
  } finally {
    await manager.close?.();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
