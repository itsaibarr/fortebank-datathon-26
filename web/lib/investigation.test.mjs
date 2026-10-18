import assert from "node:assert/strict"
import { test } from "node:test"
import {
  emptyFilters,
  filterError,
  filterEvents,
  revisionHead,
  validJobId,
} from "./investigation.ts"

// Synthetic source-linked records only. Adjacent events remain distinct even at one timestamp.
const events = [
  {
    event_id: "event-a",
    kind: "object_transfer",
    value: "Observed handover",
    start_sec: 0,
    end_sec: 2,
    decisive_sec: 0,
    actor_ids: ["p1"],
    recipient_ids: ["p2"],
    observation_ids: ["o1"],
    uncertainty: ["Object unresolved"],
    assessment: "insufficient_evidence",
    evidence: [
      {
        frame_id: "f0",
        timestamp_sec: 0,
        source_pts: 1200,
        time_base: "1/600",
      },
    ],
  },
  {
    event_id: "event-b",
    kind: "object_transfer",
    value: "Observed handover",
    start_sec: 2,
    end_sec: 4,
    decisive_sec: 2,
    actor_ids: ["p3"],
    recipient_ids: ["p2"],
    observation_ids: ["o2"],
    uncertainty: [],
    assessment: "no_violation_observed",
    evidence: [],
  },
]
const result = {
  events,
  timeline: {
    observations: [
      { observation_id: "o1", value: "Synthetic uncertain observation" },
      { observation_id: "o2", value: "Synthetic second observation" },
    ],
    coverage: {
      unexamined_intervals: [[4, 10]],
      unclear_intervals: [[0, 2]],
      pending_reinspections: 1,
    },
  },
}
const revisions = [
  {
    revision_id: "child",
    parent_revision: "parent.json",
    target_id: "event-a",
    scope: "visual",
    change: { note: "Check supporting context" },
  },
  {
    revision_id: "parent",
    parent_revision: null,
    target_id: "event-b",
    scope: "role",
    change: { note: "Role remains a hypothesis" },
  },
]

test("combined lexical participant and assessment scope keeps original event and uncertainty", () => {
  const original = structuredClone(result)
  const found = filterEvents(result, revisions, {
    ...emptyFilters,
    text: "uncertain CONTEXT",
    participant: "p2",
    assessment: "insufficient_evidence",
  })
  assert.deepEqual(found, [events[0]])
  assert.equal(found[0], events[0])
  assert.deepEqual(result, original)
  assert.equal(found[0].evidence[0].source_pts, 1200)
})

test("interval overlap is inclusive and zero remains an actual source boundary", () => {
  assert.deepEqual(
    filterEvents(result, revisions, { ...emptyFilters, from: "0", to: "0" }),
    [events[0]]
  )
  assert.deepEqual(
    filterEvents(result, revisions, { ...emptyFilters, from: "2", to: "2" }),
    events
  )
  assert.deepEqual(
    filterEvents(result, revisions, { ...emptyFilters, participant: "p3" }),
    [events[1]]
  )
})

test("no matches never mutates full result, adjacent actors or coverage", () => {
  assert.deepEqual(
    filterEvents(result, revisions, { ...emptyFilters, text: "absent-word" }),
    []
  )
  assert.equal(result.events.length, 2)
  assert.deepEqual(result.timeline.coverage.unexamined_intervals, [[4, 10]])
  assert.equal(result.timeline.coverage.pending_reinspections, 1)
})

test("review presence describes sidecars without changing event assessments", () => {
  assert.deepEqual(
    filterEvents(result, [revisions[0]], {
      ...emptyFilters,
      review: "with_notes",
    }),
    [events[0]]
  )
  assert.deepEqual(
    filterEvents(result, [revisions[0]], {
      ...emptyFilters,
      review: "without_notes",
    }),
    [events[1]]
  )
  assert.equal(events[0].assessment, "insufficient_evidence")
})

test("invalid time input is explicit, never interpreted as a clean result", () => {
  for (const values of [
    { from: "-1" },
    { from: "NaN" },
    { to: "Infinity" },
    { from: "3", to: "2" },
  ]) {
    const filters = { ...emptyFilters, ...values }
    assert.ok(filterError(filters))
    assert.deepEqual(filterEvents(result, revisions, filters), [])
  }
  assert.equal(filterError(emptyFilters), "")
})

test("correction parent follows the global ancestry rather than UUID or event order", () => {
  assert.equal(revisionHead(revisions), "child.json")
  assert.equal(revisionHead([]), null)
  assert.throws(
    () =>
      revisionHead([
        { revision_id: "a", parent_revision: null },
        { revision_id: "b", parent_revision: null },
      ]),
    /multiple heads/
  )
})

test("resume accepts only a full job UUID, never a URL or route", () => {
  assert.equal(validJobId("12345678-1234-1234-1234-123456789abc"), true)
  for (const value of ["../source", "https://other.invalid", "12345678", ""])
    assert.equal(validJobId(value), false)
})
