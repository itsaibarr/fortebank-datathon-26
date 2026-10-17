# Setup source checks on 17 October 2026

- Supplied case was read in full, including section 10 and all 35 FAQ answers. Attachment SHA256 matches `configs/provenance.json`; the original file remains outside this repo.
- Supplied `open.zip` was hashed, inventoried and CRC-checked locally through the new project command. It was not extracted or changed. The earlier structural/decode audit remains the source for unique-recording counts and annotation limitations.
- [Hyperstack getting started](https://docs.hyperstack.cloud/docs/getting-started/) verifies the environment, image, SSH key, public IP, ACTIVE state and Ubuntu SSH flow. Read using Agent-Reach's Jina route and official web documentation.
- [Hyperstack flavor catalog](https://docs.hyperstack.cloud/docs/hardware/flavors/) verifies `n3-A100x1`, GPU count/VRAM, host CPU/RAM, disks and region. No live account allocation was inspected.
- [Hyperstack pricing](https://www.hyperstack.cloud/gpu-pricing) was rechecked for A100 $1.35/hour and separate public-IP/storage charges. Actual checkout, stock, tax and minimum top-up remain unverified.
- [Provider OS images](https://docs.hyperstack.cloud/docs/virtual-machines/images/) and [driver compatibility](https://docs.hyperstack.cloud/docs/hardware/gpu-driver-compability/) document R595/CUDA 13.2 with Docker. Availability for the selected flavor must still be checked in the console.
- [vLLM v0.31.0 Dockerfile](https://github.com/vllm-project/vllm/blob/v0.31.0/docker/Dockerfile) was actually fetched; `ARG CUDA_VERSION=13.0.3` is its default. This is source evidence, not proof that an unpulled image has that exact runtime or that a host works.
- [Billing policy](https://docs.hyperstack.cloud/docs/billing/billing-policies/) and [VM state charges](https://docs.hyperstack.cloud/docs/billing/states-and-billing/) verify that stopped VMs bill and zero credit is not a hard spending cap. The user retains lifecycle control unless separately delegated.
- [Runpod pricing](https://www.runpod.io/pricing) supplies the $1.79/hour Secure A10080 fallback; no Pod was allocated.
- The inspected [LlamaFactory recipe](https://github.com/hiyouga/LlamaFactory/blob/1fded918ac4723ac9966363f51ed4500866c5d1d/examples/train_lora/qwen3vl_lora_sft.yaml) uses 4B/demo data and needs the approved 8B/private-data configuration. Training/export compatibility is pending a GPU smoke test.

Setup uses the actual existing Harness bootstrap and copied contracts; no Harness files or global settings changed. Only project-local Python dependencies were installed. No X research, external messages, private-media upload or paid work occurred.
