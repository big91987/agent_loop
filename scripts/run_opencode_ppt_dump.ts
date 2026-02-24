import { writeFileSync, mkdirSync, existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { generateText, stepCountIs, tool } from 'ai';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';
import { z } from 'zod';
import { Instance } from '/tmp/opencode/packages/opencode/src/project/instance';
import { SkillTool } from '/tmp/opencode/packages/opencode/src/tool/skill';

type AnyJson = Record<string, unknown>;

function nowTag() {
  const d = new Date();
  const p = (n: number) => `${n}`.padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function tryParseJson(s: string) {
  try { return JSON.parse(s); } catch { return s; }
}

async function loadOpencodeSkillDescription(): Promise<string> {
  return Instance.provide({
    directory: '/Users/admin/work/agent_loop',
    fn: async () => {
      const t = await SkillTool.init();
      return t.description;
    },
  });
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
  const pptPath = join(outDir, `opencode_us_election_${tag}.pptx`);
  const rawPath = join(logsDir, `opencode_ppt_raw_calls_${tag}.json`);
  const resPath = join(logsDir, `opencode_ppt_result_${tag}.json`);

  const interactions: AnyJson[] = [];
  const origFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = new Request(input, init);
    const url = req.url;
    const shouldCapture = url.startsWith(baseURL.replace(/\/$/, ''));

    let reqBody: unknown = null;
    if (shouldCapture) {
      try { reqBody = tryParseJson(await req.clone().text()); } catch { reqBody = null; }
    }

    const resp = await origFetch(req, init);

    if (shouldCapture) {
      let respBody: unknown = null;
      try { respBody = tryParseJson(await resp.clone().text()); } catch { respBody = null; }
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

  const skillDesc = await loadOpencodeSkillDescription();
  const model = createOpenAICompatible({
    baseURL,
    apiKey,
    name: 'openai-compatible',
  });

  const bashTool = tool({
    description: 'Run shell command in /Users/admin/work/agent_loop',
    inputSchema: z.object({ command: z.string() }),
    execute: async ({ command }) => {
      const p = Bun.spawn(['bash', '-lc', command], {
        cwd: workdir,
        stdout: 'pipe',
        stderr: 'pipe',
      });
      const [out, err] = await Promise.all([
        new Response(p.stdout).text(),
        new Response(p.stderr).text(),
      ]);
      const code = await p.exited;
      return `exit=${code}\nSTDOUT:\n${out}\nSTDERR:\n${err}`;
    },
  });

  const skillTool = tool({
    description: skillDesc,
    inputSchema: z.object({ name: z.string() }),
    execute: async ({ name }) => {
      const t = await SkillTool.init();
      const r = await t.execute(
        { name },
        {
          sessionID: 'capture',
          messageID: 'm1',
          callID: 'c1',
          agent: 'build',
          abort: AbortSignal.any([]),
          messages: [],
          metadata: () => {},
          ask: async () => {},
        } as any,
      );
      return r.output;
    },
  });

  const prompt = [
    '请帮我做一个 2 页的美国大选中文 PPT。',
    `请在 ${workdir} 完成，生成可打开的 .pptx 文件。`,
    `输出文件固定为: ${pptPath}`,
    '生成后请自己检查文件是否存在。',
    '最后仅回复绝对路径。',
  ].join('\n');

  let resultText = '';
  let error: string | null = null;
  try {
    const r = await generateText({
      model: model(modelName),
      messages: [{ role: 'user', content: prompt }],
      tools: { skill: skillTool, bash: bashTool },
      stopWhen: stepCountIs(30),
      temperature: 0.1,
    });
    resultText = r.text;
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
    result_text: resultText,
    error,
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
