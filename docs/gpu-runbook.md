# Verified GPU setup and repeatable model check

On 17 October 2026 the user funded Hyperstack and authorized management within $30. One `n3-A100x1` was created in CANADA-1, checked and deleted after the public/synthetic experiment. No competition recording, annotation, scene description or adapter was transferred. No training ran.

The machine provided one A100 PCIe 80 GB, driver `570.195.03`, 28 vCPUs, 120 GB RAM, a 100 GB root disk and a 750 GB ephemeral disk mounted at `/ephemeral`. Docker was `29.1.3`. The actual model and result receipt is [.context/verify/gpu-setup.json](../.context/verify/gpu-setup.json).

## Use the image that actually fits this GPU

Select **Ubuntu Server 24.04 LTS R570 CUDA 12.8 with Docker**, image ID 517 in CANADA-1. The R595/CUDA13.2 image offered in the same region has a hard B300-only flavor restriction. The earlier preflight checked its presence but missed that restriction; it was caught before paid allocation.

The verified application image is:

```text
vllm/vllm-openai@sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b
```

This x86_64 vLLM 0.31.0 image contains Python 3.12.3, Torch 2.13.0+cu130 and Transformers 5.17.0. On this datacenter GPU and R570 host, `VLLM_ENABLE_CUDA_COMPATIBILITY=1` worked. No driver replacement was needed. See the [vLLM Docker instructions](https://docs.vllm.ai/en/latest/deployment/docker/#running-on-systems-with-older-cuda-drivers) and [versioned compatibility code](https://github.com/vllm-project/vllm/blob/v0.31.0/vllm/env_override.py).

## Repeat the public/synthetic check on an authorized VM

1. Recheck credit, actual rate, stock and image/flavor restrictions. Create exactly one GPU only while there is useful work ready. The checked rate was $1.35/hour compute plus $0.006720430/hour for the public IP.
2. Use this project's dedicated environment and keypair. Private API headers, SSH key, known-host file and provisioning state are under `~/.config/forte26` on the Mac. Never print their contents, copy them into Git or paste them into chat.
3. Arm cleanup before work. The completed session used a Mac guard and a VM-side systemd timer that called DELETE only after matching the recorded VM ID, name and environment. The deadline was two hours after the creation request. The provider header on the VM was root-readable only and was outside all model-container mounts. Deletion destroyed that copy. Do not confuse a stopped VM with a deleted VM.
4. Permit inbound TCP 22 only from the current SSH connection's source `/32`; keep application ports closed. The old connection produced different HTTP-reflection and SSH source IPs. After the modem change they matched. Use the dedicated identity explicitly (`-i` and `IdentitiesOnly=yes`) even with a project control socket, and update the rule when the connection changes. An expired socket without an explicit key caused a confirmed public-key authentication failure during the second session. A temporary key-only bootstrap rule was removed immediately after establishing the restricted connection.
5. Preserve strict host-key checking after the first connection. The console-log API returned request-not-found, so the first connection used trust on first use and pinned the ED25519 key in a dedicated `known_hosts`. Independent console confirmation was unavailable; do not describe this as an independently verified host key.
6. Copy the public checkout to the GPU. From that checkout run `bash scripts/gpu_smoke.sh`. It downloads public weights at the pinned revision, then runs generated shapes in a separate container with `--network none`, offline model flags and telemetry disabled. It does not allocate a VM. It refuses to reuse an existing `forte26-smoke` container. Inspect any old container before deciding to remove it.
7. Inspect the result and container state. Require exit code 0, network mode `none`, both frame-selection checks passing and both prompts fitting 8,192 tokens. Copy and verify the result, logs, container inspection, versions and memory samples on the Mac before deleting the VM.
8. Delete the recorded VM when the useful check finishes. Verify that the VM inventory no longer contains it. Verify resource counts and charges through the provider dashboard. Preserve the dedicated non-billed environment and public keypair for the next session.

For a new rental, archive the completed private session record and create a fresh lifecycle record with a new deadline and guards. Do not treat the old VM ID or its deleted marker as the new session. Confirm the previous local guard has exited before changing its state file.

The Python smoke test and equivalent Docker/download commands ran on the rented GPU. The convenience shell wrapper was added afterward and syntax-checked; its complete invocation has not been rerun.

## What passed and what is still open

The pinned Qwen3-VL-8B-Instruct BF16 checkpoint initialized and returned schema-constrained JSON for 16 images at both planned resolutions. Initialization inside the script took 36.47 seconds. Single coarse/fine calls took 2.23/1.54 seconds with 3,230/6,302 prompt tokens and 10 output tokens each. Both selected the sole red-rectangle frame `F07`.

Peak sampled GPU use was 70,067 MiB. vLLM reserved about 49.22 GiB for KV cache under `gpu_memory_utilization=0.85`; this is not the model's minimum VRAM requirement. Model loading itself reported 16.79 GiB. The two calls were sequential, in eager mode, and subject to warm-up/cache effects. These are compatibility observations, not production latency or detection benchmarks.

The public/synthetic check above did not test full MOV analysis or task accuracy. A later permitted development-video rehearsal exercised real offline POST/GET and source-JPEG provenance, but failed detection acceptance; see `development-rehearsal.md` and its separate receipt. Cross-camera robustness, training and adapter export remain untested. Organizer permission for development footage on the dedicated Canada VM is confirmed by the user. Reviewed supervision remains required before optional training. Backend contracts, source-timed decoding and API/pipeline mechanics now pass local tests; real development-video measurements are recorded separately. UI work remains deferred until the required library discussion.
