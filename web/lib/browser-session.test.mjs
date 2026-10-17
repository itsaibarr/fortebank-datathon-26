import assert from "node:assert/strict"
import { test } from "node:test"
import {
  guardSessionResponse,
  parseDeployment,
  parseSession,
  uploadsAvailable,
} from "./browser-session.ts"

const origin = "https://review.example.invalid"
const metadata = {
  schema_version: "forte.deployment/1",
  mode: "private",
  auth_mode: "browser_session",
  destination: origin,
  browser_uploads_enabled: true,
  ready: true,
  retention: "manual",
  training_enabled: false,
  limits: {
    upload_max_bytes: 268435456,
    max_video_seconds: 180,
    upload_timeout_seconds: 30,
    job_timeout_seconds: 270,
  },
}
const session = {
  authenticated: true,
  principal: { id: "p-synthetic", username: "Synthetic reviewer" },
  csrf_token: "a".repeat(43),
  expires_at: 2000,
}

test("only exact supported HTTPS deployment metadata permits uploads", () => {
  assert.equal(uploadsAvailable(parseDeployment(metadata, origin)), true)
  for (const change of [
    { destination: "https://another.example.invalid" },
    { destination: origin + "/" },
    { auth_mode: "shared_key" },
    { schema_version: "forte.deployment/2" },
    { mode: "hosted" },
    { retention: "automatic" },
    { training_enabled: true },
    { ready: "true" },
  ])
    assert.throws(() => parseDeployment({ ...metadata, ...change }, origin))
  assert.throws(() =>
    parseDeployment(
      { ...metadata, destination: "http://localhost:8000" },
      "http://localhost:8000"
    )
  )
  assert.throws(() => parseDeployment(null, origin))
})
test("valid unavailable deployments keep their review metadata but deny uploads", () => {
  for (const change of [{ ready: false }, { browser_uploads_enabled: false }]) {
    const accepted = parseDeployment({ ...metadata, ...change }, origin)
    assert.equal(accepted.destination, origin)
    assert.equal(uploadsAvailable(accepted), false)
  }
  assert.equal(uploadsAvailable(null), false)
})
test("missing, nonfinite, noninteger and unsupported limits fail closed", () => {
  for (const key of Object.keys(metadata.limits)) {
    for (const value of [
      undefined,
      0,
      -1,
      Infinity,
      NaN,
      "30",
      true,
      1.5,
      metadata.limits[key] + 1,
    ]) {
      assert.throws(() =>
        parseDeployment(
          { ...metadata, limits: { ...metadata.limits, [key]: value } },
          origin
        )
      )
    }
  }
})
test("authenticated sessions require exact true, opaque identity, CSRF and future Unix expiry", () => {
  assert.deepEqual(parseSession(session, 1000), session)
  assert.equal(parseSession({ authenticated: false }, 1000), null)
  for (const change of [
    { authenticated: "true" },
    { csrf_token: "short" },
    { csrf_token: "x\n".repeat(32) },
    { expires_at: 999 },
    { expires_at: Infinity },
    { expires_at: "2000" },
  ]) {
    assert.throws(() => parseSession({ ...session, ...change }, 1000))
  }
  for (const principal of [
    { id: "../person", username: "Reviewer" },
    { id: "p", username: "" },
    { id: "p", username: "bad\nname" },
    { id: "p".repeat(129), username: "Reviewer" },
  ]) {
    assert.throws(() => parseSession({ ...session, principal }, 1000))
  }
})

test("a delayed private body is rejected after session invalidation", async () => {
  let deliver
  let valid = true
  let releases = 0
  const response = guardSessionResponse(
    new Response(
      new ReadableStream({
        start(controller) {
          deliver = controller
        },
      })
    ),
    () => valid,
    () => {
      releases += 1
    }
  )
  const body = response.json()
  await new Promise((resolve) => setTimeout(resolve, 0))
  valid = false
  deliver.enqueue(
    new TextEncoder().encode('{"synthetic":"late-private-canary"}')
  )
  await assert.rejects(body, { name: "SessionEnded" })
  assert.equal(releases, 1)
})

test("a buffered response cannot be consumed by a replaced principal", async () => {
  let principal = "synthetic-a"
  let releases = 0
  const response = guardSessionResponse(
    new Response('{"synthetic":true}'),
    () => principal === "synthetic-a",
    () => {
      releases += 1
    }
  )
  principal = "synthetic-b"
  await assert.rejects(response.json(), { name: "SessionEnded" })
  assert.equal(releases, 1)
})

test("current-session binary/range bytes and headers remain exact", async () => {
  let releases = 0
  const bytes = new Uint8Array([0, 255, 12, 128])
  const response = guardSessionResponse(
    new Response(bytes, {
      status: 206,
      headers: {
        "Content-Type": "video/quicktime",
        "Content-Range": "bytes 1-4/20",
      },
    }),
    () => true,
    () => {
      releases += 1
    }
  )
  assert.equal(response.status, 206)
  assert.equal(response.headers.get("Content-Range"), "bytes 1-4/20")
  assert.deepEqual(new Uint8Array(await response.arrayBuffer()), bytes)
  assert.equal(releases, 1)
})
