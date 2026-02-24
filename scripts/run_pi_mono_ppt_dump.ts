import { writeFileSync, mkdirSync, existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import {
  createAgentSession,
  createCodingTools,
  DefaultResourceLoader,
  SessionManager,
  type Skill,
} from '/Users/admin/work/pi-mono/packages/coding-agent/src/index.ts';
import { loadSkillsFromDir } from '/Users/admin/work/pi-mono/packages/coding-agent/src/core/skills.ts';

type AnyJson = Record<string, unknown>;

function nowTag() {
  const d = new Date();
  const p = (n: number) => `${n}`.padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function buildModel(baseUrl: string, modelName: string) {
  return {
    id: modelName,
    name: modelName,
    api: 'openai-completions' as const,
    provider: 'openai',
    baseUrl,
    headers: {},
    input: ['text', 'image'] as const,
    contextWindow: 128000,
    maxTokens: 8192,
    reasoning: false,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  };
}

function tryParseJson(s: string) {
  try { return JSON.parse(s); } catch { return s; }
}

async function main() {
  const apiKey = process.env.MINIMAX_API_KEY;
  if (!apiKey) throw new Error('MINIMAX_API_KEY is required');

  const baseURL = process.env.MINIMAX_BASE_URL || 'https://api.minimaxi.com/v1';
  const modelName = process.env.MINIMAX_MODEL || 'MiniMax-M2.1';
  const workdir = '/Users/admin/work/agent_loop';
  const logsDir = join(workdir, 'logs');
  const outDir = join(workdir, 'outputs');
  mkdirSync(logsDir, { recursive: true });
  mkdirSync(outDir, { recursive: true });

  const tag = nowTag();
  const pptPath = join(outDir, `pi_mono_us_election_${tag}.pptx`);
  const rawPath = join(logsDir, `pi_mono_ppt_raw_calls_${tag}.json`);
  const resPath = join(logsDir, `pi_mono_ppt_result_${tag}.json`);

  const interactions: AnyJson[] = [];
  const events: AnyJson[] = [];
  writeFileSync(rawPath, JSON.stringify(interactions, null, 2));
  const eventPath = rawPath.replace('_raw_calls_', '_events_');
  writeFileSync(eventPath, JSON.stringify(events, null, 2));

  const origFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = new Request(input, init);
    const url = req.url;
    const shouldCapture = url.startsWith(baseURL.replace(/\/$/, ''));

    let reqBody: unknown = null;
    if (shouldCapture) {
      try {
        reqBody = tryParseJson(await req.clone().text());
      } catch {
        reqBody = null;
      }
    }

    const resp = await origFetch(req, init);

    if (shouldCapture) {
      let respBody: unknown = null;
      try {
        respBody = tryParseJson(await resp.clone().text());
      } catch {
        respBody = null;
      }
      interactions.push({
        request: {
          ts: new Date().toISOString(),
          method: req.method,
          url,
          headers: Object.fromEntries(req.headers.entries()),
          body: reqBody,
        },
        response: {
          status: resp.status,
          headers: Object.fromEntries(resp.headers.entries()),
          body: respBody,
        },
      });
      writeFileSync(rawPath, JSON.stringify(interactions, null, 2));
    }

    return resp;
  }) as typeof fetch;

  process.env.OPENAI_API_KEY = apiKey;

  const all = loadSkillsFromDir({ dir: '/Users/admin/.claude/skills', source: 'claude' }).skills;
  const picked = all.filter((s) => s.name === 'pptx' || s.name === 'skill-lookup');

  const loader = new DefaultResourceLoader({
    cwd: workdir,
    agentDir: '/Users/admin/.pi/agent',
    skillsOverride: () => ({ skills: picked as Skill[], diagnostics: [] }),
  });
  await loader.reload();

  const { session } = await createAgentSession({
    cwd: workdir,
    model: buildModel(baseURL, modelName) as any,
    tools: createCodingTools(workdir),
    resourceLoader: loader,
    sessionManager: SessionManager.inMemory(),
  });

  let finalText = '';
  session.subscribe((event) => {
    events.push(event as unknown as AnyJson);
    writeFileSync(eventPath, JSON.stringify(events, null, 2));
    if (event.type === 'message_update' && event.assistantMessageEvent.type === 'text_delta') {
      finalText += event.assistantMessageEvent.delta;
    }
  });

  let error: string | null = null;
  try {
    await session.prompt(
      [
        '请使用 skills 中的 pptx 指令来完成任务。',
        `在 ${workdir} 用 bash 生成并执行 node + pptxgenjs 脚本，创建 2 页美国大选中文 PPT。`,
        `输出文件固定为: ${pptPath}`,
        '生成后用 ls -lh 校验文件存在。',
        '最后仅回复绝对路径。',
      ].join('\n'),
    );
    await session.agent.waitForIdle();
  } catch (e) {
    error = String(e);
  } finally {
    globalThis.fetch = origFetch;
  }

  const exists = existsSync(pptPath);
  const size = exists ? statSync(pptPath).size : 0;
  const summary = {
    model: modelName,
    expected_ppt: pptPath,
    ppt_exists: exists,
    ppt_size: size,
    raw_calls_file: rawPath,
    events_file: eventPath,
    final_text: finalText,
    error,
    message_count: session.state.messages.length,
    last_message: session.state.messages[session.state.messages.length - 1] || null,
  };
  writeFileSync(resPath, JSON.stringify(summary, null, 2));

  console.log(rawPath);
  console.log(resPath);
  console.log(pptPath);
  console.log('ppt_exists:', exists);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
