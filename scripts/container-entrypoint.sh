#!/usr/bin/env bash
set -euo pipefail
: "${FORTE_VISUAL_CONFIG:?Mount explicit tuned or base_control visual configuration}"
: "${FORTE_API_KEY_FILE:?Mount a separate private service API key}"
: "${FORTE_PRIVATE_ROOT:?Mount a private job directory}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1 VLLM_NO_USAGE_STATS=1 VLLM_ENABLE_CUDA_COMPATIBILITY=1
export WANDB_DISABLED=true TOKENIZERS_PARALLELISM=false
umask 077
mkdir -p "$FORTE_PRIVATE_ROOT"
chmod 700 "$FORTE_PRIVATE_ROOT"
python3 -m forte.visual_runtime serve-model --config "$FORTE_VISUAL_CONFIG" \
  > "$FORTE_PRIVATE_ROOT/model.log" 2>&1 &
model_pid=$!
forte serve --host 0.0.0.0 --port 8000 &
api_pid=$!
cleanup() {
  kill "$api_pid" "$model_pid" 2>/dev/null || true
  wait "$api_pid" "$model_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
wait -n "$model_pid" "$api_pid"
