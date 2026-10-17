# ForteBank Datathon 26 product specification

User approved local project setup on 17 October 2026 and subsequently provided a Hyperstack API credential with explicit permission to configure the GPU environment within $30. The user handles the top-up. The agent may provision and manage this project's resources after verifying credit, rates and cleanup controls, without asking again for the same authorization. It may not initiate payments, enable auto-top-up, publish private data or bypass the reviewed-data training gate. The supplied case, including all 35 FAQ answers, was reread and reconciled before setup.

## Inputs and outputs

Use the actual supplied `open.zip`, expected SHA256 `c01ee47563620f9cef14cc42fd23d81f4f58600e5d1eae39d97bb85b57961867`. It contains 42 MOV files and one XLSX; the prior full audit found 40 unique recordings. Keep originals unchanged and all private recordings, annotations, frames, descriptions and derived adapters outside Git. No audio analysis or face identification.

The final service accepts a new video, analyzes visually observable actions and provides a cautious assistance verdict, event types, source timestamps, one to three real JPEGs per event and a visible-action explanation with a relevant public Kazakhstan rule. Never infer hidden accounting facts, intent, identities or unavailable internal rules.

## Fixed public contract

`POST /api/v1/analyze` requires `X-API-Key` and a multipart MOV field named `file`, and returns HTTP 202 with `job_id`. `GET /api/v1/jobs/{job_id}` requires the same header and returns `processing`, `done` or `failed`. Completed results use only `no_violation` or `violation` and the case's fields `job_id`, `status`, `verdict`, `violations`, `type`, `timecode_sec`, `description`, `evidence_frames`, `timestamp_sec`, `image_base64`. Legal document/provision/URL go in `description`.

The normative OpenAPI contract is `contracts/api-contract.json`, copied without schema changes from the approved research. Accept approximately 29 MB case videos within the specified 256 MiB upload and 180-second duration bounds. The case supplies clips of 10 to 145 seconds. Validate actual format, dimensions and duration; an extension alone is insufficient.

Target 270 seconds from upload start and verify client completion under 300 seconds. Warm models before admission. Admit at most two jobs and reject overflow; keep polling responsive. Corrupt/unprocessable/timeout jobs fail explicitly. Return verified positive events with a stated visibility limitation if another fragment is unclear. Never treat a skipped or undecoded clip as a clean negative.

## Selected processing architecture

Use `Qwen/Qwen3-VL-8B-Instruct` revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`, BF16. Fallback is `OpenGVLab/InternVL3_5-8B`. The 8B minimum is the team's constraint. Model-specific preprocessing stays behind a stable window-analysis interface.

Use PyAV/FFmpeg for source PTS and rotation. Coarse windows are 16 seconds at 12-second stride with 1 FPS, at most 16 images and 196,608 pixels per image. Fine neighborhoods are 8 seconds at 2 FPS, at most 16 images and 393,216 pixels per image. Check actual processor counts against 8,192 context tokens. Every supplied image has an ID linked to source timing. Model output selects supplied frame IDs; application code derives timestamps.

Scan the complete duration, inspect candidates, verify evidence with a separate prompt, merge reports of the same action, and preserve distinct events. Use a reviewed local rule catalog. An omission needs visible transaction context and the full opportunity to perform the required action, with a source-frame boundary timestamp. No fixed-camera-only crop rule or closed set of training labels may silently suppress unseen event types.

Use one controlled GPU host and one deployable application container with FastAPI and a local vLLM process. Start from vLLM v0.31.0, then verify the pinned image and driver on the actual host. Store atomic filesystem job records; no database, Redis, Celery or vector store. No external AI endpoint receives video, frames, captions or sensitive descriptions. After downloading public weights/dependencies/rules, a complete job must work with outbound Internet blocked.

## Frontend gate

Frontend is Next.js App Router with TypeScript. Plan static export served through FastAPI on the same origin. Browser code calls the existing API; no job data is fetched during frontend build. Build the UI only after backend mechanics and quality/hardening checks. Before any UI implementation or UI-library installation, ask the user for the exact component/styling and supporting libraries, and agree a screen/state brief. No design system is selected yet.

Final UI requires video upload, processing, the two verdicts, event list, timestamped source evidence, cautious descriptions, public-rule links and useful error states. Accounts, history, batch upload and report export are not case requirements.

## Evaluation and optional training

Preserve recording groups and exact duplicate pairs. Resolve or flag the 57/68-second point conflict on the identical positive recording. Freeze groups before tuning. Proposed initial development/holdout counts are 31/9, subject to local session-continuity review. Jury videos never enter training or model selection; touch the locked holdout once after freezing choices.

The first version has no adapter. Optional LlamaFactory language-attention BF16 LoRA requires locally reviewed categories, intervals, evidence facts and negative windows, plus repeated baseline errors. Freeze vision and projection, rank 8/alpha 16/LR 5e-5, batch 1/accumulation 8, gradient checkpointing. Initially one pass and at most 30 updates; at most two passes and 60 total updates only if development evaluation improves. The $30 experiment envelope is separate from development time. No training has occurred.

Measure video accuracy, FP/FN, localization, category quality where labels exist, evidence relevance, explanation grounding, rule applicability, cross-angle limitations, end-to-end time, peak VRAM and spend. Promotion needs at least two corrected reviewed missed events, no added false-positive videos, no worse median time error, grounded evidence and latency compliance. Otherwise retain the base model.

## Hosting and submission gates

Preferred rental is Hyperstack `n3-A100x1`, one A100 PCIe 80 GB. On 17 October 2026 the funded API check verified $1.35/hour compute and $0.006720430/hour public IP. One VM used the compatible Ubuntu R570/CUDA12.8 Docker image 517; the R595 image initially considered is hard-restricted to B300 flavors. The pinned vLLM 0.31.0 container passed BF16 Qwen3-VL-8B offline synthetic checks with CUDA compatibility enabled, then the VM was deleted. The observed account-credit reduction was about $0.23, leaving $29.77 at the post-deletion snapshot. See `.context/verify/gpu-setup.json` for actual limits and receipts. Recheck rates/stock before another allocation. Include additional storage charges if introduced, retain a reserve, establish cleanup before allocation and manage only recorded project resource IDs. Fallback Runpod Secure A100 PCIe 80 GB is advertised at $1.79/hour, but the supplied key authorizes Hyperstack access only. Full-video quality, latency, concurrent jobs and training remain unmeasured. Existing older H100 budgets are superseded.

The user confirmed on 17 October 2026 that organizers allow development videos from open.zip on our dedicated Hyperstack VM in Canada. Inference executes inside our controlled service, never a third-party AI API. Keep recordings and sensitive outputs private and out of Git/chat. Jury data remains excluded from training/model selection; reviewed supervision remains required before adapter training.

Before submission provide public HTTPS UI/API addresses and jury key, startup/usage instructions, architecture and model list, rule catalog, supported categories, limitations and known errors. Check commercial-use licenses for final weights and dependencies. Use libraries and pretrained models, never a ready-made complete competition solution. Keep data use within the hackathon and document end-of-event cleanup. The case says 12:00 but supplies no date/timezone; confirm the actual organizer deadline.

## Source records

Case SHA256 is `f73a951c87aca9d540076aacc5b4fd8a688810a4ec827b1a382512c770d278a0`. Full research, dataset/decode audit, source ledger and original ADRs are in `/Users/itsaibarr/conductor/repos/aibar/research/fortebank-datathon-26`. The latest Obsidian case matrix and guides are linked from `README.md`. The user approved setup; runtime requirement compliance remains to be demonstrated.
