"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  guardSessionResponse,
  parseDeployment,
  parseSession,
  SessionEnded,
  type BrowserSession,
  type DeploymentMetadata,
} from "@/lib/browser-session"

const CHANNEL = "forte-session-changes"
type AuthState = "checking" | "signed-out" | "signed-in"

async function jsonResponse(response: Response) {
  if (
    !response.headers
      .get("Content-Type")
      ?.toLowerCase()
      .startsWith("application/json")
  ) {
    throw new Error("The service returned an unverified response. Try again.")
  }
  return response.json() as Promise<unknown>
}

export function useBrowserAccess() {
  const [session, setSession] = useState<BrowserSession | null>(null)
  const [state, setState] = useState<AuthState>("checking")
  const [generation, setGeneration] = useState(0)
  const [message, setMessage] = useState("")
  const [authBusy, setAuthBusy] = useState(false)
  const [metadata, setMetadata] = useState<DeploymentMetadata | null>(null)
  const [metadataError, setMetadataError] = useState("")
  const [logoutPending, setLogoutPending] = useState(false)
  const sessionRef = useRef<BrowserSession | null>(null)
  const generationRef = useRef(0)
  const requests = useRef(new Set<AbortController>())
  const authRequest = useRef<AbortController | null>(null)
  const authMutation = useRef<AbortController | null>(null)
  const metadataRequest = useRef<AbortController | null>(null)
  const channel = useRef<BroadcastChannel | null>(null)
  const blocked = useRef(false)
  const logoutSession = useRef<BrowserSession | null>(null)

  const invalidate = useCallback((text: string) => {
    authRequest.current?.abort()
    authRequest.current = null
    generationRef.current += 1
    setGeneration(generationRef.current)
    sessionRef.current = null
    setSession(null)
    setState("signed-out")
    setMessage(text)
    for (const controller of requests.current) controller.abort()
    requests.current.clear()
  }, [])

  const acceptSession = useCallback(
    (next: BrowserSession | null) => {
      const previous = sessionRef.current
      if (!next) {
        invalidate(
          previous
            ? "Your session has ended. Sign in again; the private review was cleared."
            : ""
        )
        return
      }
      if (
        previous &&
        (previous.principal.id !== next.principal.id ||
          previous.csrf_token !== next.csrf_token)
      ) {
        invalidate(
          "Your session changed. The previous private review was cleared."
        )
      }
      sessionRef.current = next
      setSession(next)
      setState("signed-in")
      setMessage("")
    },
    [invalidate]
  )

  const refreshMetadata = useCallback(async () => {
    metadataRequest.current?.abort()
    const controller = new AbortController()
    metadataRequest.current = controller
    const timer = setTimeout(() => controller.abort(), 10000)
    try {
      const response = await fetch("/deployment.json", {
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        signal: controller.signal,
      })
      if (!response.ok)
        throw new Error(
          "Deployment details are unavailable. Uploads are paused; retry the check."
        )
      const next = parseDeployment(
        await jsonResponse(response),
        window.location.origin
      )
      if (metadataRequest.current !== controller) return null
      setMetadata(next)
      setMetadataError("")
      return next
    } catch (failure) {
      if (metadataRequest.current === controller) {
        setMetadata(null)
        setMetadataError(
          failure instanceof Error && failure.name !== "AbortError"
            ? failure.message
            : "Deployment check timed out. Uploads are paused; retry the check."
        )
      }
      return null
    } finally {
      clearTimeout(timer)
    }
  }, [])

  const recheck = useCallback(async () => {
    if (blocked.current || authMutation.current) return
    authRequest.current?.abort()
    const controller = new AbortController()
    authRequest.current = controller
    const timer = setTimeout(() => controller.abort(), 10000)
    try {
      const response = await fetch("/auth/session", {
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        signal: controller.signal,
      })
      if (!response.ok)
        throw new Error("Your session could not be verified. Sign in again.")
      const next = parseSession(await jsonResponse(response))
      if (authRequest.current === controller && !blocked.current)
        acceptSession(next)
    } catch {
      if (authRequest.current === controller && !blocked.current) {
        invalidate(
          "Your session could not be verified. The private review was cleared. Retry the session check or sign in."
        )
      }
    } finally {
      clearTimeout(timer)
    }
  }, [acceptSession, invalidate])

  useEffect(() => {
    const activeRequests = requests.current
    const initial = setTimeout(() => {
      void recheck()
      void refreshMetadata()
    }, 0)
    if (typeof BroadcastChannel !== "undefined") {
      channel.current = new BroadcastChannel(CHANNEL)
      channel.current.onmessage = (event) => {
        if (event.data?.type === "session-ending") {
          blocked.current = true
          authRequest.current?.abort()
          invalidate(
            "Sign-out started in another tab. The private review was cleared."
          )
        } else if (event.data?.type === "session-changed") {
          blocked.current = false
          invalidate("Your session changed in another tab. Checking access…")
          void recheck()
          void refreshMetadata()
        }
      }
    }
    const refresh = () => {
      void recheck()
      void refreshMetadata()
    }
    const pageshow = (event: PageTransitionEvent) => {
      if (event.persisted) invalidate("Checking your restored session…")
      refresh()
    }
    window.addEventListener("focus", refresh)
    window.addEventListener("pageshow", pageshow)
    return () => {
      clearTimeout(initial)
      authRequest.current?.abort()
      authRequest.current = null
      metadataRequest.current?.abort()
      metadataRequest.current = null
      authMutation.current?.abort()
      for (const controller of activeRequests) controller.abort()
      channel.current?.close()
      window.removeEventListener("focus", refresh)
      window.removeEventListener("pageshow", pageshow)
    }
  }, [invalidate, recheck, refreshMetadata])

  useEffect(() => {
    if (!session) return
    const timer = setTimeout(
      () => {
        invalidate(
          "Your session expired. Sign in again; the private review was cleared."
        )
        channel.current?.postMessage({ type: "session-changed" })
      },
      Math.min(2147483647, Math.max(0, session.expires_at * 1000 - Date.now()))
    )
    return () => clearTimeout(timer)
  }, [invalidate, session])

  const login = useCallback(
    async (username: string, password: string) => {
      authRequest.current?.abort()
      const controller = new AbortController()
      authRequest.current = controller
      authMutation.current = controller
      blocked.current = false
      setAuthBusy(true)
      setMessage("")
      const timer = setTimeout(() => controller.abort(), 10000)
      try {
        const response = await fetch("/auth/login", {
          method: "POST",
          credentials: "same-origin",
          cache: "no-store",
          redirect: "error",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
          signal: controller.signal,
        })
        if (!response.ok)
          throw new Error(
            response.status === 429
              ? "Too many sign-in attempts. Wait before trying again."
              : "Sign-in was not accepted. Check your account details and try again."
          )
        const next = parseSession(await jsonResponse(response))
        if (!next) throw new Error("Sign-in could not be verified. Try again.")
        if (authRequest.current !== controller) return
        invalidate("")
        acceptSession(next)
        logoutSession.current = null
        setLogoutPending(false)
        channel.current?.postMessage({ type: "session-changed" })
        void refreshMetadata()
      } catch (failure) {
        if (authRequest.current === controller) {
          invalidate(
            failure instanceof Error && failure.name !== "AbortError"
              ? failure.message
              : "Sign-in could not reach the service. Try again."
          )
        }
      } finally {
        clearTimeout(timer)
        if (authMutation.current === controller) {
          authMutation.current = null
          setAuthBusy(false)
        }
      }
    },
    [acceptSession, invalidate, refreshMetadata]
  )

  const logout = useCallback(async () => {
    const ending = sessionRef.current || logoutSession.current
    if (!ending) return
    logoutSession.current = ending
    blocked.current = true
    authRequest.current?.abort()
    invalidate("Signing out. The private review was cleared.")
    channel.current?.postMessage({ type: "session-ending" })
    setAuthBusy(true)
    setLogoutPending(true)
    const controller = new AbortController()
    authMutation.current = controller
    const timer = setTimeout(() => controller.abort(), 10000)
    try {
      const response = await fetch("/auth/logout", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        headers: { "X-CSRF-Token": ending.csrf_token },
        signal: controller.signal,
      })
      if (!response.ok && response.status !== 401) throw new Error()
      logoutSession.current = null
      setLogoutPending(false)
      setMessage("You are signed out. The private review was cleared.")
      channel.current?.postMessage({ type: "session-changed" })
    } catch {
      setMessage(
        "The private review was cleared, but the service could not confirm sign-out. Retry sign out."
      )
    } finally {
      clearTimeout(timer)
      if (authMutation.current === controller) {
        authMutation.current = null
        setAuthBusy(false)
      }
    }
  }, [invalidate])

  const request = useCallback(
    async (path: string, options: RequestInit = {}) => {
      let current = sessionRef.current
      if (
        !current ||
        generationRef.current !== generation ||
        current.principal.id !== session?.principal.id
      )
        throw new SessionEnded()
      // Refresh near expiry only during an actual API action. No periodic
      // heartbeat keeps an otherwise idle session alive.
      if (current.expires_at * 1000 - Date.now() < 60000) {
        await recheck()
        current = sessionRef.current
        if (
          !current ||
          generationRef.current !== generation ||
          current.principal.id !== session?.principal.id
        )
          throw new SessionEnded()
      }
      if (current.expires_at * 1000 <= Date.now()) {
        invalidate(
          "Your session expired. Sign in again; the private review was cleared."
        )
        throw new SessionEnded()
      }
      if (
        !/^\/api\/v[12]\//.test(path) ||
        path.includes("\\") ||
        path.includes("#")
      )
        throw new Error("Invalid service request.")
      const principalId = current.principal.id
      const controller = new AbortController()
      requests.current.add(controller)
      const abort = () => controller.abort()
      options.signal?.addEventListener("abort", abort, { once: true })
      if (options.signal?.aborted) controller.abort()
      const timer = setTimeout(
        abort,
        /\/(source|evidence\/[^/]+)$/.test(path) ? 330000 : 35000
      )
      const headers = new Headers(options.headers)
      headers.delete("X-API-Key")
      headers.delete("X-Forte-Gateway-Token")
      headers.delete("X-Forte-Principal")
      if (!["GET", "HEAD"].includes((options.method || "GET").toUpperCase()))
        headers.set("X-CSRF-Token", current.csrf_token)
      let streaming = false
      const cleanup = () => {
        clearTimeout(timer)
        requests.current.delete(controller)
        options.signal?.removeEventListener("abort", abort)
      }
      try {
        const response = await fetch(path, {
          ...options,
          headers,
          credentials: "same-origin",
          cache: "no-store",
          redirect: "error",
          signal: controller.signal,
        })
        if (
          generationRef.current !== generation ||
          sessionRef.current?.principal.id !== current.principal.id
        )
          throw new SessionEnded()
        if (response.status === 401) {
          invalidate(
            "Your session has ended. Sign in again; the private review was cleared."
          )
          channel.current?.postMessage({ type: "session-changed" })
          throw new SessionEnded()
        }
        if (!response.ok)
          throw new Error(
            response.status === 403
              ? "This action was refused. Recheck your session and try again."
              : response.status === 409
                ? "The review changed. Reload its history before saving again."
                : response.status === 429
                  ? "The service is at capacity. Wait before trying again."
                  : `Request failed (${response.status}). Try again.`
          )
        streaming = true
        return guardSessionResponse(
          response,
          () =>
            generationRef.current === generation &&
            sessionRef.current?.principal.id === principalId,
          cleanup
        )
      } finally {
        if (!streaming) cleanup()
      }
    },
    [generation, invalidate, recheck, session?.principal.id]
  )

  return {
    session,
    state,
    generation,
    message,
    authBusy,
    metadata,
    metadataError,
    logoutPending,
    login,
    logout,
    recheck,
    refreshMetadata,
    request,
  }
}

export type BrowserAccess = ReturnType<typeof useBrowserAccess>
