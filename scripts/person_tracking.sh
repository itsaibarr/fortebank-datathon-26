#!/usr/bin/env bash
# Public setup is separate from private inference. Never run inference unsandboxed.
set -euo pipefail
umask 077
if [[ $# -lt 2 ]]; then
  echo 'Usage: scripts/person_tracking.sh setup PRIVATE_ROOT | propose PRIVATE_ROOT OUTPUT [flags]'
  exit 2
fi
tracking_action=$1
tracking_private_root=$2
shift 2
tracking_runtime="$tracking_private_root/person-tracking-v1/_runtime"
tracking_repo="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$tracking_repo"
if [[ "$tracking_action" == setup ]]; then
  mkdir -p "$tracking_runtime/public"
  UV_PROJECT_ENVIRONMENT="$tracking_runtime/.venv" uv sync --frozen --extra inference-tracking
  "$tracking_runtime/.venv/bin/python" - "$tracking_runtime/public" <<'PY'
import hashlib,json,sys,urllib.request
from pathlib import Path
public=Path(sys.argv[1]);config=json.loads(Path('configs/person-tracking.json').read_text())
weight=public/'yolox_s.onnx'
if not weight.exists():
    with urllib.request.urlopen(config['weights_url'],timeout=60) as response:
        with (public/'yolox_s.onnx.partial').open('wb') as target:
            import shutil
            shutil.copyfileobj(response,target)
    (public/'yolox_s.onnx.partial').rename(weight)
if hashlib.sha256(weight.read_bytes()).hexdigest()!=config['weights_sha256']:
    raise ValueError('Weight checksum mismatch; preserve artifact and investigate')
for repo,revision,name in [
    ('Megvii-BaseDetection/YOLOX',config['code_revision'],'YOLOX-LICENSE'),
    ('roboflow/trackers',config['tracker_revision'],'trackers-LICENSE')]:
    with urllib.request.urlopen(f'https://raw.githubusercontent.com/{repo}/{revision}/LICENSE',timeout=30) as r:
        (public/name).write_bytes(r.read())
print(json.dumps({'public_runtime_ready':True,'weights_sha256':config['weights_sha256']}))
PY
elif [[ "$tracking_action" == propose ]]; then
  if [[ $# -lt 1 ]]; then echo 'OUTPUT is required'; exit 2; fi
  tracking_output=$1
  shift
  if [[ "$(uname -s)" != Darwin ]] || ! command -v sandbox-exec >/dev/null; then
    echo 'This wrapper requires macOS sandbox-exec; use a network-disabled container on Linux.' >&2
    exit 1
  fi
  # OS enforcement covers Python, the detector and all child processes. Dependencies
  # and weights must already exist. No remote inference, identity or role service.
  exec env FORTE_TRACKING_NETWORK_ISOLATION=macos-sandbox-exec \
    MPLCONFIGDIR="$tracking_runtime/mpl" \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$tracking_runtime/.venv/bin/forte" tracks-prepare \
    --private-root "$tracking_private_root" --output "$tracking_output" \
    --weights "$tracking_runtime/public/yolox_s.onnx" \
    --config "$tracking_repo/configs/person-tracking.json" "$@"
else
  echo 'Unknown action' >&2
  exit 2
fi
