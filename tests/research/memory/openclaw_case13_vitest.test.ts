import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterAll, describe, expect, it, vi } from "vitest";
import { getMemorySearchManager } from "/Users/admin/work/openclaw/src/memory/index.ts";
import "/Users/admin/work/openclaw/src/memory/test-runtime-mocks.ts";

const BENCHMARK =
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

let embedBatchCalls = 0;
vi.mock("/Users/admin/work/openclaw/src/memory/embeddings.ts", () => {
  const embedText = (text: string) => {
    const lower = text.toLowerCase();
    const alpha = lower.split("奶油").length - 1;
    const beta = lower.split("香菜").length - 1;
    const gamma = lower.split("拿铁").length - 1;
    const delta = lower.split("钥匙").length - 1;
    return [alpha, beta, gamma, delta];
  };
  return {
    createEmbeddingProvider: async () => ({
      requestedProvider: "openai",
      provider: {
        id: "mock",
        model: "mock-embed",
        embedQuery: async (text: string) => embedText(text),
        embedBatch: async (texts: string[]) => {
          embedBatchCalls += 1;
          return texts.map(embedText);
        },
      },
    }),
  };
});

function parseCase13Messages(markdown: string): Array<{ role: "user" | "assistant"; content: string }> {
  const header = markdown.match(/^##+\s+.*\(Case\s+13\).*$/m);
  if (!header) throw new Error("Case13 header not found");
  const start = header.index! + header[0].length;
  const tail = markdown.slice(start);
  const nextHeader = tail.search(/^##\s+/m);
  const section = nextHeader >= 0 ? tail.slice(0, nextHeader) : tail;

  const out: Array<{ role: "user" | "assistant"; content: string }> = [];
  for (const line of section.split("\n")) {
    const row = line.trim();
    if (!row.startsWith("|")) continue;
    const cells = row
      .slice(1, -1)
      .split("|")
      .map((c) => c.trim());
    if (cells.length < 3) continue;
    const role = cells[1].toLowerCase();
    if (role !== "user" && role !== "agent" && role !== "assistant") continue;
    if (!cells[2] || cells[2] === ":---") continue;
    out.push({ role: role === "user" ? "user" : "assistant", content: cells[2] });
  }
  return out;
}

const cleanupPaths: string[] = [];
afterAll(async () => {
  await Promise.all(cleanupPaths.map((p) => fs.rm(p, { recursive: true, force: true })));
});

describe("openclaw case13 probe", () => {
  it("runs case13 queries on the same benchmark", async () => {
    const text = await fs.readFile(BENCHMARK, "utf-8");
    const messages = parseCase13Messages(text);

    const root = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-case13-"));
    cleanupPaths.push(root);
    const workspaceDir = path.join(root, "workspace");
    const memoryDir = path.join(workspaceDir, "memory");
    const stateDir = path.join(root, "state");
    const indexPath = path.join(root, "index.sqlite");
    await fs.mkdir(memoryDir, { recursive: true });
    await fs.mkdir(stateDir, { recursive: true });
    process.env.OPENCLAW_STATE_DIR = stateDir;

    const lines = messages.map((m, i) => `${String(i + 1).padStart(2, "0")} [${m.role}] ${m.content}`);
    await fs.writeFile(path.join(memoryDir, "2026-02-13-case13.md"), lines.join("\n"), "utf-8");

    const cfg: any = {
      agents: {
        defaults: {
          workspace: workspaceDir,
          memorySearch: {
            provider: "openai",
            model: "mock-embed",
            store: { path: indexPath, vector: { enabled: false } },
            chunking: { tokens: 800, overlap: 80 },
            sync: { watch: false, onSessionStart: false, onSearch: false },
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

    const res = await getMemorySearchManager({ cfg, agentId: "main" });
    expect(res.manager).not.toBeNull();
    if (!res.manager) throw new Error(res.error || "manager is null");
    await res.manager.sync?.({ reason: "case13", force: true });

    console.log("=== OPENCLAW CASE13 INPUT ===");
    console.log(JSON.stringify({ benchmark: BENCHMARK, messageCount: messages.length }, null, 2));
    console.log("=== OPENCLAW STATUS ===");
    console.log(JSON.stringify(res.manager.status(), null, 2));

    for (let i = 0; i < QUERIES.length; i++) {
      const q = QUERIES[i];
      const out = await res.manager.search(q, { maxResults: 8, minScore: 0 });
      console.log(`=== OPENCLAW QUERY ${i + 1} ===`);
      console.log(JSON.stringify({ query: q, result: out }, null, 2));
    }
    console.log(`=== OPENCLAW EMBED BATCH CALLS === ${embedBatchCalls}`);
    await res.manager.close?.();
  });
});
