# Development role diagnostic, 17 October 2026

Qwen3.8-27B BF16 fits the rented A100 80 GB for this bounded image workload, but
does not reliably correct the reviewed actor error. Neither model is promoted.
No genuine legal violation is confirmed by this experiment.

The same fixed inputs were used for both pinned models: three context variants
of one development recording, twelve chronological source-derived analysis
images per variant, at most 196,608 pixels per image. The question asks for the
moving actor's role without suggesting a violation. The existing user correction
is held separately from the input pack. Private explanations and outputs are in
the private review file and private runtime artifacts, never this repository.

| Measurement | Qwen3-VL-8B-Instruct | Qwen3.8-27B |
|---|---:|---:|
| Valid structured responses | 3/3 | 3/3 |
| Agreements with existing role correction | 0/3 | 1/3 |
| Unclear/abstained | 2/3 | 1/3 |
| Confident conflicting role assignments | 1/3 | 1/3 |
| Median warm request time | 7.98 s | 13.03 s |
| Maximum warm request time | 9.16 s | 21.46 s |
| Model initialization | 35.45 s | 146.14 s |

These are three dependent context variants, not three independent recordings or
a general accuracy estimate. Agreement with the existing role correction does
not independently validate the generated explanation, cited frames, actor
identity correspondence or legal applicability. The experiment used deterministic
generation with thinking disabled, 768 output tokens, an 8,192-token context and
one active sequence. It does not test thinking-mode improvements.

One resident model ran at a time, with Docker networking disabled and public
weights downloaded beforehand. Observed peak GPU memory across the sequential
comparison was 73,307 MiB. That does not establish capacity for the production
sixteen-image fine windows, two concurrent sequences, co-resident retrieval
models, full video coverage or the end-to-end API deadline.

The public receipt pins revisions, image digest, input-manifest hash, code,
token counts, timings and aggregate results:
[model-size-diagnostic-20261017.json](../.context/verify/model-size-diagnostic-20261017.json).

The result supports testing explicit persistent actor correspondence and
transaction context before more model promotion or training. A larger VLM can
still attach a plausible role to the wrong person. It must not become the sole
annotator and judge of its own supervised targets. Thirty-one private development
templates were prepared, but there are no reviewed training targets or confirmed
positive controls from this work. The nine reserved recordings and jury data
were not used.
