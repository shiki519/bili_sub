#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: ./run_bili_sub.sh <Bilibili_URL> [extra args]"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

URL="$(printf '%s' "$1" | tr -d '\r\n' | xargs)"
shift
EXTRA_ARGS=("$@")

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/run_${RUN_ID}.log"

log() {
  echo "$*" | tee -a "$LOG_FILE"
}

fail_stage() {
  local stage="$1"
  echo "[wrapper] failed at stage: ${stage}"
  echo "[wrapper] log: ${LOG_FILE}"
  exit 1
}

if [[ "${BILI_SUB_GIT_PULL:-0}" == "1" ]]; then
  log "[wrapper] running git pull --ff-only"
  if ! git pull --ff-only >>"$LOG_FILE" 2>&1; then
    fail_stage "git-pull"
  fi
fi

if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
  log "[wrapper] activated virtualenv: $ROOT_DIR/.venv"
else
  log "[wrapper] .venv not found, using system Python"
fi

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "[wrapper] Python was not found in PATH."
  echo "[wrapper] log: ${LOG_FILE}"
  exit 1
fi

check_proxy_health() {
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl --user is-active --quiet mihomo.service; then
      log "[wrapper] mihomo.service: active"
    else
      log "[wrapper] mihomo.service: inactive"
      if [[ "${BILI_SUB_RESTART_MIHOMO:-0}" == "1" ]]; then
        log "[wrapper] restarting mihomo.service via systemctl --user"
        if systemctl --user restart mihomo.service >>"$LOG_FILE" 2>&1; then
          if systemctl --user is-active --quiet mihomo.service; then
            log "[wrapper] mihomo.service: active after restart"
          else
            log "[wrapper] mihomo.service: still inactive after restart"
          fi
        else
          log "[wrapper] mihomo.service restart failed"
        fi
      fi
    fi
  else
    log "[wrapper] systemctl not found, skip mihomo.service check"
  fi

  if command -v ss >/dev/null 2>&1; then
    if ss -ltn | grep -q ':7890 '; then
      log "[wrapper] 127.0.0.1:7890: listening"
    else
      log "[wrapper] 127.0.0.1:7890: not listening"
    fi
    return
  fi

  if command -v netstat >/dev/null 2>&1; then
    if netstat -ltn 2>/dev/null | grep -q ':7890 '; then
      log "[wrapper] 127.0.0.1:7890: listening"
    else
      log "[wrapper] 127.0.0.1:7890: not listening"
    fi
    return
  fi

  if command -v nc >/dev/null 2>&1; then
    if nc -z 127.0.0.1 7890 >/dev/null 2>&1; then
      log "[wrapper] 127.0.0.1:7890: listening"
    else
      log "[wrapper] 127.0.0.1:7890: not listening"
    fi
    return
  fi

  log "[wrapper] no port check tool found, skip 127.0.0.1:7890 probe"
}

cleanup_retry_state() {
  local stage="$1"
  case "$stage" in
    download)
      rm -f "$ROOT_DIR/temp_download.m4a" "$ROOT_DIR/temp_download.m4a.part"
      ;;
    transcribe)
      rm -rf "$ROOT_DIR/temp_chunks"
      ;;
    summary)
      ;;
  esac
}

STAGE_OUTPUT=""

run_and_capture() {
  local stage_file=""
  local status=0
  stage_file="$(mktemp "${TMPDIR:-/tmp}/bili_sub_stage.XXXXXX")"

  set +e
  "$@" 2>&1 | tee -a "$LOG_FILE" | tee "$stage_file"
  status=${PIPESTATUS[0]}
  set -e

  STAGE_OUTPUT="$(cat "$stage_file")"
  rm -f "$stage_file"
  return "$status"
}

run_stage() {
  local stage="$1"
  local max_attempts="$2"
  shift 2

  local attempt=1
  local sleep_seconds=0

  while (( attempt <= max_attempts )); do
    log "[wrapper] stage=${stage} attempt ${attempt}/${max_attempts}"
    if run_and_capture "$@"; then
      return 0
    fi

    log "[wrapper] stage=${stage} attempt ${attempt} failed"
    if (( attempt < max_attempts )); then
      cleanup_retry_state "$stage"
      sleep_seconds=$((5 * (2 ** (attempt - 1))))
      if (( sleep_seconds > 30 )); then
        sleep_seconds=30
      fi
      log "[wrapper] retrying ${stage} in ${sleep_seconds}s"
      sleep "$sleep_seconds"
    fi
    attempt=$((attempt + 1))
  done

  return 1
}

extract_result() {
  local key="$1"
  printf '%s\n' "$STAGE_OUTPUT" | sed -n "s/^${key}=//p" | tail -n 1
}

check_proxy_health

DOWNLOAD_CMD=("$PYTHON_BIN" "$ROOT_DIR/bili_groq.py" "$URL" "--download-only" "--pdf")
if (( ${#EXTRA_ARGS[@]} > 0 )); then
  DOWNLOAD_CMD+=("${EXTRA_ARGS[@]}")
fi

if ! run_stage "download" 3 "${DOWNLOAD_CMD[@]}"; then
  fail_stage "download"
fi

TXT_PATH="$(extract_result "RESULT_TXT")"
PDF_PATH="$(extract_result "RESULT_PDF")"
SRT_PATH="$(extract_result "RESULT_SRT")"
AUDIO_PATH="$(extract_result "RESULT_AUDIO")"
TITLE="$(extract_result "RESULT_TITLE")"

if [[ -z "$TXT_PATH" ]]; then
  if [[ -z "$AUDIO_PATH" ]]; then
    log "[wrapper] download stage returned neither RESULT_TXT nor RESULT_AUDIO"
    fail_stage "download"
  fi

  TRANSCRIBE_CMD=("$PYTHON_BIN" "$ROOT_DIR/bili_groq.py" "--transcribe-file" "$AUDIO_PATH" "--pdf")
  if [[ -n "$TITLE" ]]; then
    TRANSCRIBE_CMD+=("--title" "$TITLE")
  fi
  if (( ${#EXTRA_ARGS[@]} > 0 )); then
    TRANSCRIBE_CMD+=("${EXTRA_ARGS[@]}")
  fi

  if ! run_stage "transcribe" 3 "${TRANSCRIBE_CMD[@]}"; then
    fail_stage "transcribe"
  fi

  TXT_PATH="$(extract_result "RESULT_TXT")"
  PDF_PATH="$(extract_result "RESULT_PDF")"
fi

if [[ -z "$TXT_PATH" ]]; then
  log "[wrapper] transcribe stage did not produce RESULT_TXT"
  fail_stage "transcribe"
fi

SUMMARY_CMD=("$PYTHON_BIN" "$ROOT_DIR/bili_groq.py" "--summarize-file" "$TXT_PATH")
if (( ${#EXTRA_ARGS[@]} > 0 )); then
  SUMMARY_CMD+=("${EXTRA_ARGS[@]}")
fi

if ! run_stage "summary" 3 "${SUMMARY_CMD[@]}"; then
  fail_stage "summary"
fi

SUMMARY_PATH="$(extract_result "RESULT_SUMMARY")"
if [[ -z "$SUMMARY_PATH" ]]; then
  log "[wrapper] summary stage did not produce RESULT_SUMMARY"
  fail_stage "summary"
fi

echo "RESULT_TXT=${TXT_PATH}"
if [[ -n "$SRT_PATH" ]]; then
  echo "RESULT_SRT=${SRT_PATH}"
fi
if [[ -n "$PDF_PATH" ]]; then
  echo "RESULT_PDF=${PDF_PATH}"
fi
echo "RESULT_SUMMARY=${SUMMARY_PATH}"
