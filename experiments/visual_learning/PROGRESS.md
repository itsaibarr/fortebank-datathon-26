# Visual learning workstream

Base: bd3b32f (handoff), following research 3e155bf and track contracts 292c305.
Branch: experiment/visual-learning; isolated product worktree.
Ownership: only experiments/visual_learning. Producer checkout remains untouched.

- Release reader, conservative producer TrackManifest v1 adapter, snapshot integrity,
  source-bound exporter and synthetic fixtures implemented and tested.
- Benchmark, scanner and training wiring are separate implementation slices.
- Real producer completed-export envelope not received: release compatibility is
  provisional. Synthetic contracts do not establish real actor correctness.
- Gate A, Gate B, selected training model and GPU resource ownership remain pending.
- No VM allocated, private frames inspected remotely or full model training run.
- T3 product project registered. Existing T3 thread still belongs to aibar because
  neither its MCP nor inspected UI offers per-thread project reassignment. Do not
  change the shared aibar project root: another workstream uses that workspace.
