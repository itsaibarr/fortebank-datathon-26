# VM 1108722: closed hosted-access proposal

Status: **prepared plan; no public application, certificate or external workflow is verified**.
The proposed address is `https://69.19.136.174:18443`. It is not a live-service claim.
The VM was deleted and zero provider VMs/volumes were recorded at 01:03:11 UTC.
The old IP is historical; do not assume it still belongs to this project or run
the commands below. No certificate/ingress step was activated. The canonical
closure receipt is `.context/verify/mechanic-validation-lifecycle-20261018.json`.
The separately authorized loopback/SSH transport checks completed with verified
cleanup at 00:58:57 UTC; see the [transport receipt](vm1108722-transport-verification.json).
Both temporary listeners are closed. This does not activate the HTTPS proposal.

## Ownership and execution window

- VM: `1108722`, public IPv4 `69.19.136.174`.
- The [mechanic-validation owner](t3-thread://v1/012db607-e101-42aa-b562-067b4a631600)
  retains the VM through three baseline API cases and a verified local backup for
  each case. Record its acknowledgement in the operational receipt.
- Before an explicit owner/integrator handoff, do not change the core, bridge,
  certificate configuration or firewall. Do not start another resident model.
- Stop useful work by **2026-10-18 01:08:00 UTC**. The existing hard deletion
  deadline remains **2026-10-18 01:28:30 UTC**. The **$3 session cap is shared**, not
  a new allocation; the project cap remains $30. This plan authorizes no new VM,
  deadline extension or additional spending.
- The separate public-only CPU build was **skipped** before its 00:45 UTC
  deadline. Its verified staged archive remains publisher `e066310` and exact
  exported core `e55c077`; no new image was built. That expired window grants no
  further execution permission.

The handoff must identify the exact running service/container, immutable image,
source commit, effective configuration and model/corpus fingerprints, current
GPU allocation, ports and per-case backup verification receipts. No case names,
frames, descriptions, request bodies or model replies belong in this document.

## Application integration after handoff

The only accepted post-backup plan for the current runtime is a separate
fixed-port application bridge and bounded health/client checks against unchanged
container port 8000. Follow [the unchanged-core procedure](unchanged-core-attach.md).
The current entrypoint supervises the API and model with `wait -n` and an EXIT
cleanup that kills both: an API restart is not an app-only change. No overlay,
candidate API, source replacement or session-mode transition is authorized by
this plan. Any different process needs its own concrete integrator/runtime-owner
review within the unchanged bounds. Never substitute hosted inference after a
failure.

The session/TLS steps below remain a future proposal for an accepted core
checkpoint and separate runtime handoff. They must not be executed merely
because a bridge/health handoff is available.

Reserve an installer-owned application bridge on loopback `18011`, session
gateway on loopback `18012`, and HTTPS ingress on `18443`; verify availability
before binding. Keep every model/service port private. The public origin must
be the proposed IP address and port, including browser API routing and secure
session configuration. Service keys and gateway trust tokens stay server-side.

Public uploads remain disabled until two distinct sessions demonstrate that job,
original-media, evidence, corrections and range requests enforce ownership.
Front-door authentication and a shared API key alone do not satisfy that check.

## Certificate feasibility and proposed commands

A purchased domain is unnecessary: Let's Encrypt now issues public IPv4 and IPv6
certificates. IP certificates require the `shortlived` profile, with **160-hour**
validity. [Availability](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability),
[profile requirements](https://letsencrypt.org/docs/profiles/).

Certbot standalone IP support requires at least 5.3; webroot requires 5.4.
Use the following pinned **5.8.0** image. Registry metadata supplied by the
integrator identifies the multiarchitecture digest as
`sha256:f70ad0adbb7e117f0fe42a63c553f28ea451edabc0148757b6efcd9735acaa20`
and the AMD64 manifest as
`sha256:398c47284a6d6782825be71685f677ef3a1e65b8b5c278a8b1e99f6da84b4eb9`.
This records an artifact identity, not successful execution.
[IP support](https://letsencrypt.org/2026/03/11/shorter-certs-certbot),
[5.8.0 release](https://github.com/certbot/certbot/releases/tag/v5.8.0).

HTTP-01 validation must reach **public port 80**. A container can listen on 8080
with host mapping `80:8080`; changing the client listen port does not change
the CA's destination. Do not redirect the challenge to 18443. The application
can independently serve HTTPS on 18443; TLS-ALPN validation would require 443.
[Challenge requirements](https://letsencrypt.org/docs/challenge-types/),
[client port options](https://eff-certbot.readthedocs.io/en/stable/using.html#certbot-command-line-options).

**All commands below are pending integrator authorization**, including ACME
account creation, Subscriber Agreement acceptance, image preparation, the
temporary HTTP-80 rule and the bounded HTTPS-18443 rule. They are not execution
receipts. Use an operator-provided contact address; do not invent an address or
send invitations/messages. The only intended external registration is the ACME
certificate transaction.

After handoff, prepare the pinned public image explicitly if absent. Confirm
port 80 is unused; do not stop an existing service to free it. Record every new
firewall rule ID and its removal condition. Create dedicated administrator-owned
0700 directories outside the application/case paths, then run these Bash commands:

```bash
ACME_ROOT=/opt/forte26-deploy-b/vm1108722/acme
CERTBOT_IMAGE=certbot/certbot:v5.8.0@sha256:f70ad0adbb7e117f0fe42a63c553f28ea451edabc0148757b6efcd9735acaa20
: "${ACME_CONTACT_EMAIL:?Set the operator-provided ACME contact first}"
sudo install -d -m 0700 "$ACME_ROOT" \
  "$ACME_ROOT"/{staging,production}/{config,work,logs}

request_ip_certificate() {
  local forte_acme_phase="$1"
  shift
  sudo docker run --rm --pull never \
    --name "forte-b-acme-$forte_acme_phase" \
    --label org.forte.deployment=agent-b-vm1108722 \
    --cap-drop ALL --security-opt no-new-privileges:true \
    --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
    --cpus 1 --memory 512m --pids-limit 128 \
    -p 0.0.0.0:80:8080 \
    --mount "type=bind,src=$ACME_ROOT/$forte_acme_phase/config,dst=/etc/letsencrypt" \
    --mount "type=bind,src=$ACME_ROOT/$forte_acme_phase/work,dst=/var/lib/letsencrypt" \
    --mount "type=bind,src=$ACME_ROOT/$forte_acme_phase/logs,dst=/var/log/letsencrypt" \
    "$CERTBOT_IMAGE" certonly \
    --standalone --http-01-port 8080 --preferred-challenges http \
    --required-profile shortlived --ip-address 69.19.136.174 \
    --cert-name forte-jury-ip --non-interactive --agree-tos \
    --email "$ACME_CONTACT_EMAIL" --no-eff-email "$@"
}

request_ip_certificate staging --staging
# Verify staging success and ownership before separately authorizing production.
request_ip_certificate production
```

These containers have no GPU, Docker-socket, model or case mounts. Enforce the
existing time/budget stop even if issuance fails. Staging certificates are not
browser-trusted. Production certificates reside under
`$ACME_ROOT/production/config/live/forte-jury-ip/`. Certbot's container does not
install them into the web server. Configure only the owned ingress, preserving
the `live`/`archive` symlink layout or explicitly refreshing its individual TLS
bind mounts when certificates change. [Docker operation](https://eff-certbot.readthedocs.io/en/stable/install.html#alternative-1-docker).

Remove the temporary port-80 rule after issuance. A continuing deployment needs
twice-daily renewal checks and a successful-renewal hook that refreshes only its
own ingress; renewal also needs an authorized HTTP-80 window. Short certificates
become eligible with half their lifetime remaining. **No new persistent renewal
timer is created in this session.** Record that continuing operation remains
pending rather than claiming unattended renewal.
[Renewal behavior](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates).

## Verification and rollback

Within the approved window, verify the production IP SAN, trust chain and expiry;
HTTPS readiness; authenticated sessions; a real authorized development upload;
ownership including subsequent byte-range reads; and access from outside the
VM network. Private case content must not enter remote browser/screenshot tools.
Preserve receipts at their actual evidence level; issuance and a CPU build are
not end-to-end application verification.

Rollback affects only objects created by this plan:

1. Inspect the exact certificate-container ID and its
   `org.forte.deployment=agent-b-vm1108722` label before stopping/removing it.
   Successful `--rm` runs should leave no certificate container.
2. Stop only the installer-owned ingress and gateway/bridge using their exact
   project/file or verified daemon-state identity. Preserve cases, corrections,
   ACME account material and configuration; never run broad Docker cleanup.
3. Remove only the recorded new HTTP-80/HTTPS-18443 firewall rule IDs. Preserve
   pre-existing rules and SSH access.
4. Do not stop/restart the existing model, owner bridge, SSH master, budget guard
   or deletion timer without the explicit owner handoff. Leave the hard deletion
   deadline intact and report any unverified cleanup immediately.
