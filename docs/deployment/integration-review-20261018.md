# Deployment integration review

Agent B commit `691cf02286ae20b49e35460f03d89adea9e2c94e` was cherry-picked as
`98be4bb078d48398cc4a7fab461a316c815c78d2` onto
`dc3866438c670eecf0b6c75f9660a5f11a8c7757` in an isolated checkout. The parent
mechanic-validation checkout was not modified. The source fixes are commit
`e066310ef45e684926250de2713dc2351b13fb53`.

Review found and fixed six integration defects:

- Pass the private/hosted deployment label into the actual session gateway.
- Normalize a single trailing origin slash in configuration planning and reject
  noncanonical direct runtime input before service operations.
- Recover a stopped private core by stopping only verified owned access helpers,
  then performing fresh GPU, host and port checks before starting the core.
- Bind candidate derivation to the exact source inventory bytes used by the build,
  including its core commit, before changing configuration or writing a candidate.
- Reject malformed declared resource minima before host probes. Missing or null
  minima remain explicitly unvalidated.
- Lock each shared public download through resume, hashing and publication. The
  private lock inode persists; concurrent preparation reports a retry condition.

The original integration passed 653 tests. After the fixes and regressions, the
complete suite passed **706 tests, no skips, four existing warnings** in 66.36
seconds with `FORTE_TEST_DOCKER_PROXY=1`, including cached local Nginx checks.
Scoped Ruff checks passed and all 34 deployment Python files passed formatting.
Whitespace checks passed. The parent virtualenv supplied dependencies;
`PYTHONPATH` selected the isolated checkout's source. Core, UI, session and
mechanic-validation files were unchanged by these fixes.

The corrected archive is `forte-admin-0.2.0-integrated-e066310.tar.gz`, SHA256
`7fdd77bfd6e8485254395a7c0a7fa9338ed993430037ae5ea35e830ce79f2b41`.
It identifies publisher `e066310` and exports the unchanged core snapshot
`e55c0773ea74e2745ea33512d19bfaa38b32d7fb`. Two builds were byte-identical.
All 187 release inventory hashes, 123 source file hashes and sizes, and 21 public
assets (3,826,331 bytes) were verified. Extracted CLI/import checks passed.
The install preview honestly blocked on the unsupported local host without
creating installation state; the source-build preview passed without invoking
its subprocess runner. The original B archive was preserved unchanged.

All five acceptance flags remain false. These are source and synthetic software
checks; no model build, GPU inference, live account creation, service activation,
public HTTPS acceptance or quality approval was performed by this review.
The runtime owner separately permits B's public source build on the existing
host, limited to 2 CPU / 4 GiB of actual Docker work, 1,200 seconds and the agreed
earlier stop time. This permits no evaluation-runtime, GPU, private mount,
ingress, firewall, timer or shared-cache changes. A runtime handoff remains
required before any application attachment.

Machine-readable results: [integration-review-20261018.json](integration-review-20261018.json).
Detailed local logs are outside Git under
`~/.cache/forte-deploy-b/integration-fixes-20261018/`.
