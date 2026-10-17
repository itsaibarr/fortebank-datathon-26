---
date: 2026-10-17
tags: [fortebank, requirements, verification]
---

# The plan covers the case but the product still has to pass its checks

I reread the complete supplied case, including the API example, scoring table and all 35 FAQ answers. The newly attached DOCX has the same SHA256 as the earlier case. I rechecked the actual `open.zip` on disk. The architecture covers the requirements below; this is a requirements audit, not a claim that an unfinished product has passed runtime evaluation.

## Every mandatory requirement has an implementation check

| Case requirement | Planned behavior | Evidence needed before submission |
| --- | --- | --- |
| Sections 4 and 5 require a working browser workflow | Next.js upload, processing state, verdict, event cards and evidence. Build after backend mechanics; agree exact UI libraries with you first. | A new video completes in the browser without manual commands. |
| Section 10 requires `.mov` in field `file` | FastAPI streams the upload and probes the actual video. The specified upload allowance exceeds the case's approximately 29 MB example. | Real MOV plus corrupt/wrong-format/boundary checks. |
| API-key authentication | Require `X-API-Key` on both public endpoints. | Missing and wrong keys are rejected; correct key succeeds. |
| Asynchronous API | POST `/api/v1/analyze` returns `job_id`; GET `/api/v1/jobs/{job_id}` reports `processing`, `done` or `failed`. | Live POST/poll sequence and exact schema validation. |
| Exactly two completed verdicts | `no_violation` or `violation`; no successful third verdict. | Contract tests reject extra verdicts and inconsistent event lists. |
| Multiple events | Preserve separate events and merge repeated detections of the same action. | A reviewed multi-event fixture produces separate reports. |
| Event type and time | Return `type` and `timecode_sec` from source frames. | Compare with reviewed actions and actual source timestamps. |
| One to three JPEG evidence frames | `evidence_frames` contains `timestamp_sec` and raw JPEG base64 in `image_base64`. | Decode returned bytes and verify they come from the uploaded source. |
| Grounded description | Describe visible actions, cautious rule interpretation and limits. | Local human review finds no hidden-accounting, intention or identity claim. |
| Public Kazakhstan rules | Versioned source catalog with document, provision and URL. Put the reference in `description` to preserve the API schema. | Each emitted citation exists and applies to the stated visible condition. |
| Five-minute processing limit | Warm model; bounded inputs and two admitted jobs; 270-second internal target. | Client-measured completion below 300 seconds for the supported workload, including upload and result retrieval. |
| Local inference | Model and decoder execute inside our controlled service; no external AI API. | A complete job works with outbound Internet blocked after downloads. |
| No audio or face identification | Decode visual content only; no speaker, identity or face-recognition component. | Inspect enabled modules, prompts and runtime traffic. |
| New angle and unseen event types | Full-scene sequences, no fixed camera coordinates, cautious pretrained observations and rule checks. | Independent-angle development footage if available; disclose missing independent-angle evidence. Jury footage is never used for selection. |
| Low false positives and few misses | Report FP and FN separately; investigate both. Training is conditional on actual errors. | Development confusion counts, missed-event review and evidence-grounding checks. Never promise zero errors from 40 unique recordings. |
| Public service URL | Expose controlled HTTPS UI/API and give jury the API key. | External non-jury upload/poll rehearsal and uptime check. |
| Commercially usable open source | Reuse models/libraries with compatible licenses; build our own task-specific application. | Model revisions, dependency licenses and notices checked for the final image. No ready-made complete competition solution. |
| Required submission materials | Public addresses/key, startup guide, architecture/models, rule sources, supported categories, limitations and known errors. | Submission checklist includes every item in case section 8. |
| Dataset and test restrictions | Use the actual supplied archive; keep private files outside Git; never train/select on jury videos. | Archive checksum, private split manifest and access/retention checks. |

The case's FAQ does not require accounts, history, report export or batch upload. We will spend the first implementation effort on the mandatory workflow. The 8B minimum and Next.js choice are our team's additional constraints, not statements made by the case.

## Dataset use is explicit

Source archive is `/Users/itsaibarr/Downloads/open.zip`. SHA256 is `c01ee47563620f9cef14cc42fd23d81f4f58600e5d1eae39d97bb85b57961867`. The archive contains 42 MOV files and one XLSX. The earlier per-file hash/decode audit found 40 unique recordings, 21 positive and 19 negative after deduplication. Keep the original archive unchanged. Project setup includes a read-only checksum/inventory command so a different archive cannot silently replace it.

Use the development groups for baseline analysis and any later reviewed-data training. Keep the proposed nine-recording holdout reserved; review duplicate/session continuity before freezing the split. The provided timestamps support initial localization evaluation but do not establish exact event boundaries or categories. Those need local review.

## We handle ambiguous cases without inventing a third verdict

For a supported visible event, report the event even if another fragment is unclear; state the relevant visibility limitation in its description. A clean negative requires adequate coverage. Corrupt, unprocessable or timed-out jobs return `failed`. Do not use failure as a blanket substitute for hard visual decisions.

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

The case defines local inference as models running inside the team's deployed service, which fits our own model on a rented VM. Section 10 separately prohibits passing jury videos to third parties. It does not explicitly settle whether an infrastructure provider is allowed. The user confirmed organizer permission on 17 October 2026 for development footage on our dedicated Hyperstack VM in Canada. That development hosting gate is resolved. Jury videos remain excluded from training and model selection.

The case gives a submission time of 12:00 but does not establish a date or timezone in the attached text. Record the organizer's actual event deadline before scheduling the final deployment. Neither GPU speed, cross-angle accuracy nor adapter improvement has been measured yet.

The product repository is `/Users/itsaibarr/conductor/repos/fortebank-datathon-26`. Its specification and implementation checklist carry these acceptance checks. See [[GPU rental and access guide]], [[Training process and expected results]] and [[Computer vision stack and a 30 dollar GPU budget]].
