# Source-bound visual observations

The only production orchestration is `src/forte/pipeline.py`, described in
[report.md](../report.md). `timeline.py` schedules chronological overlapping
16-second windows at 12-second stride, about 1 FPS and at most sixteen images.
One 8B call per window emits concise Russian visible facts with actor/recipient,
source frame references, visibility, uncertainty and counterevidence. Code derives
PTS timestamps and merges observations/role histories; sampled envelopes are not
exact action boundaries. No model verdicts or legal explanation generation.

Only explicit missing visual dependencies trigger deduplicated reinspection:
same 8B, at most eight seconds, about 2 FPS, at most sixteen images, global budget
and original deadline. No unconditional overview, fine verification or final
reconciliation calls. Actual processor token counting enforces 8,192 tokens with
initial 768 output tokens. Skipped windows, errors, capacity overflow and unresolved
rechecks remain explicit; validated earlier observations survive later failures.

Original PTS/timebase/rotation and reversible crop transforms remain in ledgers.
Detector/tracker/ReID/model/human origins, reflection views with unknown owners,
proposed joins and role conflicts are separate. Review sidecars are immutable;
storage does not claim automatic correction uptake. Export one to three original
JPEGs per reported event, retaining every required decisive/role/context frame.
Private artifacts stay outside Git; human review uses the local packet.
