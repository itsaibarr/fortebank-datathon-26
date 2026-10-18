---
date: 2026-10-18
tags: [fortebank, requirements, verification]
---

# Case requirements and current acceptance checks

This audit maps the supplied case, API example, scoring table and FAQ to the
accepted [architecture](../report.md) and [specification](../SPEC.md). The source
audit recorded matching case-document hashes and the archive inventory below.
Those historical observations do not establish acceptance of the current runtime.

The current technique is original source-PTS decoding, YOLOX-s/ByteTrack with
frozen OSNet correspondence, frozen Qwen3-VL-8B visual facts, local CPU Laya
three-state condition proposals, and deterministic rule/evidence/verdict code.
The same 8B performs bounded visual rechecks. Both APIs use this single pipeline;
all weights stay frozen. Runtime and semantic acceptance remain open in
[tasks](../tasks/todo.md).

## Every mandatory requirement has an implementation check

| Case requirement | Planned behavior | Evidence needed before submission |
| --- | --- | --- |
| Sections 4 and 5 require a working browser workflow | Retain the approved Next.js/TypeScript, Tailwind, shadcn and Lucide upload, processing, verdict, event and evidence workflow. | A new video completes in the browser without manual commands. |
| Section 10 requires `.mov` in field `file` | FastAPI streams the upload and probes the actual video. The specified upload allowance exceeds the case's approximately 29 MB example. | Real MOV plus corrupt/wrong-format/boundary checks. |
| API-key authentication | Require `X-API-Key` on both public endpoints. | Missing and wrong keys are rejected; correct key succeeds. |
| Asynchronous API | POST `/api/v1/analyze` returns `job_id`; GET `/api/v1/jobs/{job_id}` reports `processing`, `done` or `failed`. | Live POST/poll sequence and exact schema validation. |
| Exactly two completed verdicts | `no_violation` or `violation`; no successful third verdict. | Contract tests reject extra verdicts and inconsistent event lists. |
| Multiple events | Preserve separate events and merge repeated detections of the same action. | A reviewed multi-event fixture produces separate reports. |
| Event type and time | Return `type` and `timecode_sec` from source frames. | Compare with reviewed actions and actual source timestamps. |
| One to three JPEG evidence frames | `evidence_frames` contains `timestamp_sec` and raw JPEG base64 in `image_base64`. | Decode returned bytes and verify they come from the uploaded source. |
| Grounded description | Code renders templates from validated visual facts, condition findings, exact provisions and limits. | Local human review finds no hidden-accounting, intention or identity claim. |
| Public Kazakhstan rules | Versioned source catalog with document, provision and URL. Put the reference in `description` to preserve the API schema. | Each emitted citation exists and applies to the stated visible condition. |
| Five-minute processing limit | Warm both local models; one visual queue, bounded inputs and two admitted jobs; 270-second absolute target from upload start. | Client-measured completion below 300 seconds for the supported workload, including upload and result retrieval. |
| Local inference | Model and decoder execute inside our controlled service; no external AI API. | A complete job works with outbound Internet blocked after downloads. |
| No audio or face identification | Decode visual content only; no speaker, identity or face-recognition component. | Inspect enabled modules, prompts and runtime traffic. |
| New angle and unseen event types | Full-scene sequences, no fixed camera coordinates, cautious pretrained observations and rule checks. | Independent-angle development footage if available; disclose missing independent-angle evidence. Jury footage is never used for selection. |
| Low false positives and few misses | Report FP, FN and abstentions separately; review facts, evidence and applicability with frozen weights. | Development confusion counts, missed-event review and evidence-grounding checks. Never promise zero errors from 40 unique recordings. |
| Public service URL | Expose controlled HTTPS UI/API and give jury the API key. | External non-jury upload/poll rehearsal and uptime check. |
| Commercially usable open source | Reuse models/libraries with compatible licenses; build our own task-specific application. | Model revisions, dependency licenses and notices checked for the final image. No ready-made complete competition solution. |
| Required submission materials | Public addresses/key, startup guide, architecture/models, rule sources, supported categories, limitations and known errors. | Submission checklist includes every item in case section 8. |
| Dataset and test restrictions | Use the actual supplied archive; keep private files outside Git; never train/select on jury videos. | Archive checksum, private split manifest and access/retention checks. |

The case's FAQ does not require accounts, history, report export or batch upload.
The retained product provides principal ownership, browser sessions, immutable
corrections and review resources; these protections remain part of acceptance.
The exact frozen 8B/Laya selection and approved UI stack are team decisions.

## Dataset use is explicit

Source archive is `/Users/itsaibarr/Downloads/open.zip`. SHA256 is `c01ee47563620f9cef14cc42fd23d81f4f58600e5d1eae39d97bb85b57961867`. The archive contains 42 MOV files and one XLSX. The earlier per-file hash/decode audit found 40 unique recordings, 21 positive and 19 negative after deduplication. Keep the original archive unchanged. Project setup includes a read-only checksum/inventory command so a different archive cannot silently replace it.

Use the development groups for separately authorized evaluation and calibration.
Training and weight updates are outside the accepted architecture. Keep the
proposed nine-recording holdout reserved; review duplicate/session continuity
before freezing the split. The provided timestamps support initial localization
evaluation but do not establish exact event boundaries or categories. Those need
local review.

## We handle ambiguous cases without inventing a third verdict

For a supported visible event, report the event even if another fragment is unclear;
state the relevant visibility limitation in its description. A clean negative
requires adequate evaluated rule scope and coverage. Insufficient evidence becomes
`failed` in v1, never a successful negative. Rich v2 keeps execution, assessment
and human-review state separate. Corrupt, unprocessable or timed-out jobs fail.

For a missing mandatory action, flag an omission only if the required action and the complete opportunity to perform it are visible. Use the source frame where the transaction reaches the relevant boundary as the event timestamp and include before/after context. A sparse frame sequence that merely fails to show an action is not proof of omission.

The case permits event types absent from the supplied training set. Candidate observations must therefore not be limited to learned label names. Reporting an unfamiliar concern still needs visible evidence and an applicable public rule. No claim may depend on an internal bank rule that was not supplied.

## The scoring table controls evaluation effort

| Criterion | Points in case | What we measure |
| --- | --- | --- |
| Detection | 25 | Video-level verdict accuracy, FP and FN counts |
| Localization | 15 | Source-time error and evidence relevance |
| Classification | 15 | Accuracy on locally reviewed categories; disclose missing category labels |
| Rule justification | 15 | Citation validity, applicability and explanation grounding |
| Robustness | 10 | Separate recording groups and an independent camera angle when available |
| Product readiness | 10 | Complete UI/API flow, errors, uploads and reliability |
| Technical solution | 10 | Offline inference, latency, memory, licenses and reproducible operation |

## These conditions remain unresolved

The case defines local inference as models running inside the team's deployed
service. The earlier organizer permission for development hosting does not
authorize a new resource, private run or deployment. Current private execution
requires explicit authorization and OS-enforced denied egress after public asset
staging. Jury videos remain excluded from model selection and calibration.

The case gives a submission time of 12:00 but does not establish a date or timezone
in the attached text. Record the organizer's actual deadline before scheduling
deployment. Earlier GPU timings and failed exploratory recognition checks retain
their original source/model identities in historical receipts. They do not measure
the current architecture's quality, cross-angle accuracy, latency or memory.
See [runtime guidance](backend.md) and the remaining [acceptance tasks](../tasks/todo.md).
