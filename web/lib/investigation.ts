import type {
  Assessment,
  ReasoningResult,
  ReviewEvent,
  ReviewRevision,
} from "./review-types"

export type InvestigationFilters = {
  text: string
  participant: string
  assessment: Assessment | "all"
  review: "all" | "with_notes" | "without_notes"
  from: string
  to: string
}

export const emptyFilters: InvestigationFilters = {
  text: "",
  participant: "",
  assessment: "all",
  review: "all",
  from: "",
  to: "",
}

export function filterError(filters: InvestigationFilters): string {
  const from = filters.from === "" ? 0 : Number(filters.from)
  const to = filters.to === "" ? Infinity : Number(filters.to)
  return !Number.isFinite(from) ||
    from < 0 ||
    (filters.to !== "" && !Number.isFinite(to)) ||
    to < 0 ||
    to < from
    ? "Use nonnegative seconds, with the end at or after the start."
    : ""
}

// Retrieval changes the visible subset only. It never merges events or changes conclusions.
export function filterEvents(
  result: ReasoningResult,
  revisions: ReviewRevision[],
  filters: InvestigationFilters
): ReviewEvent[] {
  if (filterError(filters)) return []
  const terms = filters.text
    .trim()
    .toLocaleLowerCase()
    .split(/\s+/u)
    .filter(Boolean)
  const from = filters.from === "" ? 0 : Number(filters.from)
  const to = filters.to === "" ? Infinity : Number(filters.to)
  return result.events.filter((event) => {
    const notes = revisions.filter(
      (revision) => revision.target_id === event.event_id
    )
    const participants = [...event.actor_ids, ...event.recipient_ids]
    const observations = result.timeline.observations.filter((observation) =>
      event.observation_ids.includes(observation.observation_id)
    )
    const text = [
      event.event_id,
      event.kind,
      event.value,
      ...participants,
      ...event.observation_ids,
      ...event.uncertainty,
      ...observations.map((item) => item.value),
      ...notes.map((item) => item.change.note || ""),
      ...(event.legal_assessments || []).flatMap((item) => [
        item.rule_id,
        item.explanation,
      ]),
    ]
      .join(" ")
      .toLocaleLowerCase()
    return (
      terms.every((term) => text.includes(term)) &&
      (!filters.participant || participants.includes(filters.participant)) &&
      (filters.assessment === "all" ||
        event.assessment === filters.assessment) &&
      (filters.review === "all" ||
        (filters.review === "with_notes"
          ? notes.length > 0
          : notes.length === 0)) &&
      event.end_sec >= from &&
      event.start_sec <= to
    )
  })
}

export function validJobId(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    value
  )
}

// Session guards bind a principal; this gate additionally binds asynchronous history to a case/request.
export function createHistoryRequestGate() {
  let generation = 0
  let activeCase = ""
  let controller: AbortController | null = null
  return {
    invalidate() {
      generation++
      activeCase = ""
      controller?.abort()
      controller = null
    },
    begin(caseId: string) {
      controller?.abort()
      controller = new AbortController()
      activeCase = caseId
      const signal = controller.signal
      const requestGeneration = ++generation
      return {
        signal,
        current: () =>
          generation === requestGeneration &&
          activeCase === caseId &&
          !signal.aborted,
        abort: () => {
          if (generation === requestGeneration) controller?.abort()
        },
      }
    },
  }
}

export function revisionHead(revisions: ReviewRevision[]): string | null {
  if (!revisions.length) return null
  const parents = new Set(revisions.map((item) => item.parent_revision))
  const heads = revisions.filter(
    (item) => !parents.has(item.revision_id + ".json")
  )
  if (heads.length !== 1)
    throw new Error(
      "Review history has multiple heads. Reload it before saving."
    )
  return heads[0].revision_id + ".json"
}
