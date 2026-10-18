export type Assessment =
  | "supported_violation"
  | "no_violation_observed"
  | "insufficient_evidence"
  | "not_applicable"

export type SourceEvidence = {
  frame_id: string
  timestamp_sec: number
  source_pts: number
  time_base: string
}

export type LegalAssessment = {
  assessment_id: string
  rule_id: string
  assessment: Assessment
  interpretation_status: string
  explanation: string
  participant_ids: string[]
  conditions: {
    condition_id: string
    result: "satisfied" | "contradicted" | "unknown"
    supporting_evidence_ids: string[]
    contradictory_evidence_ids: string[]
    unresolved_dependencies: string[]
  }[]
  condition_specs?: { id: string; proposition: string }[]
  citations: {
    provision_id: string
    title: string
    url: string
    version_id: string
    text?: string
  }[]
  limitations: string[]
}

export type ReviewEvent = {
  event_id: string
  kind: string
  value: string
  start_sec: number
  end_sec: number
  decisive_sec: number
  actor_ids: string[]
  recipient_ids: string[]
  evidence: SourceEvidence[]
  observation_ids: string[]
  uncertainty: string[]
  assessment: Assessment
  legal_assessments?: LegalAssessment[]
  evidence_export_complete: boolean
}

export type ReasoningResult = {
  schema_version: "forte.reasoning/1"
  source_sha256: string
  assessment: Assessment
  execution: { status: "completed" | "partial"; budget_exhausted: boolean }
  source: { duration_sec: number; original_name: string; frame_count: number }
  events: ReviewEvent[]
  timeline: {
    observations: {
      observation_id: string
      value: string
      actor_ids?: string[]
      recipient_ids?: string[]
      evidence_frame_ids?: string[]
      contradictory_frame_ids?: string[]
      visibility?: "visible_samples" | "partly_occluded" | "unclear"
      uncertainty?: string[]
      decisive_sec?: number
    }[]
    coverage: {
      unexamined_intervals: [number, number][]
      unclear_intervals: [number, number][]
      pending_reinspections: number
    }
    unresolved_questions: string[]
  }
  participants: {
    box_coordinate_space?: string
    participants: { participant_id: string; identity_status?: string }[]
    frame_boxes: Record<
      string,
      Record<string, [number, number, number, number]>
    >
    sampled_source_frames: {
      frame_id: string
      timestamp_sec: number
      oriented_dimensions: [number, number]
    }[]
    source_frames?: { frame_id: string; timestamp_sec: number }[]
  }
  legal: {
    assessments: LegalAssessment[]
    rule_coverage: { rule_id: string; status: string; reason?: string }[]
  }
  limitations: string[]
  metrics: { total_seconds: number }
}

export type ReviewRevision = {
  schema_version?: string
  source_sha256?: string
  base_result_sha256?: string
  origin?: string
  other_scopes_approved?: boolean
  revision_id: string
  parent_revision: string | null
  target_id: string
  scope: string
  reviewer: string
  change: { note?: string; [key: string]: unknown }
  created_unix_sec: number
}

export const assessmentLabels: Record<Assessment, string> = {
  supported_violation: "Evidence-supported concern",
  no_violation_observed: "No violation observed",
  insufficient_evidence: "Insufficient evidence",
  not_applicable: "Not applicable",
}

export function timecode(seconds: number) {
  const value = Math.max(0, seconds)
  return `${Math.floor(value / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(value % 60)
    .toString()
    .padStart(2, "0")}.${Math.floor((value % 1) * 10)}`
}
