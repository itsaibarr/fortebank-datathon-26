# Producer exchange finding for steps 1–2

Consumer integration merges committed producer `7d9a1ca`. All 31 live current
pairs structurally validate with v1/v2 fields preserved. No completed immutable
reviewed release exists yet; the consumer does not declare one on the producer's
behalf. The live hash audit and proposed review choices remain private.

At that producer revision, `validate_pair` validates actor membership only inside
`if f.actor_id`. `training_targets` then iterates participating segments with
`any(...)`. A confirmed observed positive action with `actor_id: null` and empty
actor/participant segments passes those empty checks and can be exported when
the manifest is otherwise eligible. Independent-review strings alone do not
supply an actor or source-bound participation.

Reproduce without private data using
`test_actorless_positive_action_producer_bypass_rejected_by_consumer` in
`experiments/visual_learning/tests/test_release.py`. It builds the public
synthetic fixture, demonstrates the current producer behavior and verifies that
consumer target extraction, pair loading and release verification all reject it.
The consumer rejects the release rather than silently dropping the bad target.

The producer owner should require an actor and source-bound participating
segments for positive person-action targets, preserving actorless context where
appropriate. This branch leaves producer `annotations.py`, `tracking.py`, review
operations and all private annotations unchanged. No independent review or split
approval is inferred from fixing software validation.
