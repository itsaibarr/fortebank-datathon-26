#!/usr/bin/env bash
set -euo pipefail
: "${FORTE_MODEL_PATH:?Mount the pinned Qwen3-VL-8B-Instruct snapshot}"
: "${FORTE_API_KEY_FILE:?Mount a separate private service API key}"
: "${FORTE_PRIVATE_ROOT:?Mount a private job directory}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1 VLLM_NO_USAGE_STATS=1 VLLM_ENABLE_CUDA_COMPATIBILITY=1
mkdir -p "$FORTE_PRIVATE_ROOT"
chmod 700 "$FORTE_PRIVATE_ROOT"
vllm serve "$FORTE_MODEL_PATH" --served-model-name forte-vlm --host 127.0.0.1 --port 8001 \
  --dtype bfloat16 --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization 0.85 \
  --enforce-eager --limit-mm-per-prompt '{"image":16}' \
  --mm-processor-kwargs '{"max_pixels":393216}' > "$FORTE_PRIVATE_ROOT/model.log" 2>&1 &
model_pid=$!
forte serve --host 0.0.0.0 --port 8000 &
api_pid=$!
cleanup() {
  kill "$api_pid" "$model_pid" 2>/dev/null || true
  wait "$api_pid" "$model_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
wait -n "$model_pid" "$api_pid"
