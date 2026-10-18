# Public resource preparation

The administrator installer prepares public resources before any recording is
processed. This stage accepts the selected integration manifest and its canonical
`contracts/frozen-assets-v1.json` inventory. It does not run a model, export new
weights, read cases, interpret legislation, or select another processing host.
Resource success alone does not establish application or inference readiness.

The resource-inclusive `forte-admin-0.2.0` artifact supplies the small frozen
public bundle. The current allowlisted selection has 21 files totaling
3,826,331 bytes: legal text/provenance, rule cards, configurations, the model hash
manifest and approved ReID ONNX/export manifest. It excludes the core image and
large model files. The 18 pinned BF16 weight shards alone total
55,563,006,776 bytes, about 51.75 GiB. They are acquired separately or supplied in
an operator-prepared local bundle. They are never committed or inferred from a
model name. The administrator publisher enables the small bundle explicitly:

```sh
python3 tools/forte-admin/build.py \
  --with-public-resources --public-artifacts-root /approved/public-artifacts \
  --core-commit FULL_VERIFIED_CORE_COMMIT \
  --output /outside-git/forte-admin-0.2.0.tar.gz
```

An archive built without that selection records
`public_resources_included: false`; it contains tooling/metadata rather than the
legal/ReID bundle. The public publisher reads only the explicit approved ReID
paths and exact source files. It checks each size/hash, rejects symlinks and
omits all model shards without opening them.
The independent `--core-commit` selection exports public build inputs from the
specified full verified commit into `core-source/`; it does not include an
already-built image. `RELEASE.json` records whether source was included.

Preparation is offline by default. The nonmutating preview makes no network
requests, creates no directories, and imports no images. It may inspect whether
the exact local Docker image ID is already installed. Explicit online preparation
downloads only the individual pinned public model files and detector asset. It
does not download repository trees or use account credentials, cookies,
environment HTTP proxies, external inference, or hosted processing fallbacks.
At the CLI, `install --online` explicitly allows this public preparation;
`--resource-source /approved/resources` imports a local directory and can be
repeated. Keeping `--preview` performs neither download nor import even when
`--online` is present. Cases are processed only later, with outbound networking
denied in the selected environment. A private runtime failure never changes that
environment to our hosted VM.

The source order is an already-correct installed file, operator-supplied resource
directories, the administrator release's `public-resources/` directory, then the
release's exact legal/configuration files. Every usable file must match the
installation manifest's SHA256 and size; where the effective configuration has
no inventory size, its full SHA256 remains mandatory. Files absent from the
allowlist are never traversed or copied. Existing correct resources retain their
bytes and modification times. A corrupt source or installed file is reported;
only fully verified replacement bytes can replace a destination.

An operator-prepared disconnected bundle has the same relative paths as
`assets[].path` in the integration manifest, for example:

```text
public-resources/
  models/snapshots/<pinned-revision>/model-00001-of-00018.safetensors
  models/snapshots/<pinned-revision>/model-hashes.json
  models/public/yolox_s.onnx
  models/public/reid/osnet.onnx
  models/public/reid/manifest.json
  legal/2026-10-17/manifest.json
  legal/2026-10-17/corpus.json
  legal/2026-10-17/<act>/<revision>/source.html
  config/frozen-inference.json
```

This list is illustrative; the manifest is the complete allowlist. The checked
public legal snapshot, rule cards, original example configurations, frozen model
hash manifest and effective runtime configuration can also come directly from
their pinned source files in the administrator release. A current official page
URL is provenance, not a reproducible download URL for an old JSON snapshot.
Preparation therefore copies the shipped immutable legal files and never
re-ingests or silently updates the law. ReID ONNX and its export manifest require
the approved local artifacts if they are not included in the release bundle;
there is no substitute model or automatic re-export.

One installed CUDA backend is supported. Hardware qualification checks free
device memory and actual workload compatibility, without requiring a particular
GPU product name, workstation or VM. Weight bytes alone do not include the
vision/context/cache overhead. System RAM is not a CPU-offload implementation.
The bounded model load and visual warmup are separate from resource preparation;
only those checks can establish the selected workload's readiness on a new host.

Online transfers stream into `<filename>.part` with a bounded size and duration.
The accompanying `.part.json` identifies only the public source, expected hash,
size and strong ETag. A retry uses `Range` and `If-Range` only when that identity
and validator match. A partial response must have the exact starting offset,
total size, range length and ETag. A full response restarts the transfer rather
than appending a different representation. Without a strong validator, retries
restart. Publication is atomic after full SHA256 verification. Incomplete public
bytes remain resumable; invalid metadata, oversized partials and completed
partials with the wrong hash stop for administrator inspection. They are never
treated as usable resources.

Only HTTPS and the explicitly allowed public Hugging Face/GitHub asset origins
are permitted. A redirect to another origin stops with a fixed diagnostic. URLs
with credentials and public response bodies do not appear in diagnostic output.
Future CDN changes require a reviewed allowlist change.

For the historical core's immutable local image ID, supply an approved
`docker save` artifact through `install --image-artifact /approved/core-image.tar`.
Preparation imports it with `docker load` and checks
`docker image inspect` against the exact requested ID. An existing matching
image is preferred, and preview does not load it. An unavailable or wrong image
stays a prerequisite failure. This helper does not infer a registry repository
from a local image ID or pull an unpinned tag. Registry-digest acquisition is a
separate explicit installer operation.

`install --build-core` is a separate, explicit public source-build route. The
default is the current extracted release; `--core-source` selects another
extracted release directory containing `RELEASE.json` and `core-source/`.
`--node-image` selects an immutable Node build image. This stage may fetch public
build dependencies when online preparation
is selected. It must have no case or private credential mounts. The resulting
image ID and source receipt identify a new image; a successful build does not
establish model, offline-analysis, browser-session or ownership acceptance.
It cannot inherit a historical image's successful GPU receipt automatically.

The preparation report contains per-resource `present`, `available` (preview),
`prepared`, `missing` or `corrupt` states, published/imported byte counts,
retained partial-byte counts and safe unresolved prerequisites. The installer
must require both successful preparation and the separate release, hardware,
security and real workload checks before serving an installation.

Verification for this component uses synthetic local HTTP bytes, disconnected
file fixtures and a fake Docker command boundary. It covers resumable transfer,
changed/weak ETags, incorrect ranges and lengths, hash mismatch, interruption,
origin rejection, repeatability, symlinks and image identity. These checks are
not a clean GPU installation, a real model download, or an inference receipt.
Exact small-resource verification likewise does not prove that a complete
disconnected installation bundle, including every image/build dependency and all
weights, is available. Clean new-host installation, new-image offline analysis
and an externally verified hosted browser workflow remain separate acceptance
checks. See [administrator.md](administrator.md) for the actual CLI workflow.
