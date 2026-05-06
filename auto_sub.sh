#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: ./auto_sub.sh <Bilibili_URL> [--summarize] [extra args]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python was not found in PATH."
  exit 1
fi

URL="$1"
shift

PYTHON_ARGS=("$SCRIPT_DIR/bili_groq.py" "$URL" "--pdf")
if [[ $# -gt 0 ]]; then
  PYTHON_ARGS+=("$@")
fi

"$PYTHON_BIN" "${PYTHON_ARGS[@]}"
