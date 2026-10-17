/** Public session/deployment contracts. Service credentials never enter this bundle. */
export type BrowserSession = {
  authenticated: true
  principal: { id: string; username: string }
  csrf_token: string
  expires_at: number
}

export type DeploymentMetadata = {
  schema_version: "forte.deployment/1"
  mode: "private" | "hosted"
  auth_mode: "browser_session"
  destination: string
  browser_uploads_enabled: boolean
  ready: boolean
  retention: "manual"
  training_enabled: false
  limits: {
    upload_max_bytes: number
    max_video_seconds: number
    upload_timeout_seconds: number
    job_timeout_seconds: number
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

export function parseSession(
  value: unknown,
  now = Date.now() / 1000
): BrowserSession | null {
  if (!record(value))
    throw new Error(
      "The session response could not be verified. Sign in again."
    )
  if (value.authenticated === false) return null
  if (
    value.authenticated !== true ||
    !record(value.principal) ||
    typeof value.principal.id !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$/.test(value.principal.id) ||
    typeof value.principal.username !== "string" ||
    !value.principal.username.trim() ||
    value.principal.username.length > 128 ||
    /[\u0000-\u001f\u007f]/.test(value.principal.username) ||
    typeof value.csrf_token !== "string" ||
    !/^[A-Za-z0-9_-]{32,256}$/.test(value.csrf_token) ||
    typeof value.expires_at !== "number" ||
    !Number.isFinite(value.expires_at) ||
    value.expires_at <= now
  )
    throw new Error(
      "Your session has ended or could not be verified. Sign in again."
    )
  return value as BrowserSession
}

export function parseDeployment(
  value: unknown,
  origin: string
): DeploymentMetadata {
  if (
    !record(value) ||
    value.schema_version !== "forte.deployment/1" ||
    (value.mode !== "private" && value.mode !== "hosted") ||
    value.auth_mode !== "browser_session" ||
    value.destination !== origin ||
    !origin.startsWith("https://") ||
    typeof value.browser_uploads_enabled !== "boolean" ||
    typeof value.ready !== "boolean" ||
    value.retention !== "manual" ||
    value.training_enabled !== false ||
    !record(value.limits)
  )
    throw new Error(
      "Deployment details could not be verified. Uploads are unavailable; ask your administrator to check this address."
    )
  const maxima = {
    upload_max_bytes: 256 * 1024 * 1024,
    max_video_seconds: 180,
    upload_timeout_seconds: 30,
    job_timeout_seconds: 270,
  }
  for (const [key, maximum] of Object.entries(maxima)) {
    const limit = value.limits[key]
    if (
      typeof limit !== "number" ||
      !Number.isInteger(limit) ||
      limit <= 0 ||
      limit > maximum
    ) {
      throw new Error(
        "The recording limits could not be verified. Uploads are unavailable."
      )
    }
  }
  return value as DeploymentMetadata
}

export function uploadsAvailable(metadata: DeploymentMetadata | null) {
  return metadata?.ready === true && metadata.browser_uploads_enabled === true
}

export class SessionEnded extends Error {
  constructor() {
    super(
      "Your session has ended. Sign in again; the private review was cleared."
    )
    this.name = "SessionEnded"
  }
}

/** Reject private bytes that finish arriving after this session was invalidated. */
export function guardSessionResponse(
  response: Response,
  valid: () => boolean,
  release: () => void
) {
  const reader = response.body?.getReader()
  let released = false
  function cleanup() {
    if (!released) {
      released = true
      release()
    }
  }
  function requireCurrent() {
    if (!valid()) {
      void reader?.cancel().catch(() => {})
      throw new SessionEnded()
    }
  }
  if (!reader) {
    try {
      requireCurrent()
      return response
    } finally {
      cleanup()
    }
  }
  const body = new ReadableStream<Uint8Array>({
    async pull(stream) {
      try {
        requireCurrent()
        const chunk = await reader.read()
        requireCurrent()
        if (chunk.done) {
          cleanup()
          stream.close()
        } else stream.enqueue(chunk.value)
      } catch (failure) {
        cleanup()
        stream.error(valid() ? failure : new SessionEnded())
      }
    },
    cancel(reason) {
      cleanup()
      return reader.cancel(reason)
    },
  })
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  })
}
