#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
python3 -m unittest -v tests/test_v1_v2.py tests/test_v3_tools.py tests/test_v4_1_mcp.py tests/test_logging.py
