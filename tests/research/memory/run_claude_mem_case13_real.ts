#!/usr/bin/env bun
import fs from "node:fs/promises";
import path from "node:path";

import { SessionStore } from "/tmp/memory_scan_round2/claude-mem/src/services/sqlite/SessionStore.ts";
import { SessionSearch } from "/tmp/memory_scan_round2/claude-mem/src/services/sqlite/SessionSearch.ts";
import { SearchOrchestrator } from "/tmp/memory_scan_round2/claude-mem/src/services/worker/search/SearchOrchestrator.ts";
import { ChromaSync } from "/tmp/memory_scan_round2/claude-mem/src/services/sync/ChromaSync.ts";
import { ChromaMcpManager } from "/tmp/memory_scan_round2/claude-mem/src/services/sync/ChromaMcpManager.ts";

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

function parseArg(name: string): string | undefined {
  const idx = process.argv.findIndex((v) => v === name);
  if (idx < 0) return undefined;
  return process.argv[idx + 1];
}

function parseCase13Messages(markdown: string): Msg[] {
  const header = markdown.match(/^##+\s+.*\(Case\s+13\).*$/m);
  if (!header) throw new Error("Case 13 header not found");
  const start = header.index! + header[0].length;
  const tail = markdown.slice(start);
  const nextHeader = tail.search(/^##\s+/m);
  const section = nextHeader >= 0 ? tail.slice(0, nextHeader) : tail;
  const out: Msg[] = [];
  for (const row of section.split("\n").map((s) => s.trim())) {
    if (!row.startsWith("|")) continue;
    const cells = row
      .slice(1, -1)
      .split("|")
      .map((c) => c.trim());
    if (cells.length < 3) continue;
    const role = cells[1].toLowerCase();
    if (role !== "user" && role !== "agent" && role !== "assistant") continue;
    const content = cells[2];
    if (!content || content === ":---") continue;
    out.push({ role: role === "user" ? "user" : "assistant", content });
  }
  if (!out.length) throw new Error("No Case13 messages parsed");
  return out;
}

async function main() {
  const benchmarkPath = parseArg("--benchmark-path") || process.argv[2] || DEFAULT_BENCHMARK;
  const withChromaRaw = parseArg("--with-chroma") ?? "true";
  const withChroma = withChromaRaw !== "false";
  const text = await fs.readFile(benchmarkPath, "utf-8");
  const messages = parseCase13Messages(text);

  const runtime = path.join(
    "/Users/admin/work/agent_loop/backups/memory/claude_mem_case13_runtime",
    String(Date.now()),
  );
  await fs.mkdir(runtime, { recursive: true });
  const dbPath = path.join(runtime, "claude-mem-case13.db");

  const sessionStore = new SessionStore(dbPath);
  const sessionSearch = new SessionSearch(dbPath);
  const project = "case13-probe";
  const chromaSync = withChroma ? new ChromaSync(project) : null;
  const orchestrator = new SearchOrchestrator(sessionSearch, sessionStore, chromaSync);

  const contentSessionId = "content-case13";
  const memorySessionId = "memory-case13";
  const sessionDbId = sessionStore.createSDKSession(contentSessionId, project, "case13 bootstrap");
  sessionStore.ensureMemorySessionIdRegistered(sessionDbId, memorySessionId);

  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    const createdAtEpoch = Date.now() + i;
    const obs = {
      type: m.role === "user" ? "discovery" : "change",
      title: `${m.role.toUpperCase()}-${i + 1}`,
      subtitle: null,
      facts: [],
      narrative: m.content,
      concepts: [],
      files_read: [],
      files_modified: [],
    };
    const stored = sessionStore.storeObservation(
      memorySessionId,
      project,
      obs,
      i + 1,
      0,
      createdAtEpoch,
    );
    if (chromaSync) {
      await chromaSync.syncObservation(
        stored.id,
        memorySessionId,
        project,
        obs,
        i + 1,
        createdAtEpoch,
        0,
      );
    }
  }

  console.log("=== CLAUDE-MEM CASE13 INPUT ===");
  console.log(JSON.stringify({ benchmarkPath, messageCount: messages.length, dbPath, withChroma }, null, 2));

  const filterOnly = await orchestrator.search({ project, limit: 8 });
  console.log("=== CLAUDE-MEM FILTER-ONLY CHECK ===");
  console.log(JSON.stringify(filterOnly, null, 2));

  for (let i = 0; i < QUERIES.length; i++) {
    const q = QUERIES[i];
    const result = await orchestrator.search({ query: q, limit: 8, project });
    console.log(`=== CLAUDE-MEM QUERY ${i + 1} ===`);
    console.log(JSON.stringify({ query: q, result }, null, 2));
  }

  if (chromaSync) {
    await chromaSync.close();
    await ChromaMcpManager.getInstance().stop();
  }
  sessionStore.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
