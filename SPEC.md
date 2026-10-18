# Product specification

The accepted architecture is [report.md](report.md); all implementation follows its
single frozen 8B → CPU Laya → deterministic decision path.

## Contracts and security

Preserve `contracts/api-contract.json` exactly: multipart MOV `file`, `X-API-Key`,
202 `job_id`, polling with processing/done/failed and binary violation/no_violation.
Insufficient evidence becomes failed v1, never a successful negative. Rich v2/UI,
source/evidence, immutable correction and report routes adapt the same pipeline.
V2 execution, assessment and human-review state remain independent.

Maintain authenticated principal ownership on all private resources. Trusted
session gateway uses same-origin protected cookies, CSRF, explicit upload
activation and same-socket upstream ownership verification. Key-only operation
remains single-reviewer private. No service secrets enter browser source.

## Inference invariants

Decode original PTS/timebase/rotation; retain reversible crops and recording hashes.
Track detector, tracker, ReID, model and human origins separately. Preserve role
history, unresolved identity, proposed joins, reflection views with nullable owner,
counterevidence, immutable revisions and previously cited frames.

Schedule overlapping 16-second windows every 12 seconds across the full duration,
up to sixteen images at about 1 FPS; one observation pass per window. Ambiguity
alone triggers deduplicated same-model reinspection, at most eight seconds and
sixteen images at about 2 FPS, with a global budget and original absolute deadline.
Use 8,192 total visual tokens and initial 768 output tokens, actual processor
admission counts and explicit overflow/partial coverage. Sparse samples do not
establish continuous visibility, exact action boundaries or absence.

Qwen/Qwen3-VL-8B-Instruct revision
`0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` remains frozen BF16.
CPU FP32 `convaiinnovations/laya-multilingual` revision
`1720e3e3357cfe1e281542e223f8273b0890ca34` receives text only, with explicit
satisfied/contradicted/unknown choices. Count its exact tokenizer sequence,
including instructions/options/state, under 1,024 tokens. Refuse all truncation;
keep counterevidence. Batch at most four independent rows. Missing Laya fails
readiness. Injected backends are test fixtures only.

Local BM25/exact official-law retrieval retains clauses, parent context, notices,
editions and source hashes. Code owns condition polarity, scope, prerequisites,
exceptions, metadata, evidence and templates. Draft cards stay draft. Unknown
calendar dates/institution facts are not inferred from source PTS or filenames.
A missing-action conclusion needs a complete visible opportunity. Separately
supported events survive unrelated incomplete work; clearance needs full scope.
Export one to three original JPEGs per reported event, including every required
role/context/decisive frame. If they cannot fit, retain insufficient evidence.

## Runtime and acceptance

One host/application container, local visual queue and resident CPU decisions;
atomic jobs, at most two admissions, 256 MiB upload, 180-second validated duration,
30-second upload bound, 270-second absolute job target from upload start.
No new database, queue, frontend system, model router or weight updates.

Approved UI: Next.js/TypeScript, Tailwind, shadcn and Lucide. Keep source playback,
event markers, participant/evidence/conditions, correction history and useful errors.

Private data never enters Git or external AI inference. Private execution requires
explicit authorization and OS-enforced outbound denial after public staging.
Reserved/jury data never enters training or selection; duplicate recordings stay
in one split; session grouping needs review. Synthetic checks establish mechanics,
not accuracy, latency, memory, legal approval or deployment acceptance.
No paid resources, model downloads, live changes, private runs or deployment under
source-cleanup authorization. Real acceptance tasks remain in `tasks/todo.md`.
