# Reviewer quick start

Reviewers use a browser. For the hosted demonstration, recordings are processed
on our VM. For a private installation, they are processed and stored on your
organization's configured GPU workstation, server or VM. The CLI is for the
administrator; it is not installed on each reviewer's computer.

The source includes secure local accounts, browser sessions and per-principal
job/media authorization. Deployment verification remains incomplete: no current
hosted URL, clean customer GPU installation or external browser workflow is
claimed. Use the actual verified HTTPS address and account supplied by your
administrator when the installation is activated. An example hostname or another
computer's `localhost` is not that address.

1. Sign in with your local application account. The application shows hosted or
   private mode, the actual destination, readiness, upload limits, manual
   retention and training disabled. Service credentials stay server-side.
2. Upload only footage authorized for that environment. Current limits are MOV,
   video duration at most 180 seconds and a 256 MiB limit for the complete
   multipart request. The upload has a 30-second bound; a slow connection can
   fail before reaching the size limit. Jobs run asynchronously, and unavailable
   service, capacity limits and failed jobs remain explicit.
3. Open the completed case and inspect an event marker, its original source
   interval, participant proposal, source frames and official provision.
   Incomplete coverage and uncertainty remain visible. A completed job with
   `partial` execution or `insufficient_evidence` does not establish compliance.
4. Save corrections under the appropriate review scope and sign out on a shared
   computer. Corrections retain immutable history and authenticated attribution;
   storage alone does not retrain the frozen model or replay corrections into
   future inference.

An authorized prepared example must be labeled as previously analyzed. A live
upload executes the real local pipeline. A private failure never changes the
processing location to our VM. Your account must not access another user's jobs,
original recording, evidence or corrections, including later range requests.
Report a denial or playback defect to the administrator without sharing private
frames or case narratives in public support channels.

Originals, derivatives, corrections, temporary artifacts and backups currently
follow administrator-controlled manual retention. Session expiry or ordinary
shutdown does not delete a case. Uploads are excluded from training; reserved
and jury recordings are excluded from model selection and deployment rehearsals.
