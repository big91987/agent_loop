#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

JSON_PREFIX = "__JSON__"
STATE: dict[str, Any] = {}


def _emit(payload: dict[str, Any]) -> None:
    print(JSON_PREFIX + json.dumps(payload, ensure_ascii=False), flush=True)


def _startup(payload: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(str(payload["workspace"])).expanduser().resolve()
    artifact_dir = Path(str(payload["artifact_dir"])).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "storage": {"workspace": str(workspace)},
        "embedding": {
            "dense": {
                "provider": "openai",
                "model": str(payload["embed_model"]),
                "api_key": str(payload["embed_api_key"]),
                "api_base": str(payload["embed_base_url"]),
                "dimension": int(payload.get("embed_dim", 1024)),
            }
        },
        "vlm": {
            "provider": "openai",
            "model": str(payload["llm_model"]),
            "api_key": str(payload["llm_api_key"]),
            "api_base": str(payload["llm_base_url"]),
        },
        "default_search_mode": str(payload.get("default_search_mode", "quick") or "quick"),
        "log": {"level": "INFO", "output": "stdout"},
    }
    config_file = artifact_dir / "openviking.conf"
    config_file.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.environ["OPENVIKING_CONFIG_FILE"] = str(config_file)

    import openviking as ov

    client = ov.OpenViking(path=str(workspace))
    client.initialize()
    STATE.update(
        client=client,
        workspace=str(workspace),
        config_file=str(config_file),
    )
    return {"ok": True, "workspace": str(workspace), "config_file": str(config_file)}


def _ensure_session(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload["session_id"]).strip()
    session = STATE["client"].session(session_id=session_id, must_exist=False)
    return {"ok": True, "session_id": getattr(session, "session_id", session_id)}


def _glob_memory_files(target_uri: str) -> list[str]:
    matches = STATE["client"].glob(pattern="**/*.md", uri=target_uri)
    rows = matches.get("matches", []) if isinstance(matches, dict) else []
    return sorted(set([str(item) for item in rows if isinstance(item, str)]))


def _append_and_commit(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload["session_id"]).strip()
    messages = payload.get("messages", [])
    timeout = float(payload.get("timeout", 180.0) or 180.0)
    target_uri = str(payload.get("target_uri", "viking://user/default/memories"))
    STATE["client"].session(session_id=session_id, must_exist=False)
    for msg in messages if isinstance(messages, list) else []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "user")).strip() or "user"
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        STATE["client"].add_message(session_id=session_id, role=role, content=content)
    commit = STATE["client"].commit_session(session_id)
    wait_result = STATE["client"].wait_processed(timeout=timeout)
    memory_files = _glob_memory_files(target_uri)
    return {
        "ok": True,
        "session_id": session_id,
        "commit": commit,
        "wait_processed": wait_result,
        "memory_files": memory_files,
        "memory_file_count": len(memory_files),
    }


def _search(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload["session_id"]).strip()
    query = str(payload["query"]).strip()
    target_uri = str(payload.get("target_uri", "viking://user/default/memories"))
    limit = int(payload.get("limit", 8) or 8)
    score_threshold = payload.get("score_threshold")
    find_fallback = bool(payload.get("find_fallback", True))
    search_result = STATE["client"].search(
        query=query,
        target_uri=target_uri,
        session_id=session_id,
        limit=limit,
        score_threshold=score_threshold,
    )
    items: list[dict[str, Any]] = []

    def add_from_result(result: Any) -> None:
        memories = result.get("memories", []) if isinstance(result, dict) else []
        for row in memories if isinstance(memories, list) else []:
            if not isinstance(row, dict):
                continue
            uri = str(row.get("uri", ""))
            if not uri.endswith(".md"):
                continue
            try:
                content = STATE["client"].read(uri)
            except Exception:
                content = ""
            items.append(
                {
                    "uri": uri,
                    "abstract": str(row.get("abstract", "")),
                    "score": row.get("score", 0.0),
                    "level": row.get("level", ""),
                    "category": str(row.get("category", "")),
                    "content": str(content).strip(),
                }
            )

    add_from_result(search_result)
    if find_fallback and not items:
        find_result = STATE["client"].find(
            query=query,
            target_uri=target_uri,
            limit=limit,
            score_threshold=score_threshold,
        )
        add_from_result(find_result)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        uri = item.get("uri", "")
        if uri in seen:
            continue
        seen.add(uri)
        deduped.append(item)
    return {
        "ok": True,
        "query": query,
        "target_uri": target_uri,
        "items": deduped[:limit],
        "raw_hit_count": len(items),
    }


def _stats(payload: dict[str, Any]) -> dict[str, Any]:
    target_uri = str(payload.get("target_uri", "viking://user/default/memories"))
    memory_files = _glob_memory_files(target_uri)
    return {
        "target_uri": target_uri,
        "memory_files": memory_files,
        "memory_file_count": len(memory_files),
        "workspace": STATE.get("workspace", ""),
        "config_file": STATE.get("config_file", ""),
    }


def _close() -> dict[str, Any]:
    client = STATE.get("client")
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
    return {"ok": True}


def main() -> int:
    handlers = {
        "startup": _startup,
        "ensure_session": _ensure_session,
        "append_and_commit": _append_and_commit,
        "search": _search,
        "stats": _stats,
        "close": lambda payload: _close(),
    }
    for line in sys.stdin:
        row = line.strip()
        if not row:
            continue
        try:
            payload = json.loads(row)
            cmd = str(payload.get("cmd", ""))
            handler = handlers.get(cmd)
            if handler is None:
                _emit({"ok": False, "error": f"unknown cmd: {cmd}"})
                continue
            result = handler(payload)
            _emit(result)
            if cmd == "close":
                break
        except Exception as err:
            _emit({"ok": False, "error": repr(err)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
