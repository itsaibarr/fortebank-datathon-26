/* THESIS: Source video leads a checkable review. OWN-WORLD: Selected Nova/sky/zinc,
Manrope and Geist. STORY: Upload, select an event, inspect conditions, append review.
FIRST VIEWPORT: Wide source player with chronological event rail and upload controls.
FORM: User-pinned operating workspace; original evidence and condition tabs below. */
"use client"

import { useEffect, useRef, useState } from "react"
import {
  ArrowRight,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  ExternalLink,
  FileVideo,
  Layers2,
  LoaderCircle,
  Play,
  ScanEye,
  ShieldCheck,
  Upload,
} from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import {
  DeploymentNotice,
  SignInWorkspace,
  WorkspaceHeader,
} from "@/components/review-access"
import {
  useBrowserAccess,
  type BrowserAccess,
} from "@/hooks/use-browser-access"
import { uploadsAvailable } from "@/lib/browser-session"
import {
  assessmentLabels,
  timecode,
  type Assessment,
  type LegalAssessment,
  type ReasoningResult,
  type ReviewEvent,
  type ReviewRevision,
  type SourceEvidence,
} from "@/lib/review-types"

function AssessmentBadge({ value }: { value: Assessment }) {
  return (
    <Badge
      variant={value === "supported_violation" ? "destructive" : "secondary"}
    >
      {assessmentLabels[value]}
    </Badge>
  )
}

function EvidenceImage({
  frame,
  jobId,
  request,
  onSeek,
}: {
  frame: SourceEvidence
  jobId: string
  request: BrowserAccess["request"]
  onSeek: (seconds: number) => void
}) {
  const [image, setImage] = useState("")
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl = ""
    request(
      `/api/v2/jobs/${jobId}/evidence/${encodeURIComponent(frame.frame_id)}`,
      { signal: controller.signal }
    )
      .then((response) => response.blob())
      .then((blob) => {
        if (!controller.signal.aborted) {
          objectUrl = URL.createObjectURL(blob)
          setImage(objectUrl)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [request, frame.frame_id, jobId])
  return (
    <figure className="min-w-0">
      <button
        type="button"
        className="evidence-image"
        onClick={() => onSeek(frame.timestamp_sec)}
        aria-label={`Seek source video to ${timecode(frame.timestamp_sec)}`}
      >
        {/* Authenticated local blobs intentionally bypass remote image optimization. */}
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={image}
            alt={`Original source frame at ${timecode(frame.timestamp_sec)}`}
          />
        ) : (
          <span>
            {failed ? "Evidence unavailable" : "Loading source frame…"}
          </span>
        )}
      </button>
      <figcaption className="mt-2 flex flex-wrap justify-between gap-1 text-xs text-muted-foreground">
        <span className="tabular-nums">{timecode(frame.timestamp_sec)}</span>
        <span>{frame.frame_id}</span>
      </figcaption>
    </figure>
  )
}

function LegalFindings({
  assessments,
  onSeek,
  result,
}: {
  assessments: LegalAssessment[]
  onSeek: (seconds: number) => void
  result: ReasoningResult
}) {
  function evidenceTime(id: string) {
    const observation = result.timeline.observations.find(
      (item) => item.observation_id === id
    )
    if (observation?.decisive_sec !== undefined) return observation.decisive_sec
    return (
      result.events
        .flatMap((event) => event.evidence)
        .find((frame) => frame.frame_id === id)?.timestamp_sec ??
      result.participants.source_frames?.find((frame) => frame.frame_id === id)
        ?.timestamp_sec
    )
  }
  if (!assessments.length)
    return (
      <Empty className="py-10">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <CircleHelp />
          </EmptyMedia>
          <EmptyTitle>No linked condition findings</EmptyTitle>
          <EmptyDescription>
            This observation has no source-bound legal assessment. It remains a
            review candidate.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  return (
    <div className="flex flex-col gap-8">
      {assessments.map((assessment) => (
        <section key={assessment.assessment_id} className="flex flex-col gap-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 className="text-base font-semibold">
                {assessment.rule_id.replaceAll("_", " ")}
              </h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Interpretation: {assessment.interpretation_status} · independent
                review pending
              </p>
            </div>
            <AssessmentBadge value={assessment.assessment} />
          </div>
          <p className="max-w-prose text-sm leading-relaxed">
            {assessment.explanation}
          </p>
          <div className="condition-list">
            {assessment.conditions.map((condition) => (
              <div key={condition.condition_id} className="condition-row">
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    {condition.condition_id.replaceAll("_", " ")}
                  </p>
                  {assessment.condition_specs?.find(
                    (spec) => spec.id === condition.condition_id
                  )?.proposition && (
                    <p className="mt-1 text-sm leading-relaxed">
                      {
                        assessment.condition_specs.find(
                          (spec) => spec.id === condition.condition_id
                        )?.proposition
                      }
                    </p>
                  )}
                  <p className="mt-1 text-xs text-muted-foreground">
                    {condition.unresolved_dependencies.length
                      ? condition.unresolved_dependencies.join(" · ")
                      : condition.result === "unknown"
                        ? "Required evidence remains unresolved."
                        : "See supporting source references."}
                  </p>
                  {!!condition.supporting_evidence_ids.length && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {condition.supporting_evidence_ids.map((id) => {
                        const seconds = evidenceTime(id)
                        return seconds !== undefined ? (
                          <Button
                            key={id}
                            size="xs"
                            variant="outline"
                            onClick={() => onSeek(seconds)}
                          >
                            {id}
                          </Button>
                        ) : (
                          <span
                            className="text-xs text-muted-foreground"
                            key={id}
                          >
                            {id}
                          </span>
                        )
                      })}
                    </div>
                  )}
                  {!!condition.contradictory_evidence_ids.length && (
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                      <span>Counterevidence:</span>
                      {condition.contradictory_evidence_ids.map((id) => {
                        const seconds = evidenceTime(id)
                        return seconds !== undefined ? (
                          <Button
                            key={id}
                            variant="outline"
                            size="xs"
                            onClick={() => onSeek(seconds)}
                          >
                            {id}
                          </Button>
                        ) : (
                          <span key={id}>{id}</span>
                        )
                      })}
                    </div>
                  )}
                </div>
                <Badge variant="outline">{condition.result}</Badge>
              </div>
            ))}
          </div>
          <div className="flex flex-col gap-3">
            {assessment.citations.map((source) => (
              <div key={source.provision_id}>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="source-link"
                >
                  <ShieldCheck className="size-4 shrink-0" />
                  <span className="min-w-0">
                    <span className="block font-medium">{source.title}</span>
                    <span className="mt-1 block text-xs break-all text-muted-foreground">
                      {source.provision_id} · version {source.version_id}
                    </span>
                  </span>
                  <ExternalLink className="size-3.5 shrink-0" />
                </a>
                {source.text && (
                  <details className="mt-2 px-4">
                    <summary className="cursor-pointer text-xs font-medium">
                      Exact provision from the local official snapshot
                    </summary>
                    <blockquote className="mt-3 text-sm leading-relaxed whitespace-pre-wrap">
                      {source.text}
                    </blockquote>
                  </details>
                )}
              </div>
            ))}
          </div>
          {!!assessment.limitations.length && (
            <p className="text-xs leading-relaxed text-muted-foreground">
              {assessment.limitations.join(" ")}
            </p>
          )}
        </section>
      ))}
    </div>
  )
}

export default function ReviewPage() {
  const access = useBrowserAccess()
  return access.session ? (
    <PrivateReviewWorkspace
      key={`${access.generation}/${access.session.principal.id}`}
      access={access}
    />
  ) : (
    <SignInWorkspace access={access} />
  )
}

function PrivateReviewWorkspace({ access }: { access: BrowserAccess }) {
  const { request } = access
  const uploadReady = uploadsAvailable(access.metadata)
  const [file, setFile] = useState<File | null>(null)
  const [videoUrl, setVideoUrl] = useState("")
  const [jobId, setJobId] = useState("")
  const [result, setResult] = useState<ReasoningResult | null>(null)
  const [phase, setPhase] = useState<
    "idle" | "uploading" | "processing" | "done" | "error"
  >("idle")
  const [error, setError] = useState("")
  const [selectedId, setSelectedId] = useState("")
  const [currentTime, setCurrentTime] = useState(0)
  const [mediaDuration, setMediaDuration] = useState(0)
  const [videoSize, setVideoSize] = useState<[number, number]>([16, 9])
  const [showOverlays, setShowOverlays] = useState(true)
  const [revisions, setRevisions] = useState<ReviewRevision[]>([])
  const [scope, setScope] = useState("visual")
  const [note, setNote] = useState("")
  const [reviewStatus, setReviewStatus] = useState("")
  const [saving, setSaving] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [sourceError, setSourceError] = useState("")
  const video = useRef<HTMLVideoElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const localUrl = useRef("")
  const submitting = useRef(false)
  const busy = phase === "uploading" || phase === "processing"
  const selected =
    result?.events.find((event) => event.event_id === selectedId) ||
    result?.events[0]
  const duration = result?.source.duration_sec || mediaDuration
  const selectedReviews = revisions.filter(
    (revision) => revision.target_id === selected?.event_id
  )
  const nearestFrame = result?.participants.sampled_source_frames?.reduce(
    (best, frame) =>
      !best ||
      Math.abs(frame.timestamp_sec - currentTime) <
        Math.abs(best.timestamp_sec - currentTime)
        ? frame
        : best,
    undefined as
      | ReasoningResult["participants"]["sampled_source_frames"][number]
      | undefined
  )
  const overlayBoxes =
    nearestFrame && Math.abs(nearestFrame.timestamp_sec - currentTime) <= 0.3
      ? result?.participants.frame_boxes[nearestFrame.frame_id] || {}
      : {}

  useEffect(
    () => () => {
      if (localUrl.current) URL.revokeObjectURL(localUrl.current)
    },
    []
  )
  useEffect(() => {
    if (!jobId || phase !== "processing") return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const response = await request(`/api/v2/jobs/${jobId}`, {
          signal: controller.signal,
        })
        const job = await response.json()
        if (controller.signal.aborted) return
        if (job.status === "done") {
          setResult(job.result)
          setPhase("done")
          setSelectedId(job.result.events[0]?.event_id || "")
        } else if (job.status === "failed") {
          setError(
            job.error?.message ||
              "Analysis did not complete. Retry the recording."
          )
          setPhase("error")
        } else timer = setTimeout(poll, 2000)
      } catch (failure) {
        if (!controller.signal.aborted) {
          setError(
            failure instanceof Error
              ? failure.message
              : "Connection lost. Retry the analysis."
          )
          setPhase("error")
        }
      }
    }
    poll()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [request, jobId, phase])
  useEffect(() => {
    if (!result || !jobId) return
    const controller = new AbortController()
    request(`/api/v2/jobs/${jobId}/corrections`, {
      signal: controller.signal,
    })
      .then((response) => response.json())
      .then((data) => {
        if (!controller.signal.aborted) setRevisions(data.revisions)
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setReviewStatus(
            "Review history could not be loaded. Reload it before saving a correction."
          )
      })
    return () => controller.abort()
  }, [request, jobId, result])

  useEffect(() => {
    if (!result || !jobId) return
    const controller = new AbortController()
    let sourceUrl = ""
    request(`/api/v2/jobs/${jobId}/source`, { signal: controller.signal })
      .then((response) => response.blob())
      .then((blob) => {
        if (!controller.signal.aborted) {
          sourceUrl = URL.createObjectURL(blob)
          setVideoUrl(sourceUrl)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setVideoUrl(localUrl.current)
          setSourceError(
            "Stored source could not be loaded; the selected original file remains available."
          )
        }
      })
    return () => {
      controller.abort()
      if (sourceUrl) URL.revokeObjectURL(sourceUrl)
    }
  }, [request, jobId, result])

  function chooseFile(candidate: File | undefined) {
    if (!candidate || busy || !uploadReady || !access.metadata) return
    if (!candidate.name.toLowerCase().endsWith(".mov")) {
      setError("Choose a MOV recording.")
      return
    }
    if (
      !candidate.size ||
      candidate.size + 1024 > access.metadata.limits.upload_max_bytes
    ) {
      setError(
        "Choose a nonempty MOV within this installation’s total upload limit."
      )
      return
    }
    if (localUrl.current) URL.revokeObjectURL(localUrl.current)
    localUrl.current = URL.createObjectURL(candidate)
    setFile(candidate)
    setVideoUrl(localUrl.current)
    setResult(null)
    setJobId("")
    setPhase("idle")
    setError("")
    setSourceError("")
    setRevisions([])
    setReviewStatus("")
    setCurrentTime(0)
  }
  async function analyze() {
    if (!file || !uploadReady || busy || submitting.current) return
    submitting.current = true
    setPhase("uploading")
    const metadata = await access.refreshMetadata()
    if (!uploadsAvailable(metadata) || !metadata) {
      submitting.current = false
      setPhase(result ? "done" : "idle")
      return
    }
    if (
      file.size + 1024 > metadata.limits.upload_max_bytes ||
      (mediaDuration && mediaDuration > metadata.limits.max_video_seconds)
    ) {
      setError(
        "This recording exceeds the installation’s size or duration limit."
      )
      submitting.current = false
      setPhase(result ? "done" : "idle")
      return
    }
    setPhase("uploading")
    setJobId("")
    setVideoUrl(localUrl.current)
    setError("")
    setResult(null)
    setRevisions([])
    setReviewStatus("")
    const form = new FormData()
    form.append("file", file)
    try {
      const response = await request("/api/v2/analyze", {
        method: "POST",
        body: form,
      })
      const accepted = await response.json()
      setJobId(accepted.job_id)
      setPhase("processing")
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Upload failed. Check the connection and retry."
      )
      setPhase("error")
    } finally {
      submitting.current = false
    }
  }
  function seek(seconds: number) {
    if (video.current) {
      video.current.currentTime = seconds
      setCurrentTime(seconds)
    }
  }
  function selectEvent(event: ReviewEvent) {
    setSelectedId(event.event_id)
    seek(event.start_sec)
    setNote("")
    setReviewStatus("")
  }
  async function reloadReviews() {
    const response = await request(`/api/v2/jobs/${jobId}/corrections`)
    const data = await response.json()
    setRevisions(data.revisions)
    return data.revisions as ReviewRevision[]
  }
  async function saveCorrection() {
    if (!result || !selected || !access.session || !note.trim()) return
    setSaving(true)
    setReviewStatus("")
    try {
      const parents = new Set(
        revisions.map((revision) => revision.parent_revision)
      )
      const head = revisions.find(
        (revision) => !parents.has(revision.revision_id + ".json")
      )
      const response = await request(`/api/v2/jobs/${jobId}/corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_sha256: result.source_sha256,
          parent_revision: head ? head.revision_id + ".json" : null,
          scope,
          target_id: selected.event_id,
          reviewer: access.session.principal.id,
          change: { note: note.trim() },
        }),
      })
      const saved = await response.json()
      await reloadReviews()
      setNote("")
      setReviewStatus(
        `Correction saved as ${saved.revision}. Other review scopes remain separate.`
      )
    } catch (failure) {
      setReviewStatus(
        failure instanceof Error
          ? failure.message + " Reload review history and retry."
          : "Correction could not be saved."
      )
    } finally {
      setSaving(false)
    }
  }
  const evaluatedRules =
    result?.legal.rule_coverage.filter((rule) => rule.status === "evaluated")
      .length || 0

  const uploadControls = (
    <section
      className={cn("upload-section", dragging && "is-dragging")}
      aria-labelledby="upload-title"
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault()
        setDragging(false)
        chooseFile(event.dataTransfer.files[0])
      }}
    >
      <div className="flex items-start gap-3">
        <Upload className="mt-0.5 size-5 shrink-0 text-primary" />
        <div>
          <h2 id="upload-title" className="text-sm font-semibold">
            {file ? "Recording ready" : "Add a recording"}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {file
              ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MiB`
              : uploadReady
                ? "Drop a MOV here, or choose a file within the installation limits above."
                : "Uploads are paused. Existing reviews remain available."}
          </p>
          <input
            ref={fileInput}
            id="recording"
            type="file"
            accept=".mov,video/quicktime"
            hidden
            disabled={busy || !uploadReady}
            onChange={(event) => chooseFile(event.target.files?.[0])}
            aria-label="Choose MOV recording"
          />
          <Button
            variant="link"
            size="xs"
            className="mt-2 px-0"
            disabled={busy || !uploadReady}
            onClick={() => fileInput.current?.click()}
          >
            {file ? "Choose another file" : "Browse files"}
            <ArrowRight data-icon="inline-end" />
          </Button>
        </div>
      </div>
      <div className="upload-actions">
        <Button
          size="lg"
          disabled={
            !file ||
            !uploadReady ||
            busy ||
            !!(
              access.metadata &&
              mediaDuration > access.metadata.limits.max_video_seconds
            )
          }
          onClick={analyze}
        >
          {busy ? (
            <LoaderCircle
              data-icon="inline-start"
              className="animate-spin motion-reduce:animate-none"
            />
          ) : (
            <ScanEye data-icon="inline-start" />
          )}
          {busy ? "Analyzing…" : "Analyze recording"}
        </Button>
      </div>
    </section>
  )

  return (
    <div className="min-h-screen bg-sidebar/35">
      <a href="#review-main" className="skip-link">
        Skip to review workspace
      </a>
      <WorkspaceHeader access={access} />
      <main
        id="review-main"
        className={cn("workspace-main", result && "has-result")}
      >
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm text-muted-foreground">
              Cash operation review
            </p>
            <h1 className="mt-2 font-heading text-3xl font-semibold tracking-tight sm:text-4xl">
              Follow the evidence.
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
              Review visible actions, the people involved, and the conditions of
              official Kazakhstan provisions.
            </p>
          </div>
          {result && (
            <div className="flex flex-col items-start gap-2 sm:items-end">
              <AssessmentBadge value={result.assessment} />
              <span className="text-xs text-muted-foreground">
                {result.execution.status === "partial"
                  ? "Partial analysis"
                  : "Analysis completed"}{" "}
                · human review pending
              </span>
            </div>
          )}
        </div>
        <DeploymentNotice access={access} />
        {error && (
          <Alert variant="destructive">
            <CircleHelp />
            <AlertTitle>Analysis needs attention</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <p
          className="sr-only"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          {phase === "done" && result
            ? `Analysis finished. ${assessmentLabels[result.assessment]}. ${result.events.length} source-bound events.`
            : phase === "error"
              ? `Analysis needs attention. ${error}`
              : busy
                ? "Recording analysis is in progress."
                : "Ready to add a recording."}
        </p>
        {phase === "error" && jobId && (
          <Button
            variant="outline"
            onClick={() => {
              setError("")
              setPhase("processing")
            }}
          >
            Retry job status
          </Button>
        )}

        {!result && uploadControls}

        <div className="review-grid">
          <section className="min-w-0" aria-label="Original recording">
            <div className="player-toolbar">
              <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
                <FileVideo className="size-4 shrink-0" />
                <span className="truncate">
                  {file?.name || "Original recording"}
                </span>
              </span>
              <Badge variant="secondary">
                {result ? timecode(duration) : "MOV"}
              </Badge>
            </div>
            <div className="source-player">
              {videoUrl ? (
                <>
                  <video
                    ref={video}
                    src={videoUrl}
                    controls
                    playsInline
                    preload="metadata"
                    className="source-video"
                    onTimeUpdate={(event) =>
                      setCurrentTime(event.currentTarget.currentTime)
                    }
                    onLoadedMetadata={(event) => {
                      setVideoSize([
                        event.currentTarget.videoWidth,
                        event.currentTarget.videoHeight,
                      ])
                      setMediaDuration(
                        Number.isFinite(event.currentTarget.duration)
                          ? event.currentTarget.duration
                          : 0
                      )
                    }}
                    onError={() =>
                      setSourceError(
                        "This browser cannot preview this MOV codec. Analysis can still use the original source."
                      )
                    }
                    aria-label="Original source video"
                  >
                    <track kind="captions" />
                  </video>
                  {result &&
                    showOverlays &&
                    !!Object.keys(overlayBoxes).length && (
                      <svg
                        className="participant-overlay"
                        viewBox={`0 0 ${videoSize[0]} ${videoSize[1]}`}
                        aria-label="Proposed anonymous participant boxes"
                      >
                        {Object.entries(overlayBoxes).map(([id, box]) => {
                          const normalized =
                            result.participants.box_coordinate_space ===
                            "oriented_normalized_xyxy"
                          const [x1, y1, x2, y2] = box.map((v, index) =>
                            normalized ? v * videoSize[index % 2] : v
                          )
                          return (
                            <g key={id}>
                              <rect
                                x={x1}
                                y={y1}
                                width={x2 - x1}
                                height={y2 - y1}
                                fill="none"
                                stroke="currentColor"
                                strokeWidth={Math.max(2, videoSize[0] / 500)}
                              />
                              <text
                                x={x1 + 4}
                                y={Math.max(18, y1 - 6)}
                                fontSize={Math.max(14, videoSize[0] / 60)}
                                fill="currentColor"
                                stroke="var(--background)"
                                strokeWidth=".5"
                              >
                                {id} · proposal
                              </text>
                            </g>
                          )
                        })}
                      </svg>
                    )}
                </>
              ) : (
                <Empty className="h-full border-0">
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <FileVideo />
                    </EmptyMedia>
                    <EmptyTitle>Your recording, in context</EmptyTitle>
                    <EmptyDescription>
                      Add a MOV to inspect the original video and its
                      timestamped evidence.
                    </EmptyDescription>
                  </EmptyHeader>
                  <Button
                    variant="outline"
                    onClick={() => fileInput.current?.click()}
                    disabled={!uploadReady}
                  >
                    <Upload data-icon="inline-start" />
                    Choose recording
                  </Button>
                </Empty>
              )}
            </div>
            {sourceError && (
              <p role="status" className="mt-2 text-xs text-muted-foreground">
                {sourceError}
              </p>
            )}
            <div className="player-footer">
              <span className="text-xs text-muted-foreground tabular-nums">
                {timecode(currentTime)} / {duration ? timecode(duration) : "—"}
              </span>
              <Field orientation="horizontal" className="w-auto">
                <Layers2 className="size-3.5 text-muted-foreground" />
                <FieldLabel htmlFor="overlays">
                  Participant proposals
                </FieldLabel>
                <Switch
                  id="overlays"
                  size="sm"
                  checked={showOverlays}
                  onCheckedChange={setShowOverlays}
                  disabled={!result}
                />
              </Field>
            </div>
            {result && (
              <div
                className="recording-timeline"
                aria-label="Event positions on the source timeline"
              >
                <div className="timeline-axis" />
                {result.events.map((event, index) => (
                  <button
                    key={event.event_id}
                    type="button"
                    className={cn(
                      "timeline-marker",
                      selected?.event_id === event.event_id && "is-selected"
                    )}
                    style={{
                      left: `${Math.max(1, Math.min(98, (event.decisive_sec / duration) * 100))}%`,
                    }}
                    onClick={() => selectEvent(event)}
                    aria-label={`Event ${index + 1} at ${timecode(event.decisive_sec)}`}
                    aria-pressed={selected?.event_id === event.event_id}
                  >
                    {index + 1}
                  </button>
                ))}
                <span className="timeline-start tabular-nums">00:00</span>
                <span className="timeline-end tabular-nums">
                  {timecode(duration)}
                </span>
              </div>
            )}
          </section>
          <aside className="event-rail" aria-label="Recording events">
            <div className="rail-heading">
              <h2 className="text-base font-semibold">Events</h2>
              <Badge variant="secondary">{result?.events.length || 0}</Badge>
            </div>
            {busy ? (
              <div
                className="flex flex-col gap-5 px-5 py-10"
                role="status"
                aria-live="polite"
              >
                <LoaderCircle className="size-6 animate-spin text-primary motion-reduce:animate-none" />
                <div>
                  <h3 className="font-medium">
                    {phase === "uploading"
                      ? "Uploading recording"
                      : "Reviewing the recording"}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {phase === "uploading"
                      ? "Transferring the original file to the installation shown above."
                      : "Participants, timeline observations and official rule conditions are being checked."}
                  </p>
                </div>
                <p className="text-xs text-muted-foreground">
                  Results will appear here when the job finishes.
                </p>
              </div>
            ) : result?.events.length ? (
              <ol className="event-list">
                {result.events.map((event, index) => (
                  <li key={event.event_id}>
                    <button
                      type="button"
                      onClick={() => selectEvent(event)}
                      className={cn(
                        "event-item",
                        selected?.event_id === event.event_id && "is-selected"
                      )}
                      aria-current={
                        selected?.event_id === event.event_id
                          ? "true"
                          : undefined
                      }
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="event-number">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {timecode(event.start_sec)}–{timecode(event.end_sec)}
                        </span>
                        <ChevronRight className="size-4 text-muted-foreground" />
                      </span>
                      <span className="mt-3 block text-sm leading-relaxed font-medium">
                        {event.value}
                      </span>
                      <span className="mt-3 flex flex-wrap items-center gap-2">
                        <Badge variant="outline">
                          {event.actor_ids.join(", ") || "Unresolved actor"}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {assessmentLabels[event.assessment]}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            ) : (
              <Empty className="border-0 px-5 py-12">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <Clock3 />
                  </EmptyMedia>
                  <EmptyTitle>
                    {result
                      ? "No grounded event markers"
                      : "A timeline will appear here"}
                  </EmptyTitle>
                  <EmptyDescription>
                    {result
                      ? "No event was established from the available evidence. This does not clear the recording."
                      : "Select an event to seek the video and inspect its evidence."}
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            )}
            {result && (
              <div className="rail-footnote">
                {evaluatedRules} of {result.legal.rule_coverage.length} scoped
                rules evaluated. Sparse frames do not establish absence.
              </div>
            )}
          </aside>
        </div>

        {result && (
          <section
            className="result-details"
            aria-label="Selected evidence and condition findings"
          >
            <div className="detail-summary">
              <div>
                <p className="text-xs text-muted-foreground">
                  {selected ? "Selected event" : "Recording assessment"}
                </p>
                <h2 className="mt-2 text-xl font-semibold">
                  {selected
                    ? selected.value
                    : assessmentLabels[result.assessment]}
                </h2>
                {selected && (
                  <p className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                    <span className="tabular-nums">
                      {timecode(selected.start_sec)}–
                      {timecode(selected.end_sec)}
                    </span>
                    <span>
                      {selected.actor_ids.join(", ") || "Actor unresolved"}
                    </span>
                    <span>Source evidence envelope</span>
                  </p>
                )}
              </div>
              {selected && (
                <Button
                  variant="outline"
                  onClick={() => seek(selected.start_sec)}
                >
                  <Play data-icon="inline-start" />
                  Go to event
                </Button>
              )}
            </div>
            <Tabs defaultValue="evidence" className="mt-6">
              <TabsList variant="line" className="max-w-full">
                <TabsTrigger value="evidence">Source evidence</TabsTrigger>
                <TabsTrigger value="conditions">Rule conditions</TabsTrigger>
                <TabsTrigger value="review">Human review</TabsTrigger>
              </TabsList>
              <Separator className="mt-2" />
              <TabsContent value="evidence" className="pt-5">
                {selected?.evidence.length ? (
                  <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                    {selected.evidence.map((frame) => (
                      <EvidenceImage
                        key={`${jobId}/${frame.frame_id}`}
                        frame={frame}
                        jobId={jobId}
                        request={request}
                        onSeek={seek}
                      />
                    ))}
                  </div>
                ) : (
                  <Empty>
                    <EmptyHeader>
                      <EmptyTitle>No source frames selected</EmptyTitle>
                      <EmptyDescription>
                        The available analysis did not establish source-bound
                        event evidence.
                      </EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                )}
                {selected && (
                  <p className="mt-5 text-xs leading-relaxed text-muted-foreground">
                    Original decoded frames. Participant overlays are separate.
                    These timestamps identify source samples; the action may
                    begin or end between samples.
                  </p>
                )}
                {!!selected?.uncertainty.length && (
                  <Alert className="mt-5">
                    <CircleHelp />
                    <AlertTitle>Unresolved evidence</AlertTitle>
                    <AlertDescription>
                      {selected.uncertainty.join(" ")}
                    </AlertDescription>
                  </Alert>
                )}
              </TabsContent>
              <TabsContent value="conditions" className="pt-5">
                <LegalFindings
                  assessments={
                    selected
                      ? selected.legal_assessments || []
                      : result.legal.assessments
                  }
                  onSeek={seek}
                  result={result}
                />
                {!!selected && (
                  <details className="mt-6">
                    <summary className="cursor-pointer text-sm font-medium">
                      All recording condition findings (
                      {result.legal.assessments.length})
                    </summary>
                    <div className="mt-5">
                      <LegalFindings
                        assessments={result.legal.assessments}
                        onSeek={seek}
                        result={result}
                      />
                    </div>
                  </details>
                )}
                <details className="mt-6">
                  <summary className="cursor-pointer text-sm font-medium">
                    Complete scoped rule coverage (
                    {result.legal.rule_coverage.length})
                  </summary>
                  <div className="condition-list mt-4">
                    {result.legal.rule_coverage.map((rule) => (
                      <div className="condition-row" key={rule.rule_id}>
                        <span className="text-sm">
                          {rule.rule_id.replaceAll("_", " ")}
                          {rule.reason && (
                            <span className="mt-1 block text-xs text-muted-foreground">
                              {rule.reason}
                            </span>
                          )}
                        </span>
                        <Badge variant="outline">
                          {rule.status.replaceAll("_", " ")}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </details>
              </TabsContent>
              <TabsContent value="review" className="pt-5">
                <div className="grid gap-10 lg:grid-cols-2">
                  <div>
                    <h3 className="text-base font-semibold">
                      Append a scoped correction
                    </h3>
                    <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted-foreground">
                      Your correction preserves the original proposal and
                      previous revisions. A role correction does not approve
                      geometry or legal conclusions.
                    </p>
                    {selected ? (
                      <FieldGroup className="mt-5">
                        <p className="text-sm text-muted-foreground">
                          Saved as {access.session?.principal.username}.
                          Attribution comes from your authenticated session.
                        </p>
                        <Field>
                          <FieldLabel htmlFor="review-scope">
                            Review scope
                          </FieldLabel>
                          <select
                            id="review-scope"
                            className="native-select"
                            value={scope}
                            onChange={(event) => setScope(event.target.value)}
                          >
                            <option value="visual">Visible facts</option>
                            <option value="identity">
                              Participant continuity
                            </option>
                            <option value="geometry">Boxes and geometry</option>
                            <option value="role">Role assignment</option>
                            <option value="legal">Legal assessment</option>
                          </select>
                        </Field>
                        <Field>
                          <FieldLabel htmlFor="correction-note">
                            Correction for {selected.event_id}
                          </FieldLabel>
                          <Textarea
                            id="correction-note"
                            value={note}
                            maxLength={12000}
                            onChange={(event) => setNote(event.target.value)}
                            placeholder="Describe the correction and the source frames supporting it."
                          />
                        </Field>
                        <div className="flex flex-wrap gap-3">
                          <Button
                            disabled={saving || !access.session || !note.trim()}
                            onClick={saveCorrection}
                          >
                            {saving ? (
                              <LoaderCircle
                                data-icon="inline-start"
                                className="animate-spin motion-reduce:animate-none"
                              />
                            ) : (
                              <Check data-icon="inline-start" />
                            )}
                            Save correction
                          </Button>
                          <Button
                            variant="outline"
                            disabled={saving}
                            onClick={() =>
                              reloadReviews()
                                .then(() =>
                                  setReviewStatus("Review history reloaded.")
                                )
                                .catch(() =>
                                  setReviewStatus(
                                    "Review history could not be loaded."
                                  )
                                )
                            }
                          >
                            Reload history
                          </Button>
                        </div>
                      </FieldGroup>
                    ) : (
                      <p className="mt-4 text-sm text-muted-foreground">
                        Select a source-bound event before adding an event
                        correction.
                      </p>
                    )}
                    {!!reviewStatus && (
                      <p className="mt-4 text-sm break-words" role="status">
                        {reviewStatus}
                      </p>
                    )}
                  </div>
                  <div>
                    <h3 className="text-base font-semibold">
                      Correction history
                    </h3>
                    <p className="mt-2 text-xs text-muted-foreground">
                      {selectedReviews.length} revisions for this event ·{" "}
                      {revisions.length} in this recording
                    </p>
                    {selectedReviews.length ? (
                      <ol className="mt-5 flex flex-col gap-5">
                        {[...selectedReviews]
                          .sort(
                            (a, b) => b.created_unix_sec - a.created_unix_sec
                          )
                          .map((revision) => (
                            <li
                              key={revision.revision_id}
                              className="review-revision"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <span className="text-sm font-medium">
                                  {revision.reviewer}
                                </span>
                                <Badge variant="outline">
                                  {revision.scope}
                                </Badge>
                              </div>
                              <p className="mt-2 text-sm leading-relaxed whitespace-pre-wrap">
                                {revision.change.note ||
                                  "Structured correction saved."}
                              </p>
                              <p className="mt-2 text-xs break-all text-muted-foreground">
                                {revision.revision_id}.json
                              </p>
                            </li>
                          ))}
                      </ol>
                    ) : (
                      <Empty className="mt-5">
                        <EmptyHeader>
                          <EmptyTitle>No corrections yet</EmptyTitle>
                          <EmptyDescription>
                            Independent review has not been recorded for this
                            event.
                          </EmptyDescription>
                        </EmptyHeader>
                      </Empty>
                    )}
                  </div>
                </div>
              </TabsContent>
            </Tabs>
            <Separator className="my-6" />
            <details>
              <summary className="cursor-pointer text-sm font-medium">
                Coverage and limitations
              </summary>
              <div className="mt-4 flex flex-col gap-3 text-sm leading-relaxed text-muted-foreground">
                <p>
                  {result.timeline.coverage.unexamined_intervals.length}{" "}
                  unexamined intervals ·{" "}
                  {result.timeline.coverage.unclear_intervals.length} unclear
                  intervals · {result.timeline.coverage.pending_reinspections}{" "}
                  pending reinspections.
                </p>
                <ul className="flex list-disc flex-col gap-2 pl-5">
                  {[
                    ...result.timeline.unresolved_questions,
                    ...result.limitations,
                  ].map((limitation, index) => (
                    <li key={index}>{limitation}</li>
                  ))}
                </ul>
                <p className="text-xs break-all">
                  Source SHA256: {result.source_sha256}
                </p>
              </div>
            </details>
          </section>
        )}
        {result && uploadControls}

        <footer className="workspace-footer">
          <span>ForteBank Datathon 26</span>
          <span>
            Frozen inference · source-bound evidence · independent review
          </span>
        </footer>
      </main>
    </div>
  )
}
