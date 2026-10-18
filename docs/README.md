# Engineering documentation index

The sole architecture authority is [report.md](../report.md). Start with the
[project README](../README.md), [specification](../SPEC.md) and [remaining tasks](../tasks/todo.md).
The [jury guide source](../docs-site/introduction.mdx) explains the same frozen
8B → CPU Laya → deterministic pipeline.

- [Runtime/API](backend.md), [visual timeline](timeline-inference.md), [legal conditions](legal-reasoning.md)
- [Frozen tracking](frozen-tracking.md), [independent human review](person-tracking.md), [saved review format](review-packet-format.md)
- [Browser sessions](browser-session-plan.md), [offline transport](offline-api-bridge.md)
- [Case acceptance](case-requirements.md), [legal review](legal-and-annotation.md), [official corpus](../legal/README.md)
- [Consolidation inventory](cleanup-inventory.md)

Historical receipts under `.context/verify/` and `web/qa/` retain their original
source/model identity. Superseded guides remain recoverable in Git; they are not
current runtime instructions. Private data and review artifacts stay outside Git.
