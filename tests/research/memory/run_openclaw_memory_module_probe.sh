#!/usr/bin/env bash
set -euo pipefail

# Module-level probe for OpenClaw memory subsystem.
# Usage:
#   bash tests/research/memory/run_openclaw_memory_module_probe.sh /Users/admin/work/openclaw

OPENCLAW_DIR="${1:-/Users/admin/work/openclaw}"

if [[ ! -d "${OPENCLAW_DIR}" ]]; then
  echo "[ERROR] openclaw dir not found: ${OPENCLAW_DIR}" >&2
  exit 1
fi

echo "[INFO] openclaw_dir=${OPENCLAW_DIR}"
cd "${OPENCLAW_DIR}"

if [[ ! -d node_modules ]]; then
  echo "[STEP] bun install"
  bun install
fi

echo "[STEP] run memory core tests"
bun x vitest run \
  src/memory/backend-config.test.ts \
  src/memory/index.test.ts \
  src/auto-reply/reply/memory-flush.test.ts \
  src/memory/hybrid.test.ts \
  src/memory/temporal-decay.test.ts \
  src/memory/manager.read-file.test.ts \
  src/memory/qmd-scope.test.ts

echo "[DONE] openclaw memory module probe passed"
