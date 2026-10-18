# REA execution and reproducibility

Checked 18 October 2026. These are public website observations. They establish
rendered pages and navigation destinations, not operation of either vendor's
analytics, incident system, API, tracking model or VLM backend.

## Tool and scope

The official REA README, skill and runtime-observation guide were retrieved from
`morluto/rea`, guidance revision
`bbfe6edd60290f9bfbec68c8a0bcf605d8bbf5b3`, skill version 42. The executed CLI
was `rea-agents` **6.5.0**, using its actual
`capture-browser-scenario <inputJson>` command. The packaged schema implementation
and `--help` were inspected before execution. Node was 24.16.0; the launched
Chrome identified Chromium 155.0.8059.82.

The first transient npm acquisition/doctor attempt exited unsuccessfully. The
subsequent pinned CLI worked. Read-only doctor reported missing/drifted Codex MCP
registration and missing native-analysis engines. No client configuration, skill
installation, Hopper or other analysis-engine installation was performed. The
supported CLI fallback completed the requested browser work; MCP registration
was not a prerequisite for this route.

## Executed operations

Two separate **declared launch scenarios** ran in REA-owned temporary profiles:

1. Open the public Mikshi `/CommingSoon` page, wait for a visible body and allow
   one second to settle; retain DOM, accessibility and final URL. Evidence
   `ev_16a4a8c8a6de206322c16e1322fb4dc670eef9ec73bbe5902e8dc7fe954867d4`.
   All three reported steps completed; the public launch placeholder was present.
2. Open AxxonSoft's public VLM page with the same declared waits/captures.
   Evidence
   `ev_d3386afde38a5765b8ce523b77b4a4b8165434d332b735e22f9201786a752a64`.
   All three steps completed. This observed the vendor's presented VLM claims,
   not their truth or actual inference.

Both results report `terminated-owned-process` cleanup and complete requested
sections without truncation. Captures did not request network bodies, storage,
screenshots, execution coverage or initiator traces. Completeness applies only
to the selected sections and attach window. Browser artifact identity was not
established by the provider; website/server versions remain unpinned.

Ordinary T3 browser navigation separately inspected marketing/doc pages and
Mikshi's VLM menu destination. Official Android-store screenshots were static
publisher artifacts. Those observations are not relabeled as REA execution.
There was no passive capture, authenticated vendor session, native VMS binary
analysis, model query, media upload, account creation, contact form or hidden API
probe. Source-available ForteBank code was inspected with normal repository tools.

## Reproduce

Use an existing Chrome-family executable, editing only the executable path in the
two scenario files if necessary:

```sh
npx -y rea-agents@6.5.0 capture-browser-scenario \
  docs/product-research/mikshi-vlm-scenario.json --format json > /outside/git/mikshi-REA.json
npx -y rea-agents@6.5.0 capture-browser-scenario \
  docs/product-research/axxon-vlm-scenario.json --format json > /outside/git/axxon-REA.json
```

These operations execute the declared public pages and their ordinary browser
requests. They do not contain network traffic. Do not substitute a private case
URL, private media, a signed-in account or an internal page into these scenarios.

[The evidence manifest](evidence-manifest.json) records exact Evidence IDs,
operations, browser cleanup, scenario/file hashes, limitations and local export
locations. Full public exports and source-reader artifacts are retained outside
Git at `/Users/itsaibarr/.local/share/forte26/product-research-20261018-v1/`.
Source bodies are not copied into the research report. The export directory is
local evidence, not a portable published artifact or proof of a deployed feature.

Official guidance:
[REA](https://github.com/morluto/rea),
[skill](https://github.com/morluto/rea/blob/main/.agents/skills/reverse-engineer-anything/SKILL.md),
[runtime observation](https://github.com/morluto/rea/blob/main/.agents/skills/reverse-engineer-anything/references/runtime-observation.md),
[scenario contract](https://github.com/morluto/rea/blob/main/docs/browser-scenario-contract.md).
