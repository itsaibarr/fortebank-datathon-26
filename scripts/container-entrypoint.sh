#!/usr/bin/env bash
set -euo pipefail
: "${FORTE_MODEL_PATH:?Mount the explicitly selected pinned model snapshot}"
: "${FORTE_API_KEY_FILE:?Mount a separate private service API key}"
: "${FORTE_PRIVATE_ROOT:?Mount a private job directory}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1 VLLM_NO_USAGE_STATS=1 VLLM_ENABLE_CUDA_COMPATIBILITY=1
mkdir -p "$FORTE_PRIVATE_ROOT"
chmod 700 "$FORTE_PRIVATE_ROOT"
profile="${FORTE_MODEL_PROFILE:-baseline8b}"
forte model-check --root "$FORTE_MODEL_PATH" --profile "$profile" \
  > "$FORTE_PRIVATE_ROOT/model-runtime.json"
export FORTE_MODEL_REVISION
FORTE_MODEL_REVISION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' \
  "$FORTE_PRIVATE_ROOT/model-runtime.json")
sequences=2
pixels=393216
memory=0.85
context=8192
if [[ "$profile" == "frozen27b" ]]; then
  : "${FORTE_REASONING_CONFIG:?Mount the explicit frozen inference configuration}"
  sequences=1
  pixels=196608
  memory=0.9
  context=16384
fi
export FORTE_MAX_CONTEXT_TOKENS="$context"
vllm serve "$FORTE_MODEL_PATH" --served-model-name "${FORTE_MODEL_NAME:-forte-vlm}" \
  --host 127.0.0.1 --port 8001 \
  --dtype bfloat16 --max-model-len "$context" --max-num-seqs "$sequences" \
  --gpu-memory-utilization "$memory" \
  --enforce-eager --limit-mm-per-prompt '{"image":16}' \
  --mm-processor-kwargs "{\"max_pixels\":$pixels}" > "$FORTE_PRIVATE_ROOT/model.log" 2>&1 &
model_pid=$!
api_pid=""
cleanup() {
  if [[ -n "$api_pid" ]]; then kill "$api_pid" 2>/dev/null || true; fi
  kill "$model_pid" 2>/dev/null || true
  if [[ -n "$api_pid" ]]; then wait "$api_pid" 2>/dev/null || true; fi
  wait "$model_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
python3 /app/check_frozen_visual.py --revision "$FORTE_MODEL_REVISION" --wait-seconds 240 \
  --model-name "${FORTE_MODEL_NAME:-forte-vlm}" --max-context-tokens "$context" \
  --output "$FORTE_PRIVATE_ROOT/visual-warmup.json" \
  > "$FORTE_PRIVATE_ROOT/visual-warmup.log" 2>&1
forte serve --host 0.0.0.0 --port 8000 &
api_pid=$!
wait -n "$model_pid" "$api_pid"
