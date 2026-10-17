# Research: visual grounding, Kazakhstan rules, and the next model experiment

Checked 17 October 2026. This is a revised research recommendation, not an implemented RAG system, trained model, or claim of complete legal coverage. No new GPU was rented for this research. Private scene descriptions remain in the local review JSON.

## Recommendation

Build a versioned local corpus of relevant official Kazakhstan acts and an auditable set of video-verifiable obligations. Separate actor/action observations from legal retrieval and applicability. Add persistent anonymous actor tracks and transaction context, then compare the current Qwen3-VL-8B with the native multimodal **Qwen3.8-27B** on the same reviewed reference cases. Fine-tune only after this comparison identifies a recurring, learnable error and reliable targets exist.

The user should not have to know Kazakhstan law to correct an actor assignment. Observable facts and legal interpretation need separate annotation fields and separate review. We should prepare the legal mapping and proposed labels, with ambiguous applicability or unavailable business context explicitly identified for review.

## What the present system actually does

The packaged `src/forte/data/rules.json` contains three provisional predicates from NBK Resolution 231: points 20 and 22. `rules.py` checks the cached source hash and loads those predicates. It does not search the web, retrieve the full act, or use RAG at inference time.

The complete cached act exists locally, but the model receives only the three selected predicates. Candidate generation itself is constrained to their rule IDs: see `src/forte/inference.py:128` and the generation schema. This can limit discovery to those categories. The role verifier does not see the candidate narrative initially, but it uses the same VLM on sampled frames. There is no detector/tracker maintaining a person's track ID across the recording. Those are observed implementation facts; whether larger capacity or better temporal evidence contributes most remains unmeasured.

The latest user review rejects the new report as well. The detailed correction is recorded privately. Passing frame-ID, JPEG provenance, schema and earlier-role-frame checks does not establish that the role interpretation is correct. The latest five-case GPU run still has one supplied-negative alert and four insufficient-evidence failures.

## Domain findings: collect rules with their scope

The primary seed is [NBK Resolution 231, 29 November 2019](https://adilet.zan.kz/rus/docs/V1900019680), covering bank cash operations and collection. Its cached official text distinguishes cash acceptance from payout, denomination exchange and other operations. For example, point 20 addresses acceptance/counting in a customer's presence; point 31 contains payout duties, including counting before handing money over; point 22 concerns the cashier leaving before service is finished and sits within the acceptance section. A correct interpretation needs that parent section and transaction context, rather than an isolated matching sentence. The source also delegates some procedures to internal bank documents, which were not supplied and cannot be invented.

Follow the base act's actual cross-references. Its point 5 links to [NBK Resolution 14, 24 February 2020, premises/security rules](https://adilet.zan.kz/rus/docs/V2000020075). Its point 58 links to [NBK Resolution 49, 4 April 2019, foreign-currency exchange rules](https://adilet.zan.kz/rus/docs/V1900018545). These are candidate corpus members whose applicable versions and video relevance need verification. The [NBK 2024 bulletin](https://nationalbank.kz/file/download/107733) records an amendment to Resolution 14. This is a reason to follow the amendment chain, not to use whichever older security rule ranks first in search.

An official [NBK explanation](https://nationalbank.kz/file/download/106258) also identifies Resolution 231 as governing cash acceptance/payout. The explanatory publication is useful corroboration; the normative act remains the source for an obligation.

“All rules” should mean all applicable public obligations within the agreed cash-operation scope, with a coverage register. It cannot mean every Kazakhstan act is reliably detectable from CCTV. For each provision, record whether it is visually testable, requires documents/accounting records, depends on an internal procedure, or falls outside the observed operation. Customer identity validity, account posting, exact amounts and authorization records generally cannot be established from these clips alone.

### Retrieval status and provenance limits

The existing official-text snapshot is 226,017 bytes and matches the packaged SHA256. Fresh direct Adilet/Jina access returned a 460-byte JavaScript welcome shell, not the act. Official EKB export probes failed with certificate/fetch errors. Two collaborative-browser snapshots timed out; a subsequent DOM-read probe also timed out. Official search-index excerpts corroborate selected provisions, but they do not establish a newly downloaded, complete, current corpus.

Therefore corpus ingestion and current-version verification are **not complete**. An unofficial `adilet.kz` mirror appeared in search; it is a different domain from `adilet.zan.kz` and is not accepted as normative evidence. Preserve this distinction in the ingest allowlist. Reject welcome shells, empty exports, missing sections and stale versions rather than marking a crawl successful from HTTP 200 alone. A version date discovered through a mirror is a verification lead, not authority.

## Proposed local legal retrieval

Download official texts once during corpus preparation, retain raw snapshots and hashes, and freeze a dated release for inference. Refresh between releases when an official amendment changes an applicable act. No per-video Internet search is needed, and legal text updates need not require model retraining.

Each clause record should retain act ID, issuer, title, official URL/anchor, language, provision/subparagraph, parent headings, definitions, cross-references, exceptions, effective dates, retrieval date, source hash and review state. Preserve original text alongside a derived operational rule card. Split by legal hierarchy; retrieve neighboring context and referenced definitions rather than arbitrary detached character chunks.

Start with local lexical retrieval plus multilingual embeddings and reranking. [BGE-M3/FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) provides dense and lexical retrieval and multilingual rerankers; it is a candidate to evaluate on Russian legal queries, not proof of Kazakhstan-law retrieval quality. The initial corpus can be held in local files and an in-memory index; RAG does not require a hosted vector database.

Retrieve from neutral observed actions, transaction phase and actor roles. Do not form a search query by assuming the proposed violation is true. Retrieve both obligations and possible exceptions. A matching clause supplies an applicable hypothesis; it is not visual evidence. Evidence remains source frames and their temporal sequence.

Keep a coverage pass over all potentially applicable, video-verifiable obligation families. Nearest-neighbor top-k alone can miss a duty, and a catalog limited to three rule IDs can suppress discovery before retrieval starts. The proposed observation interface should permit ordinary actions and unfamiliar events without requiring a legal category up front.

Evaluate retrieval separately with expected clause IDs and authoritative spans, including acceptance/payout confusion, negated queries, exceptions, repealed versions, internal-policy-only questions and cases with no applicable public rule. [LegalBench-RAG](https://github.com/zeroentropy-ai/legalbenchrag) demonstrates span-based retrieval precision/recall evaluation. Its contract datasets are not a Kazakhstan compliance benchmark; reuse the evaluation idea with our own reference questions.

## Open-source video research and what it contributes

- [LAVAD, CVPR 2024](https://github.com/lucazanella/lavad): captions, temporal aggregation, caption cleaning and anomaly-score refinement. Useful evidence that temporal context and noisy descriptions need explicit treatment. Its surveillance benchmarks and multi-model pipeline do not validate bank-rule interpretation.
- [VERA, CVPR 2025](https://github.com/vera-framework/VERA): learns guiding questions using video labels and validation, then estimates/refines anomaly scores. It illustrates measured prompt learning, rather than unbounded manual prompt changes. Its published generic questions include signals outside this case's scope, so they should not be copied unchanged.
- [CoReVAD, ICPR 2026](https://github.com/Muk-00/CoReVAD): a frozen VLM with local response cleaning and temporal refinement. Useful as a reference for checking generated descriptions against visual features. It does not provide a cashier-role or Kazakhstan-law oracle.
- [VadCLIP, AAAI 2024](https://github.com/nwpu-zxr/VadCLIP): adapts CLIP with temporal components and weak video-level supervision. It could inform candidate localization, but binary anomaly labels do not supply actor-grounded legal explanations.
- [ByteTrack](https://github.com/FoundationVision/ByteTrack) associates detections across frames; [SAM 2](https://github.com/facebookresearch/sam2) supports prompted video segmentation/propagation. These can supply persistent object correspondence. Neither assigns the semantic role “cashier.” ByteTrack declares MIT and SAM 2 Apache-2.0; separately verify any detector/checkpoint license before adoption.

Repository revisions and declared licenses are pinned in `.context/verify/domain-research-sources.json`. LAVAD, VERA and CoReVAD were not cleared for code reuse from their GitHub license metadata. Study their methods; review actual code/weight terms before copying anything. The public [Lighthouse-AI cashier-compliance starter](https://github.com/st2offer-bot/Lighthouse-AI) explicitly describes placeholder verdicts; its README was inspected for research and it is not adopted as a completed competition solution.

### Proposed visual representation

Track anonymous people across the sequence. Keep a full-scene view plus track-conditioned crops and a timeline of observable workstation/object interactions. Derive roles from those interactions and continuity, with an unresolved state when occlusion or a track switch prevents support. Do not use appearance, face identification or fixed left/right coordinates as role definitions.

Track IDs should persist within a clip. Any role change needs new evidence; a new window should not silently invent a new actor. Transaction phases should include acceptance, payout, ongoing/finished/uncertain service and relevant handoffs when visible. Track continuity can still be wrong, so test identity switches and occlusion explicitly.

Use denser sampling around handoffs and movement boundaries, plus earlier/later context for role establishment. This is a hypothesis to compare, not a claim that a particular FPS will solve the problem. Annotated crops/IDs may be analysis inputs; returned evidence must remain unchanged source JPEGs.

## Is 27B justified?

Yes as a benchmark candidate. The official [Qwen3.8-27B card](https://huggingface.co/Qwen/Qwen3.8-27B) identifies a native image/video model with controllable thinking and Apache-2.0 licensing. Pin `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`. Its public weight index totals 55,562,855,904 bytes, about 51.75 GiB, before runtime state and visual activations. Those files were inspected as metadata; weights were not downloaded.

One A100 80 GB is a plausible bounded-inference test target, not a proven fit or latency result. Use one resident model at a time, short measured context and one active sequence initially. Account for the visual encoder, cache/state and generation buffers. The old 8B service's reserved memory cannot be added to a 27B service. The official [vLLM recipe](https://recipes.vllm.ai/Qwen/Qwen3.8-27B) requires model-specific serving/reasoning configuration; its examples do not establish A100 performance on our videos. [Unsloth's guide](https://unsloth.ai/docs/models/qwen3.8) distinguishes quantization/hardware paths; a Blackwell-only NVFP4 recipe is not an A100 recipe.

Run the same reference cases with the current 8B and 27B model, with fixed frame inputs, law snapshot and evaluation rubric. Compare actor correctness, continuity, transaction phase, event localization, grounded explanation, false reports, misses, abstentions and end-to-end latency. Then measure the proposed tracking/context change separately. A newer model changes both size and training generation; a gain cannot be attributed to parameter count alone. More reasoning tokens also consume the five-minute budget and can expand an incorrect premise.

## Annotation and supervised learning

Prepare two linked annotation layers. The visual layer contains anonymous track IDs, role-supporting evidence or uncertainty, actions, objects, intervals and source-frame IDs. The legal layer contains the proposed applicable act/clause/version, each prerequisite and exception, a short evidence-linked rationale and a review status. A visually confirmed action can have an unresolved legal label.

I can research the official rules, derive proposed rule cards, and prepare annotation drafts with an approved local model. The user need only correct visible facts they can verify; they should not have to research RK law. Ambiguous legal/business-context labels need an operations/legal reviewer or must stay unresolved. The current confidentiality boundary still keeps private frames out of external AI inference, so this research did not send videos to a remote vision model.

A stronger local model can propose labels, but its drafts are not independent ground truth. Training the current model on its repeated wrong role assignment would preserve the error. Review the targets used for training and keep reviewed evaluation cases separate by recording group. The dataset has 40 unique recordings; slicing them into many windows does not create independent camera/session evidence.

SFT should teach concrete outputs: supported role/action/interval, relevant evidence, applicable rule or no rule, and calibrated uncertainty. Include hard negatives, near misses and interrupted/finished service. Use concise evidence-grounded rationales rather than invented long reasoning traces. Keep the changing legal corpus outside the weights.

Start with a small LoRA/QLoRA experiment only if the untrained 27B/reference comparison leaves repeated errors that reviewed targets can address. The [Qwen repository](https://github.com/QwenLM/Qwen3.8) lists supported training frameworks. Confirm the chosen framework supports the exact vision/video model and dataset format. Do a memory smoke test: quantizing frozen weights does not eliminate activation/backpropagation memory. Full-parameter 27B training is not the proposed budget experiment.

## Concrete next work order and acceptance

1. **Corpus and rule cards:** verify official exports/versions, structure the scoped act inventory, classify observability and retain definitions/exceptions. Deliver a coverage register; do not claim all public duties are implemented from a three-rule seed.
2. **Reference annotations:** prepare law-independent actor/action tasks and proposed legal mappings for development recordings. Carry the user's existing corrections into evaluation. Resolve recording groups before model selection and review ambiguous legal labels without shifting legislation research to the user.
3. **Controlled model comparison:** compare current 8B and pinned 27B first; then test track-conditioned temporal evidence. Test normal cases, real supported events and hard negatives. Source evidence must be correct and relevant; failures count against quality; latency must fit the case limit.
4. **Optional adapter:** train on reviewed development targets, compare against the untuned model on separate recording groups, and retain it only if measured behavior improves without additional false reports. Keep holdout/jury data excluded.

Current deliverables are this recommendation, primary-source/repository pins and a seed legal inventory. RAG ingestion, tracking, model replacement and SFT remain unimplemented. The public API, working checkout and existing outputs are preserved. No additional GPU cost was incurred for this research.
