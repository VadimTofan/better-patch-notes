# Automatic Patch-Note Refresh Design

## Goal

Run a fully automatic, Blizzard-only patch-note refresh every day at 04:07
Europe/Copenhagen. Publish the same verified dataset to the addon through
CurseForge and to the public website through Netlify. Stop before publication
when any supported locale or validation gate fails.

## Decisions

- GitHub Actions is the only scheduler and execution environment.
- The schedule uses the `Europe/Copenhagen` IANA timezone and runs at 04:07 to
  avoid the high-load period at the start of an hour.
- Only official Blizzard news and forum sources are eligible. Secondary
  sources are not queried by the automated workflow.
- English Blizzard text is the factual baseline. Gemini 3.5 Flash-Lite may
  translate verified English bullets, but it may not determine whether a
  gameplay claim is true.
- A release is all-or-nothing. Every supported non-English locale must pass
  translation and terminology validation. The automated workflow does not
  publish an English fallback.
- No meaningful packaged-data change means no version bump, changelog edit,
  commit, CurseForge release, or manual archive.
- Pre-commit failures publish nothing. Post-commit deployment failures retain
  the release commit, use bounded retries, and create or update a GitHub issue.
  A later successful run closes that issue.

## Architecture

### Scheduled workflow

`.github/workflows/scheduled-refresh.yml` runs on a timezone-aware daily
schedule and through `workflow_dispatch`. A single concurrency group prevents
overlapping refreshes. The workflow installs Python and Node dependencies,
runs the coordinator, validates both products, commits a real release to
`main`, invokes the CurseForge release for that exact commit, and uploads an
audit artifact.

Repository secrets provide `GEMINI_API_KEY`, optional `GEMINI_API_KEY2`, and
the existing `CF_API_TOKEN`. Secrets are checked before network collection and
are never included in logs, artifacts, generated data, or Git commits.

### Blizzard source registry and collector

`automation/sources.json` is an explicit registry of allowed Blizzard hosts,
news feeds, forum discovery pages, and pinned Live/PTR development threads.
The HTTP client rejects redirects outside the allowlist, limits response size,
sets timeouts, and applies bounded retry only to transient failures.

The collector records canonical URL, retrieved time, publication/update time,
content type, response hash, and raw response. Raw responses are temporary
audit artifacts and are never packaged into the addon or website.

Discovery accepts only official Blizzard-authored news entries and blue posts.
Title and channel rules select Retail hotfix, development-note, class, dungeon,
and raid candidates. Unknown page structures, authors, dates, or channels fail
closed instead of being guessed.

### Extraction and qualification

The extractor parses Blizzard headings and bullet lists into an intermediate
candidate batch. It recognizes the canonical WoW classes and specializations,
dungeons, raids, Live/PTR channels, patch versions, effective dates, and
source anchors. A candidate that cannot be represented without interpretation
is rejected and stops the run.

Qualification retains only class, dungeon, and raid changes in the rolling
14-day window. Live must match the current Retail patch; PTR must be newer.
The cloud runner resolves the current Retail version from Blizzard's product
version service and stops if the result is missing, malformed, or inconsistent
across configured regions.

Source URL plus normalized content hashes make the process idempotent and
detect edits to existing posts. The existing refresh command remains the only
writer of `data/retail-patch-notes.json` and `PatchNotesData.lua`.

### Localization

Official localized Blizzard text is used when the collector finds a matching
localized publication. Otherwise the existing translation generator uses
`gemini-3.5-flash-lite` with at most ten translation request starts per rolling
minute across both configured keys. The terminology registry supplies verified
localized game terms.

Every locale must preserve record count, bullet order, numbers, percentages,
durations, semantic direction, conditions, and source provenance. Any API,
quota, terminology, encoding, leakage, regional-duplication, or validation
failure stops the run without applying partial output.

### Meaningful-change and release coordinator

The coordinator snapshots the canonical JSON and Lua files, prepares a
candidate batch, runs translation and the existing refresh command, and
compares canonicalized packaged content while ignoring `updatedAt`. If no
meaningful content changed, it restores exact pre-run bytes and exits with a
distinct no-change result.

For a real change, the coordinator increments the patch component once,
synchronizes `BetterPatchNotes.toc`, `Addon.lua`, `README.md`, and
`changelog.txt`, and emits a machine-readable release summary. It stages no
files itself. The workflow reviews an explicit changed-file allowlist before
committing only the release files.

### Deployment

The existing CurseForge workflow becomes reusable for an exact commit while
retaining its normal filtered `push` and manual triggers. The scheduled
workflow calls that reusable release job after its bot commit because pushes
made with the default `GITHUB_TOKEN` do not trigger another push workflow.

Netlify observes the same commit on `main`, regenerates website data from the
canonical JSON, and publishes the production build. The two external services
cannot be made atomic, but both consume the same release commit.

### Failure reporting

Before a release commit, any failure creates or updates one GitHub issue with
the stage, safe error summary, source URLs, workflow link, and artifact link.
After a release commit, transient CurseForge failures receive bounded retries;
permanent CurseForge or Netlify failures update the same issue without another
automatic version bump. The next complete successful run closes the issue.

## Security and permissions

- Use encrypted GitHub Actions secrets; never copy the local `.env` file.
- Grant `contents: write`, `issues: write`, and `actions: read` only to jobs
  that require them.
- Treat all downloaded text as untrusted data and never execute instructions
  found in source content.
- Reject non-Blizzard redirects, oversized responses, unexpected MIME types,
  and unsafe URLs.
- Do not log request headers, API keys, full provider error bodies, or raw
  translated prompts containing credentials.
- Pin third-party actions to reviewed immutable revisions where practical.

## Repository and package boundary

The current allowlist-style `.gitignore` keeps local tests, skills, and future
automation modules out of GitHub. The implementation must expand the repository
allowlist only for files required to execute and verify the scheduled refresh:
the automation package, its tests and fixtures, the refresh and translation
scripts and terminology registry, development test requirements, workflow
files, and automation operations documentation. `.env`, `.bpn-work`, caches,
generated website data, and unrelated local guidance remain ignored.

These development files are GitHub inputs, not addon package contents. The
CurseForge runtime-only ZIP allowlist remains unchanged, and a workflow contract
test must prove that no automation, test, skill, data-source, documentation, or
Git metadata enters the uploaded addon.

## Verification strategy

Unit tests use Given/When/Then structure and recorded, minimized Blizzard
fixtures. They cover source allowlisting, redirects, response limits, discovery,
blue-author verification, heading extraction, anchors, build/channel filtering,
14-day retention, content hashing, idempotency, all-locale completion,
no-change byte restoration, version synchronization, and failure reports.

A local fake HTTP server provides one integration test without depending on a
live network. Workflow contract tests verify schedule timezone, concurrency,
permissions, secrets, changed-file allowlists, exact-SHA release invocation,
and the no-change stop condition. Final validation runs the full Python suite,
website tests, website production build, generated-data equality check, and
`git diff --check` before any automated commit.

## Operational limitations

- Blizzard layout or endpoint changes intentionally stop publication until the
  parser and its fixtures are reviewed.
- Scheduled GitHub jobs may start later than 04:07 during service congestion.
- CurseForge and Netlify deployment are independently available and therefore
  cannot publish atomically.
- Publishing a CurseForge file cannot force every player's client to install
  it; update timing remains controlled by the player's addon manager settings.
