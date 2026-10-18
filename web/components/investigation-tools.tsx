"use client"

import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { assessmentLabels, type ReasoningResult } from "@/lib/review-types"
import {
  emptyFilters,
  filterError,
  type InvestigationFilters,
} from "@/lib/investigation"

export function InvestigationTools({
  result,
  filters,
  onChange,
  count,
  historyReady,
  disabled,
}: {
  result: ReasoningResult
  filters: InvestigationFilters
  onChange: (filters: InvestigationFilters) => void
  count: number
  historyReady: boolean
  disabled: boolean
}) {
  const participants = Array.from(
    new Set(
      result.events.flatMap((event) => [
        ...event.actor_ids,
        ...event.recipient_ids,
      ])
    )
  ).sort()
  const error = filterError(filters)
  return (
    <details className="border-b px-5 py-4">
      <summary className="cursor-pointer text-sm font-medium">
        Investigate this recording
      </summary>
      <fieldset
        className="mt-4 flex min-w-0 flex-col gap-4"
        disabled={disabled}
      >
        <Field>
          <FieldLabel htmlFor="event-search">
            Search events and review notes
          </FieldLabel>
          <Input
            id="event-search"
            type="search"
            maxLength={500}
            value={filters.text}
            onChange={(event) =>
              onChange({ ...filters, text: event.target.value })
            }
            placeholder="Words, event or participant ID"
          />
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="participant-filter">Participant</FieldLabel>
            <select
              id="participant-filter"
              className="native-select"
              value={filters.participant}
              onChange={(event) =>
                onChange({ ...filters, participant: event.target.value })
              }
            >
              <option value="">All participants</option>
              {participants.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </Field>
          <Field>
            <FieldLabel htmlFor="assessment-filter">Assessment</FieldLabel>
            <select
              id="assessment-filter"
              className="native-select"
              value={filters.assessment}
              onChange={(event) =>
                onChange({
                  ...filters,
                  assessment: event.target
                    .value as InvestigationFilters["assessment"],
                })
              }
            >
              <option value="all">All assessments</option>
              {Object.entries(assessmentLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field>
            <FieldLabel htmlFor="event-from">From second</FieldLabel>
            <Input
              id="event-from"
              type="number"
              min="0"
              step="0.1"
              value={filters.from}
              aria-invalid={!!error}
              aria-describedby={error ? "event-time-error" : undefined}
              onChange={(event) =>
                onChange({ ...filters, from: event.target.value })
              }
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="event-to">Through second</FieldLabel>
            <Input
              id="event-to"
              type="number"
              min="0"
              step="0.1"
              value={filters.to}
              aria-invalid={!!error}
              aria-describedby={error ? "event-time-error" : undefined}
              onChange={(event) =>
                onChange({ ...filters, to: event.target.value })
              }
            />
          </Field>
        </div>
        <Field>
          <FieldLabel htmlFor="review-filter">Review records</FieldLabel>
          <select
            id="review-filter"
            className="native-select"
            value={filters.review}
            disabled={!historyReady}
            onChange={(event) =>
              onChange({
                ...filters,
                review: event.target.value as InvestigationFilters["review"],
              })
            }
          >
            <option value="all">All events</option>
            <option value="with_notes">With saved corrections</option>
            <option value="without_notes">Without saved corrections</option>
          </select>
        </Field>
        {error && (
          <p
            id="event-time-error"
            role="alert"
            className="text-sm text-destructive"
          >
            {error}
          </p>
        )}
        {!historyReady && (
          <p role="status" className="text-xs text-muted-foreground">
            Review history is loading or unavailable. Saved notes are not
            included in search yet.
          </p>
        )}
        <div className="flex items-center justify-between gap-3">
          <p role="status" className="text-xs text-muted-foreground">
            {count} of {result.events.length} events shown
          </p>
          <Button
            size="xs"
            variant="outline"
            onClick={() => onChange({ ...emptyFilters })}
          >
            Clear filters
          </Button>
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Local word matching within this recording. A match is a review
          candidate. Notes do not approve an event. The report retains every
          event and all coverage limits.
        </p>
      </fieldset>
    </details>
  )
}
