# Steps 3–4 handoff

The independent preparation is executable in branch `experiment/visual-learning`,
worktree `/Users/itsaibarr/conductor/repos/fortebank-visual-learning`. Start with
[README.md](README.md) for exact commands, gate receipts, profile isolation and
limitations. The production pipeline and the running producer checkout were not
edited. Producer commits 7131f73 and aeeb158 were merged only into this worktree.

Software delivered: `forte-visual release-check`, `export`, `compare`, `train`,
`scan` and `evaluate`, plus `evaluate-adapter`, `evaluate-tracks`, `evaluate-scan`
and `synthetic`. The scan CLI runs a synthetic mock; controlled executors can use
the library planner, track-scoped role cache and timeline assembler. Exported
references stay physically separate from inference inputs. An exact-source receipt
and a conservative versioned reader isolate the producer interface.

Verification: **135 passing tests** (42 experiment + 93 committed producer), Ruff
check/format, experiment and product sdist/wheel builds, all CLI paths exercised
on synthetic blocks, including dry runs. The 30-second scan regression verifies
cross-window ID stability, three coarse windows, all fine calls within 16 images,
and the final source frame. Fractional-start frame duplication was found and fixed.
Four existing warnings remain. CUDA frameworks are absent from the CPU environment.

Actual experiments: two synthetic groups/six cases with two independent mock
executions, both abstaining; two known synthetic action misses, role precision
undefined at zero answer coverage, source validity 1, zero failed jobs/invalid
references. These are software-test outcomes, not a quality estimate. The synthetic
scan executes nine calls, covers the eight-second coarse schedule and sampled
fine envelope, and keeps the whole duration unresolved for omission purposes.
Proposal recall is 1 on its single synthetic event; event recall is 0. Tiny NumPy
assistant-only CE updates and exact adapter reload pass (max error 0). Spend is $0;
no VM was allocated and no full model was loaded. Aggregate evidence is in
[configs/synthetic-verification.json](configs/synthetic-verification.json).

Real compatibility/readiness: the adapter imports the actual aeeb158 TrackManifest
v1, separate counterpart evidence, participant direction and review validation.
The completed-release envelope remains provisional because no completed reviewed
producer export was supplied. A live metadata check reports 31 proposal packets,
zero reviewed segments/roles/actions/training targets. No semantic scene content
was read by remote tools and no actively edited packet was snapshotted. Required
next inputs are listed in README: completed immutable export/allowlist/provenance,
reviewed Gate A pilot and near misses, frozen Gate B session split/class coverage,
and oracle-to-automatic track correspondence.

Model selection: **not executed on reviewed data; no model selected**. The mock
report is inconclusive. Both exact 8B and 27B remain candidates, with primary
metadata/source hashes and distinct architectures recorded. No inference-fit,
full-model backward-fit, visual-learning or promotion claim follows from locks or
tiny tensors. A selected 27B first receives its exact offline one-step probe; there
is no automatic fallback to training 8B. Internal testing is withheld until a
checkpoint is selected; reserved/jury sources are excluded by the real-release
allowlist gate. The default exporter does not decode internal-test sources.

Paid execution: pending explicit handoff from steps 1–2 and fresh live lifecycle,
rate, credit, reservation and cleanup receipts under the same $30 project cap.
No provider state or resources were changed. Offline full-model compatibility,
base/adapter quality, live multi-fact scans and the upload-origin 270-second /
client-under-300-second runtime gates remain unmeasured. Optional VideoPrism is
deferred. Subsequent legal/public API/deployment work is outside this handoff.

T3 limitation: the ForteBank project was registered and the worktree opened in
Finder. This existing thread could not be reassigned: the MCP and native thread
menus have no move-project operation. Its aibar binding remains unchanged so the
labeling thread's workspace is preserved. No replacement thread/agent was started.
