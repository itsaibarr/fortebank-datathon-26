# Reviewer quick start

The intended choices are a hosted HTTPS demonstration, or the browser address
of your organization's private installation. Reviewers do not install the CLI.

**Current release boundary:** no externally verified hosted URL or secure
multi-user browser release is available. The existing core is approved for one
private reviewer trust domain with administrative API access. Browser sessions
and job/media ownership enforcement remain required before enabling browser
uploads through these profiles. Ask the deployment administrator for the actual
verified address when that integration is completed; do not substitute a sample
hostname or the reviewer's localhost.

Once enabled, the application must show:

- Hosted or private installation, and the actual processing destination.
- Readiness, MOV-only input, a 256 MiB total multipart limit and 180-second video limit.
- A 30-second upload bound, asynchronous progress and explicit unavailable/failed states.
- Manual retention for original/derived media and backups; uploads are not used for training.
- Findings with uncertainty, coverage limitations, original source intervals and official provisions.

Sign in through the installation's secure session. Upload only material
specifically authorized for that environment. A prepared example must be labeled
as a previously analyzed example. A live upload must execute the actual local
pipeline; it must not silently change processing location.

When a job completes, open a marker and check the original interval, participant,
source frames and exact provision. `insufficient_evidence` is an incomplete
assessment, not a finding of compliance. Corrections are preserved review
records; storing them does not imply weight updates or automatic replay.

For failure, retain the job ID and share it with your authorized administrator.
Do not send source recordings, evidence frames, keys or case narratives in public
support messages. Administrator shutdown preserves cases; deletion follows the
installation's actual policy.
