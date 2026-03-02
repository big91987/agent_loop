#!/usr/bin/env bash
set -euo pipefail

# Module-level probe for claude-mem memory subsystem.
# Usage:
#   bash tests/research/memory/run_claude_mem_module_probe.sh /tmp/memory_scan_round2/claude-mem

CLAUDE_MEM_DIR="${1:-/tmp/memory_scan_round2/claude-mem}"

if [[ ! -d "${CLAUDE_MEM_DIR}" ]]; then
  echo "[ERROR] claude-mem dir not found: ${CLAUDE_MEM_DIR}" >&2
  exit 1
fi

echo "[INFO] claude_mem_dir=${CLAUDE_MEM_DIR}"
cd "${CLAUDE_MEM_DIR}"

if [[ ! -d node_modules ]]; then
  echo "[STEP] bun install"
  bun install
fi

echo "[STEP] run sqlite + search module tests"
bun test \
  tests/sqlite/observations.test.ts \
  tests/sqlite/summaries.test.ts \
  tests/worker/search/search-orchestrator.test.ts \
  tests/worker/search/result-formatter.test.ts

echo "[DONE] claude-mem memory module probe passed"
