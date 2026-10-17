"use client"

import { useState } from "react"
import Link from "next/link"
import {
  CircleHelp,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  ScanEye,
} from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import type { BrowserAccess } from "@/hooks/use-browser-access"
import { uploadsAvailable } from "@/lib/browser-session"

export function WorkspaceHeader({ access }: { access: BrowserAccess }) {
  return (
    <header className="workspace-header">
      <Link href="/" className="brand">
        <span className="brand-mark">
          <ScanEye className="size-5" />
        </span>
        <span>
          forte
          <span className="font-normal text-muted-foreground"> / review</span>
        </span>
      </Link>
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-3">
        {access.session ? (
          <>
            <span
              className="max-w-40 truncate text-sm"
              title={access.session.principal.username}
            >
              {access.session.principal.username}
            </span>
            <span className="hidden text-xs text-muted-foreground lg:block">
              Session until{" "}
              {new Intl.DateTimeFormat(undefined, {
                hour: "2-digit",
                minute: "2-digit",
              }).format(access.session.expires_at * 1000)}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void access.logout()}
              disabled={access.authBusy}
            >
              <LogOut data-icon="inline-start" />
              Sign out
            </Button>
          </>
        ) : (
          <Badge variant="outline">
            <LockKeyhole />
            Secure sign-in
          </Badge>
        )}
      </div>
    </header>
  )
}

export function DeploymentNotice({ access }: { access: BrowserAccess }) {
  const { metadata, metadataError } = access
  return (
    <section
      aria-label="Deployment and recording policy"
      className="deployment-notice"
    >
      {metadata ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold">Private installation</h2>
              <p className="mt-1 text-xs break-all text-muted-foreground">
                Processing destination: {metadata.destination}
              </p>
            </div>
            <Badge variant="outline">
              {uploadsAvailable(metadata)
                ? "Ready for uploads"
                : metadata.ready
                  ? "Uploads disabled"
                  : "Service not ready"}
            </Badge>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
            MOV · up to{" "}
            {(metadata.limits.upload_max_bytes / 1024 / 1024).toLocaleString(
              undefined,
              { maximumFractionDigits: 1 }
            )}{" "}
            MiB total upload and {metadata.limits.max_video_seconds} seconds.
            Upload within {metadata.limits.upload_timeout_seconds} seconds;
            analysis budget {metadata.limits.job_timeout_seconds} seconds.
          </p>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
            Manual retention: originals, evidence, corrections and backups
            remain until administrator deletion. Uploads are not used for
            training.
          </p>
          {!uploadsAvailable(metadata) && (
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <p className="text-xs text-muted-foreground">
                Existing reviews remain available. Retry readiness before a new
                upload.
              </p>
              <Button
                variant="outline"
                size="xs"
                onClick={() => void access.refreshMetadata()}
              >
                Recheck readiness
              </Button>
            </div>
          )}
        </>
      ) : (
        <Alert>
          <CircleHelp />
          <AlertTitle>
            {metadataError ? "Uploads paused" : "Checking deployment"}
          </AlertTitle>
          <AlertDescription>
            <p>
              {metadataError ||
                "Confirming this installation, recording limits and processing destination."}
            </p>
            {metadataError && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => void access.refreshMetadata()}
              >
                Retry deployment check
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}
    </section>
  )
}

export function SignInWorkspace({ access }: { access: BrowserAccess }) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!username.trim() || !password || access.authBusy) return
    try {
      await access.login(username.trim(), password)
    } finally {
      setPassword("")
    }
  }
  return (
    <div className="min-h-screen bg-sidebar/35">
      <a href="#review-main" className="skip-link">
        Skip to sign in
      </a>
      <WorkspaceHeader access={access} />
      <main id="review-main" className="workspace-main pb-10">
        <div>
          <p className="text-sm text-muted-foreground">Cash operation review</p>
          <h1 className="mt-2 font-heading text-3xl font-semibold tracking-tight sm:text-4xl">
            Sign in to your review workspace.
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            Use the account provided by this installation&apos;s administrator.
            Your recordings and review history require an active session.
          </p>
        </div>
        <DeploymentNotice access={access} />
        <section className="sign-in-panel" aria-labelledby="sign-in-title">
          <h2 id="sign-in-title" className="text-lg font-semibold">
            {access.state === "checking" ? "Checking your session" : "Sign in"}
          </h2>
          <p
            role="status"
            aria-live="polite"
            aria-atomic="true"
            className="mt-3 text-sm leading-relaxed"
          >
            {access.message ||
              (access.state === "checking"
                ? "Confirming access to this installation…"
                : "Your session stays in a protected browser cookie.")}
          </p>
          {access.logoutPending ? (
            <Button
              className="mt-5"
              disabled={access.authBusy}
              onClick={() => void access.logout()}
            >
              {access.authBusy && (
                <LoaderCircle
                  data-icon="inline-start"
                  className="animate-spin motion-reduce:animate-none"
                />
              )}
              Retry sign out
            </Button>
          ) : (
            access.state !== "checking" && (
              <form onSubmit={submit} className="mt-5">
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="username">Username</FieldLabel>
                    <Input
                      id="username"
                      name="username"
                      autoComplete="username"
                      required
                      maxLength={128}
                      value={username}
                      onChange={(event) => setUsername(event.target.value)}
                      disabled={access.authBusy}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="password">Password</FieldLabel>
                    <Input
                      id="password"
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      required
                      maxLength={1024}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      disabled={access.authBusy}
                    />
                    <FieldDescription>
                      Need access or a password reset? Contact your installation
                      administrator.
                    </FieldDescription>
                  </Field>
                  <div className="flex flex-wrap gap-3">
                    <Button
                      type="submit"
                      disabled={
                        access.authBusy || !username.trim() || !password
                      }
                    >
                      {access.authBusy ? (
                        <LoaderCircle
                          data-icon="inline-start"
                          className="animate-spin motion-reduce:animate-none"
                        />
                      ) : (
                        <LockKeyhole data-icon="inline-start" />
                      )}
                      Sign in
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      disabled={access.authBusy}
                      onClick={() => void access.recheck()}
                    >
                      Retry session check
                    </Button>
                  </div>
                </FieldGroup>
              </form>
            )
          )}
        </section>
      </main>
    </div>
  )
}
