#!/usr/bin/env bash
set -euo pipefail
: "${FORTE_MODEL_PATH:?Mount the pinned 8B snapshot}"
: "${FORTE_LAYA_PATH:?Mount the pinned multilingual Laya snapshot}"
: "${FORTE_REASONING_CONFIG:?Mount the selected inference configuration}"
: "${FORTE_API_KEY_FILE:?Mount a private service key}"
: "${FORTE_PRIVATE_ROOT:?Mount private jobs outside the source tree}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1 VLLM_NO_USAGE_STATS=1 VLLM_ENABLE_CUDA_COMPATIBILITY=1
mkdir -p "$FORTE_PRIVATE_ROOT"
chmod 700 "$FORTE_PRIVATE_ROOT"
forte model-check --root "$FORTE_MODEL_PATH" > "$FORTE_PRIVATE_ROOT/model-runtime.json"
export FORTE_MODEL_REVISION=0c351dd01ed87e9c1b53cbc748cba10e6187ff3b
export FORTE_MAX_CONTEXT_TOKENS=8192
vllm serve "$FORTE_MODEL_PATH" --served-model-name "${FORTE_MODEL_NAME:-forte-vlm}" \
  --host 127.0.0.1 --port 8001 --dtype bfloat16 --max-model-len 8192 --max-num-seqs 1 \
  --gpu-memory-utilization 0.85 --enforce-eager --limit-mm-per-prompt '{"image":16}' \
  --mm-processor-kwargs '{"max_pixels":393216}' > "$FORTE_PRIVATE_ROOT/model.log" 2>&1 &
model_pid=$!
laya_pid=""
api_pid=""
cleanup() {
  for pid in "$api_pid" "$laya_pid" "$model_pid"; do
    if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT INT TERM
python -m forte.laya_service --root "$FORTE_LAYA_PATH" > "$FORTE_PRIVATE_ROOT/laya.log" 2>&1 &
laya_pid=$!
python /app/check_frozen_visual.py --revision "$FORTE_MODEL_REVISION" --wait-seconds 240 \
  --model-name "${FORTE_MODEL_NAME:-forte-vlm}" --max-context-tokens 8192 \
  --output "$FORTE_PRIVATE_ROOT/visual-warmup.json" > "$FORTE_PRIVATE_ROOT/visual-warmup.log" 2>&1
forte serve --host 0.0.0.0 --port 8000 &
api_pid=$!
wait -n "$model_pid" "$laya_pid" "$api_pid"
