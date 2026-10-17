#!/usr/bin/env bash
# Run on an already-authorized Linux GPU host. This script does not rent a VM.
set -euo pipefail

FORTE_GPU_ROOT="${FORTE_GPU_ROOT:-/ephemeral/forte26}"
FORTE_RUN_DIR="${FORTE_RUN_DIR:-/opt/forte26}"
FORTE_IMAGE='vllm/vllm-openai@sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b'
FORTE_REVISION='0c351dd01ed87e9c1b53cbc748cba10e6187ff3b'
FORTE_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if docker container inspect forte26-smoke >/dev/null 2>&1; then
  printf '%s\n' 'Container forte26-smoke already exists; inspect it before a new run.' >&2
  exit 1
fi

mkdir -p "$FORTE_GPU_ROOT/hf-cache" "$FORTE_RUN_DIR"
cp "$FORTE_SCRIPT_DIR/gpu_smoke.py" "$FORTE_RUN_DIR/gpu_smoke.py"
docker pull "$FORTE_IMAGE"
docker run --rm \
  -v "$FORTE_GPU_ROOT/hf-cache:/root/.cache/huggingface" \
  -e HF_HUB_DISABLE_TELEMETRY=1 -e DO_NOT_TRACK=1 \
  --entrypoint python3 "$FORTE_IMAGE" -c \
  "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Qwen/Qwen3-VL-8B-Instruct', revision='$FORTE_REVISION')"

docker run --name forte26-smoke --gpus all --network none --ipc=host \
  -v "$FORTE_GPU_ROOT/hf-cache:/root/.cache/huggingface:ro" \
  -v "$FORTE_RUN_DIR:/work" \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  -e HF_HUB_DISABLE_TELEMETRY=1 -e DO_NOT_TRACK=1 -e VLLM_NO_USAGE_STATS=1 \
  -e VLLM_ENABLE_CUDA_COMPATIBILITY=1 \
  -e "FORTE_MODEL_PATH=/root/.cache/huggingface/hub/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/$FORTE_REVISION" \
  --entrypoint python3 "$FORTE_IMAGE" /work/gpu_smoke.py
