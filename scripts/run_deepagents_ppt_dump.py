#!/usr/bin/env python3
import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends.local_shell import LocalShellBackend
from langchain_openai import ChatOpenAI

MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2.1")
BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
API_KEY = os.getenv("MINIMAX_API_KEY")
SKILLS_SOURCE = os.getenv("SKILLS_SOURCE", "/Users/admin/.claude/skills")
WORKDIR = Path(os.getenv("WORKDIR", "/Users/admin/work/agent_loop"))
LOG_DIR = WORKDIR / "logs"
OUT_DIR = WORKDIR / "outputs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

if not API_KEY:
    raise SystemExit("MINIMAX_API_KEY is required")

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
ppt_path = OUT_DIR / f"deepagents_us_election_{ts}.pptx"
raw_path = LOG_DIR / f"deepagents_ppt_raw_calls_{ts}.json"
res_path = LOG_DIR / f"deepagents_ppt_result_{ts}.json"

calls: list[dict[str, Any]] = []


def to_jsonable(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, list):
        return [to_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): to_jsonable(val) for k, val in v.items()}
    if hasattr(v, "model_dump"):
        try:
            return to_jsonable(v.model_dump())
        except Exception:
            pass
    if hasattr(v, "dict"):
        try:
            return to_jsonable(v.dict())
        except Exception:
            pass
    return repr(v)


model = ChatOpenAI(model=MODEL, base_url=BASE_URL, api_key=API_KEY, timeout=240)
orig_create = model.client.create


def logged_create(*args: Any, **kwargs: Any):
    req = to_jsonable(kwargs)
    rec: dict[str, Any] = {"request": req}
    calls.append(rec)
    try:
        resp = orig_create(*args, **kwargs)
        parsed_obj = None
        if hasattr(resp, "parse"):
            try:
                parsed_obj = resp.parse()
            except Exception as e:  # noqa: BLE001
                rec["response_parse_error"] = f"{type(e).__name__}: {e}"
        rec["response"] = to_jsonable(parsed_obj if parsed_obj is not None else resp)
        return resp
    except Exception as err:  # noqa: BLE001
        rec["error"] = f"{type(err).__name__}: {err}"
        raise
    finally:
        raw_path.write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding="utf-8")


model.client.create = logged_create  # type: ignore[method-assign]
# LocalShellBackend enables the `execute` tool for end-to-end command execution.
backend = LocalShellBackend(
    root_dir=str(WORKDIR),
    virtual_mode=False,
    inherit_env=True,
    timeout=300.0,
)
agent = create_deep_agent(model=model, backend=backend, skills=[SKILLS_SOURCE])

prompt = (
    "任务：生成一个2页的美国大选主题PPT。\\n"
    f"输出路径：{ppt_path}"
)

result_payload: dict[str, Any]
try:
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]}, config={"recursion_limit": 80})
    result_payload = to_jsonable(result)
except Exception as err:  # noqa: BLE001
    result_payload = {"error": f"{type(err).__name__}: {err}", "traceback": traceback.format_exc()}

result_payload["expected_ppt"] = str(ppt_path)
result_payload["ppt_exists"] = ppt_path.exists()
result_payload["raw_calls_file"] = str(raw_path)
res_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

print(str(raw_path))
print(str(res_path))
print(str(ppt_path))
print("calls:", len(calls))
print("ppt_exists:", ppt_path.exists())
