# Automatic Patch-Note Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Subagent
> execution is disabled by this repository unless the user explicitly enables
> it. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically publish verified Blizzard-only Retail patch-note
updates to CurseForge and Netlify at 04:07 Europe/Copenhagen while stopping
before release when any supported locale or validation gate fails.

**Architecture:** A standard-library Python collector discovers and parses an
explicit allowlist of Blizzard news and forum sources into the existing refresh
batch format. A release coordinator applies build, date, localization,
meaningful-change, version, and changed-file gates. A scheduled GitHub workflow
commits a qualifying release, invokes a reusable CurseForge workflow for the
exact commit, and reports failures through one lifecycle-managed GitHub issue.

**Tech Stack:** Python 3.12 standard library and `unittest`, GitHub Actions,
Gemini Interactions/Batch API through the existing translation scripts, Vue 3
website validation, Netlify, and CurseForge API.

---

## File map

- `automation/models.py`: immutable source, document, candidate, and run-result
  value objects shared by the automation modules.
- `automation/sources.json`: reviewed Blizzard host, feed, forum, title, author,
  region, and channel allowlists.
- `automation/source_registry.py`: validates and loads `sources.json`.
- `automation/http_client.py`: bounded, allowlisted HTTP retrieval with safe
  redirect, MIME, size, timeout, and retry behavior.
- `automation/discovery.py`: discovers candidate Blizzard news articles and
  official blue posts and emits normalized source documents.
- `automation/extraction.py`: converts supported Blizzard headings and bullets
  into the existing refresh input schema.
- `automation/qualification.py`: resolves the Retail build and enforces
  Live/PTR, effective-date, category, and idempotency rules.
- `automation/release_files.py`: meaningful-content comparison, byte snapshots,
  semantic version bump, changelog entry, and synchronized version edits.
- `automation/coordinator.py`: composes collection, translation, refresh,
  validation, restoration, and machine-readable run outcomes.
- `automation/reporting.py`: creates, updates, and closes the single automation
  failure issue without exposing secrets.
- `.github/workflows/scheduled-refresh.yml`: schedule, validation, bot commit,
  reusable release invocation, artifacts, and failure reporting.
- `.github/workflows/release.yml`: accepts an exact commit through
  `workflow_call` while retaining filtered push and manual release behavior.
- `tests/fixtures/blizzard/`: minimized official response fixtures with a small
  manifest containing source URL, capture date, and response hash.
- `tests/test_automation_*.py`: Given/When/Then unit and integration coverage.
- `tests/test_scheduled_refresh_workflow.py`: workflow contract coverage.
- `tests/test_release_workflow.py`: reusable exact-SHA release coverage.
- `AGENTS.md`: persistent rules for scheduled releases and manual intervention.
- `.gitignore`: tracks only the automation dependencies needed by GitHub while
  preserving the runtime-only CurseForge package boundary.
- `requirements-dev.txt` and `.codex/config.toml`: tracked test dependencies and
  repository-scoped translation configuration needed by the full CI suite.

## Task 1: Define automation contracts and the Blizzard registry

**Files:**

- Modify: `.gitignore`
- Modify: `tests/test_gitignore_contract.py`
- Create: `automation/__init__.py`
- Create: `automation/models.py`
- Create: `automation/sources.json`
- Create: `automation/source_registry.py`
- Create: `tests/test_automation_source_registry.py`

- [ ] **Step 1: Write failing registry and model tests**

Add Given/When/Then tests that load a temporary registry and prove that only
HTTPS Blizzard hosts, known channels, exact blue-author identities, positive
response limits, and non-empty title rules are accepted:

```python
# Describe the trusted Blizzard source registry.
class SourceRegistryTests(unittest.TestCase):
    def test_rejects_a_non_blizzard_source_host(self) -> None:
        # Given
        registry = valid_registry()
        registry["allowedHosts"].append("wowhead.com")

        # When / Then
        with self.assertRaisesRegex(ValueError, "unsupported Blizzard host"):
            load_registry(write_registry(registry))

    def test_loads_explicit_live_and_ptr_sources(self) -> None:
        # Given
        path = write_registry(valid_registry())

        # When
        registry = load_registry(path)

        # Then
        self.assertEqual({source.channel for source in registry.sources},
                         {"live", "ptr"})
        self.assertEqual(registry.max_response_bytes, 5_000_000)
```

First extend `tests/test_gitignore_contract.py` with a failing test that uses
`git check-ignore` to require the following CI inputs to be trackable:
`automation/`, `tests/`, the fetch and translation scripts, the terminology
registry, `requirements-dev.txt`, `.codex/config.toml`, `AGENTS.md`, automation
documentation, and `scheduled-refresh.yml`. Require `.env`, `.bpn-work`, cache
files, and generated outputs to remain ignored.

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```powershell
python -m unittest tests.test_automation_source_registry -v
```

Expected: import failure for `automation.source_registry`.

- [ ] **Step 3: Add immutable models and strict registry loading**

Define frozen dataclasses for `RegisteredSource`, `SourceRegistry`,
`SourceDocument`, `ExtractedChange`, and `RefreshOutcome`. Use
`urllib.parse.urlsplit` and reject any registry host not equal to or below
`blizzard.com` or `battle.net`. Require `live` or `ptr` for every source and
reject unknown JSON properties so configuration mistakes fail immediately.

Initial `sources.json` must include:

```json
{
  "schemaVersion": 1,
  "allowedHosts": [
    "news.blizzard.com",
    "worldofwarcraft.blizzard.com",
    "us.forums.blizzard.com",
    "eu.forums.blizzard.com",
    "us.version.battle.net",
    "eu.version.battle.net"
  ],
  "blueAuthors": ["Kaivax", "Linxy", "Nethaera", "Bornakk"],
  "maxResponseBytes": 5000000,
  "timeoutSeconds": 20,
  "sources": []
}
```

Populate `sources` only with URLs verified during implementation from current
official Blizzard pages. Record each URL's `kind`, `channel`, `locale`, and
accepted title patterns; do not invent a discovery URL when Blizzard does not
provide one.

Update `.gitignore` with narrow negation rules for the approved CI inputs. Do
not broadly unignore the repository root. Keep the CurseForge runtime list in
`release.yml` unchanged; Git trackability must never imply addon packaging.

- [ ] **Step 4: Run the focused tests**

Run the Task 1 test command. Expected: all tests pass.

- [ ] **Step 5: Request a commit checkpoint**

Show the Task 1 diff and ask the user whether to stage and commit these files.
Do not run Git write commands without that explicit authorization.

## Task 2: Build the safe Blizzard HTTP client

**Files:**

- Create: `automation/http_client.py`
- Create: `tests/test_automation_http_client.py`

- [ ] **Step 1: Write failing HTTP safety tests**

Use a local `ThreadingHTTPServer` fixture and verify:

```python
# Describe bounded retrieval of untrusted Blizzard responses.
class BlizzardHttpClientTests(unittest.TestCase):
    def test_rejects_a_redirect_outside_the_allowlist(self) -> None:
        # Given
        client = BlizzardHttpClient(
            allowed_hosts={"127.0.0.1"},
            max_response_bytes=1024,
            timeout_seconds=1,
        )

        # When / Then
        with self.assertRaisesRegex(SourceRejected, "redirect host"):
            client.get(self.server.url("/redirect-external"))

    def test_rejects_a_response_larger_than_the_limit(self) -> None:
        # Given
        client = self.client(max_response_bytes=32)

        # When / Then
        with self.assertRaisesRegex(SourceRejected, "response limit"):
            client.get(self.server.url("/large"))
```

Also cover unsupported MIME types, HTTP-to-HTTPS downgrade, credentials in
URLs, fragments, permanent 4xx errors, and bounded retry of 429/500/502/503/504.

- [ ] **Step 2: Verify the focused tests fail**

Run:

```powershell
python -m unittest tests.test_automation_http_client -v
```

Expected: import failure for `automation.http_client`.

- [ ] **Step 3: Implement the client with injectable transport and clock**

Use `urllib.request` with a redirect handler that validates every destination.
Read at most `max_response_bytes + 1`, accept JSON, HTML, XML, and plain-text
content types, use exponential delays of 1, 2, and 4 seconds for transient
responses, and raise typed `SourceUnavailable` or `SourceRejected` exceptions.
Expose response bytes, final URL, normalized MIME type, status, and SHA-256.
Never include headers or query credentials in exception text.

- [ ] **Step 4: Verify the client tests pass**

Run the Task 2 test command. Expected: all tests pass with no external network.

- [ ] **Step 5: Request a commit checkpoint**

Present only the HTTP client and its tests for optional user-authorized commit.

## Task 3: Discover official news and blue posts

**Files:**

- Create: `automation/discovery.py`
- Create: `tests/fixtures/blizzard/manifest.json`
- Create: `tests/fixtures/blizzard/news-feed.xml`
- Create: `tests/fixtures/blizzard/forum-topic.json`
- Create: `tests/test_automation_discovery.py`

- [ ] **Step 1: Capture and minimize verified official fixtures**

Read current official Blizzard source responses. Reduce them to the smallest
documents that preserve author, title, canonical URL, post number, timestamps,
locale, and body. Add each original URL, UTC capture time, and full-response
SHA-256 to `manifest.json`. Do not include cookies, tokens, user identifiers,
analytics payloads, or unrelated posts.

- [ ] **Step 2: Write failing discovery tests**

```python
# Describe discovery of eligible official Blizzard documents.
class BlizzardDiscoveryTests(unittest.TestCase):
    def test_accepts_only_blue_authored_forum_posts(self) -> None:
        # Given
        topic = load_fixture("forum-topic.json")

        # When
        documents = discover_forum_documents(topic, self.registry)

        # Then
        self.assertTrue(documents)
        self.assertTrue(all(document.author_is_blue for document in documents))
        self.assertEqual(documents[0].channel, "ptr")

    def test_rejects_an_unknown_feed_shape(self) -> None:
        # Given
        malformed_feed = b"<feed><unexpected /></feed>"

        # When / Then
        with self.assertRaisesRegex(UnsupportedSourceShape, "news feed"):
            discover_news_documents(malformed_feed, self.registry)
```

Cover title allowlists, non-blue replies, duplicates, canonical post anchors,
locale mismatches, missing dates, future dates, and edited-content hashes.

- [ ] **Step 3: Verify the discovery tests fail**

Run:

```powershell
python -m unittest tests.test_automation_discovery -v
```

Expected: import failure for `automation.discovery`.

- [ ] **Step 4: Implement strict news and forum discovery**

Use `xml.etree.ElementTree` for feeds and `json` for forum documents. Require
every forum candidate's author to match the reviewed blue-author registry and
every candidate title to match a configured rule. Canonicalize forum URLs with
their post number. Return documents sorted by publication time and URL.

- [ ] **Step 5: Run discovery tests and request a commit checkpoint**

Expected: all Task 3 tests pass. Then show the fixture provenance and diff
before asking whether the user wants this coherent unit committed.

## Task 4: Extract supported patch-note records

**Files:**

- Create: `automation/extraction.py`
- Create: `tests/fixtures/blizzard/class-notes.html`
- Create: `tests/fixtures/blizzard/dungeon-notes.html`
- Create: `tests/fixtures/blizzard/raid-notes.html`
- Create: `tests/test_automation_extraction.py`

- [ ] **Step 1: Write failing extraction behavior tests**

```python
# Describe strict conversion of Blizzard sections into refresh input.
class PatchNoteExtractionTests(unittest.TestCase):
    def test_groups_multiple_bullets_into_one_change_array(self) -> None:
        # Given
        document = fixture_document("class-notes.html", channel="live")

        # When
        changes = extract_changes(document)

        # Then
        mage = next(change for change in changes if change.class_name == "Mage")
        self.assertEqual(mage.change, (
            "Arcane Blast damage increased by 5%.",
            "Arcane Barrage damage reduced by 3%.",
        ))

    def test_stops_on_an_unknown_heading_inside_a_supported_section(self) -> None:
        # Given
        document = document_with_heading("Experimental Wizardry")

        # When / Then
        with self.assertRaisesRegex(AmbiguousPatchNote, "heading"):
            extract_changes(document)
```

Cover all 13 classes, class-wide and specialization notes, dungeon and raid
names, nested bullets, effective dates, patch versions, Live/PTR channels,
source anchors, excluded PvP/items/professions, and reversed semantic wording.

- [ ] **Step 2: Verify the extraction tests fail**

Run:

```powershell
python -m unittest tests.test_automation_extraction -v
```

Expected: import failure for `automation.extraction`.

- [ ] **Step 3: Implement a small explicit document parser**

Subclass `html.parser.HTMLParser` to emit heading and list-item tokens while
retaining element IDs for source anchors. Map only reviewed section headings,
class names, specialization names, dungeon names, and raid names. Convert each
supported section into the schema-v5 batch shape with every `change` value as
a non-empty list of strings. Raise `AmbiguousPatchNote` for unsupported nested
structures within an otherwise qualifying section.

- [ ] **Step 4: Run extraction and existing data tests**

Run:

```powershell
python -m unittest tests.test_automation_extraction tests.test_update_data -v
```

Expected: all tests pass.

- [ ] **Step 5: Request a commit checkpoint**

Present the parser, fixtures, and tests as one optional commit scope.

## Task 5: Resolve builds and qualify Live/PTR candidates

**Files:**

- Create: `automation/qualification.py`
- Create: `tests/fixtures/blizzard/product-versions.txt`
- Create: `tests/test_automation_qualification.py`

- [ ] **Step 1: Write failing qualification tests**

```python
# Describe build and release-window qualification.
class QualificationTests(unittest.TestCase):
    def test_live_must_match_the_current_retail_patch(self) -> None:
        # Given
        current_patch = "12.0.7"
        candidate = change(channel="live", patch="12.0.8")

        # When
        result = qualify((candidate,), current_patch, date(2026, 8, 5))

        # Then
        self.assertEqual(result.accepted, ())
        self.assertEqual(result.rejected[0].reason, "live patch mismatch")

    def test_ptr_must_be_newer_than_the_current_retail_patch(self) -> None:
        # Given
        candidate = change(channel="ptr", patch="12.1.0")

        # When
        result = qualify((candidate,), "12.0.7", date(2026, 8, 5))

        # Then
        self.assertEqual(result.accepted, (candidate,))
```

Cover the inclusive 14-day window, timezone-aware dates, patch tuple parsing,
multiple-region version agreement, malformed version service responses,
unsupported categories, and deterministic rejection summaries.

- [ ] **Step 2: Verify the qualification tests fail**

Run:

```powershell
python -m unittest tests.test_automation_qualification -v
```

Expected: import failure for `automation.qualification`.

- [ ] **Step 3: Implement build resolution and qualification**

Parse Blizzard product-version text into `major.minor.patch`, require the
configured US and EU Retail values to agree, and inject the resolved patch into
the qualification function. Reuse the patch tuple semantics from
`refresh_patch_notes.py`; move shared parsing into one importable helper only
if duplication would otherwise create inconsistent validation.

- [ ] **Step 4: Run build and refresh tests**

Run:

```powershell
python -m unittest tests.test_automation_qualification tests.test_refresh_patch_notes -v
```

Expected: all tests pass.

- [ ] **Step 5: Request a commit checkpoint**

Show the build resolver and qualification diff before requesting any Git write.

## Task 6: Add all-locale translation and meaningful-change gates

**Files:**

- Create: `automation/release_files.py`
- Create: `automation/coordinator.py`
- Create: `tests/test_automation_release_files.py`
- Create: `tests/test_automation_coordinator.py`
- Modify: `skills/translate-patch-notes/scripts/generate_translations.py`
- Modify: `skills/translate-patch-notes/scripts/validate_translations.py`

- [ ] **Step 1: Write failing release-file tests**

```python
# Describe byte-safe no-change and synchronized release preparation.
class ReleaseFileTests(unittest.TestCase):
    def test_updated_at_alone_is_not_a_meaningful_change(self) -> None:
        # Given
        before = canonical_data(updated_at="2026-08-04T04:07:00+02:00")
        after = canonical_data(updated_at="2026-08-05T04:07:00+02:00")

        # When
        changed = has_meaningful_change(before, after)

        # Then
        self.assertFalse(changed)

    def test_bumps_and_synchronizes_the_patch_version_once(self) -> None:
        # Given
        files = release_files(version="0.2.9")

        # When
        update_release_files(files, date(2026, 8, 5), release_summary())

        # Then
        self.assertEqual(read_versions(files), {"0.2.10"})
        self.assertIn("Version 0.2.10 - 2026-08-05", files.changelog.read_text())
```

Also verify exact byte restoration, newest-first changelog format, changed-file
allowlist enforcement, no interface-number bump, and source URLs excluded from
player-facing changelog text.

- [ ] **Step 2: Write failing coordinator tests**

Inject collector, translator, refresh runner, clock, and filesystem paths. Test
the `NO_CHANGE`, `BLOCKED`, and `RELEASE_READY` outcomes. Require the locale set
to equal `deDE`, `esES`, `esMX`, `frFR`, `itIT`, `koKR`, `ptBR`, `ruRU`,
`zhCN`, and `zhTW`; one failed locale must return `BLOCKED` and restore every
tracked byte.

- [ ] **Step 3: Verify both focused test modules fail**

Run:

```powershell
python -m unittest tests.test_automation_release_files tests.test_automation_coordinator -v
```

Expected: import failures for the new modules.

- [ ] **Step 4: Implement release-file operations and coordinator composition**

Canonicalize JSON after removing only top-level `updatedAt`; never ignore
record dates, IDs, source URLs, provenance, or localization metadata. Snapshot
files as bytes before invoking existing generators. Run translation into a
temporary directory, validate the complete batch, then call the existing
refresh function. Apply release versions only after meaningful change is
proven. Emit `.bpn-work/automation-result.json` with counts, locales, patch
versions, changed files, version, and outcome, but no secrets or raw prompts.

Extend the existing translation CLI only where needed to accept GitHub secret
environment variables and a deterministic temporary output path. Preserve the
configured Gemini model and shared ten-request-per-minute limiter. Do not add
an English-fallback mode to automated runs.

- [ ] **Step 5: Run translation, coordinator, and full Python tests**

Run:

```powershell
python -m unittest tests.test_automation_release_files tests.test_automation_coordinator -v
python -m unittest discover -s tests -v
```

Expected: all tests pass and no tracked file changes are produced by tests.

- [ ] **Step 6: Request a commit checkpoint**

Present the coordinator scope and explicitly exclude the user's existing
`web-app/package-lock.json` modification from staging.

## Task 7: Make the CurseForge workflow reusable for an exact commit

**Files:**

- Modify: `.github/workflows/release.yml`
- Modify: `tests/test_release_workflow.py`

- [ ] **Step 1: Add failing workflow contract tests**

Require `workflow_call`, an optional `commit_sha` input, checkout of the input
SHA for reusable calls, existing filtered push behavior, manual dispatch, and
tag creation from the checked-out release version. Require the workflow to
return CurseForge file ID, version, and tag as outputs.

- [ ] **Step 2: Verify the workflow contract fails**

Run:

```powershell
python -m unittest tests.test_release_workflow -v
```

Expected: failures for missing reusable trigger, input, checkout ref, and
outputs.

- [ ] **Step 3: Refactor release.yml without changing packaging scope**

Add:

```yaml
on:
  workflow_call:
    inputs:
      commit_sha:
        required: false
        type: string
    secrets:
      CF_API_TOKEN:
        required: true
  workflow_dispatch:
  push:
    branches: [main]
    paths:
      - BetterPatchNotes.toc
      - Addon.lua
      - Localization.lua
      - PatchNotesData.lua
      - Data.lua
      - State.lua
      - Window.lua
      - MinimapButton.lua
      - Core.lua
      - changelog.txt
```

Checkout `${{ inputs.commit_sha || github.sha }}` and expose validated version,
tag, and uploaded file ID as job/workflow outputs. Keep the runtime-only ZIP
list unchanged.

- [ ] **Step 4: Run workflow and full Python tests**

Run the focused workflow test, then the full Python suite. Expected: all pass.

- [ ] **Step 5: Request a commit checkpoint**

Show that only the release workflow contract and workflow changed before
requesting user authorization for a commit.

## Task 8: Add the scheduled refresh and failure issue lifecycle

**Files:**

- Create: `automation/reporting.py`
- Create: `.github/workflows/scheduled-refresh.yml`
- Create: `tests/test_automation_reporting.py`
- Create: `tests/test_scheduled_refresh_workflow.py`

- [ ] **Step 1: Write failing reporting tests**

Test a pure `build_issue_payload()` function. Require a constant issue marker,
safe stage name, workflow URL, sanitized error summary, source list, and
artifact name. Verify strings matching Gemini or CurseForge token patterns are
replaced with `[REDACTED]`.

- [ ] **Step 2: Write failing scheduled-workflow contract tests**

Require:

```yaml
on:
  schedule:
    - cron: "7 4 * * *"
      timezone: "Europe/Copenhagen"
  workflow_dispatch:

concurrency:
  group: better-patch-notes-refresh
  cancel-in-progress: false
```

Also assert minimum permissions, Python 3.12, Node from `web-app/.nvmrc`, secret
preflight, coordinator execution, no-change short circuit, full Python tests,
website tests/build, `git diff --check`, explicit changed-file allowlist,
bot commit, exact commit SHA output, reusable release call, artifact upload with
`if: always()`, and issue create/update/close behavior.

- [ ] **Step 3: Verify reporting and workflow tests fail**

Run:

```powershell
python -m unittest tests.test_automation_reporting tests.test_scheduled_refresh_workflow -v
```

Expected: missing module and workflow failures.

- [ ] **Step 4: Implement reporting and the scheduled workflow**

The coordinator step writes outcome and changed-file outputs. For `NO_CHANGE`,
skip every version, Git, release, and issue-success step. For `BLOCKED`, upload
artifacts, create or update the marked issue through `gh issue`, and fail the
run. For `RELEASE_READY`, run all validation commands, compare the actual Git
diff against the coordinator allowlist, configure `github-actions[bot]`, add
only explicit paths, commit with `data: refresh retail patch notes for DATE`,
push `HEAD:main`, and pass `git rev-parse HEAD` to the reusable release job.

Use the repository `GITHUB_TOKEN`; do not add a PAT. Never run `git add .` or
include `.bpn-work`, fixtures, tests, skills, automation code, workflow code,
or the user's unrelated files in an automated data-release commit.

- [ ] **Step 5: Run workflow contracts and all local validations**

Run:

```powershell
python -m unittest discover -s tests -v
Set-Location web-app
npm.cmd test
npm.cmd run build
Set-Location ..
git diff --check
```

Expected: Python tests, website tests, type-check, and production build pass;
`git diff --check` prints nothing.

- [ ] **Step 6: Request a commit checkpoint**

Present the workflow permissions, commit allowlist, and failure-issue behavior.
Do not stage or commit until the user explicitly approves this exact scope.

## Task 9: Persist operational guidance and run a dry run

**Files:**

- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `tests/test_skill_contract.py`
- Modify: `tests/test_gitignore_contract.py`
- Create: `docs/automatic-refresh-operations.md`

- [ ] **Step 1: Write failing guidance contract tests**

Require AGENTS guidance to state: Blizzard-only automatic sources, 04:07
Europe/Copenhagen schedule, all-locales-or-stop rule, no-change stop, no PAT,
exact changed-file allowlist, no second bump after post-commit failure, and
manual review procedure for parser failures.

Also require the Git ignore contract to prove that every file imported or read
by the scheduled workflow is tracked, and that `.env`, `.bpn-work`, caches,
Netlify output, and other local files remain ignored.

- [ ] **Step 2: Verify the contract fails**

Run:

```powershell
python -m unittest tests.test_skill_contract -v
```

Expected: missing automatic-refresh guidance assertions.

- [ ] **Step 3: Add maintainer documentation**

Document required secrets, authorization-key migration, manual dispatch,
workflow artifacts, failure issue lifecycle, parser fixture refresh, safe
reruns, Netlify verification, CurseForge verification, and rollback by a new
reviewed release. State that the pipeline cannot force client installation.

- [ ] **Step 4: Run a no-write local dry run**

Add a coordinator `--dry-run` option that forbids release-file writes and Git
commands. Run it against recorded fixtures and require `RELEASE_READY` or
`NO_CHANGE` output plus an audit report. Then run the full validation commands
from Task 8.

- [ ] **Step 5: Review all diffs and request release authorization**

Confirm the pre-existing `web-app/package-lock.json` change remains separate.
Show the complete file list and tests. Ask the user separately whether to
stage, commit, and push the automation feature. A push containing workflow or
development-only changes must follow the repository's current Git ownership
rules; do not infer authorization from approval of this plan.

## Task 10: Prove the production workflow without publishing bad data

**Files:**

- No production-code change expected.

- [ ] **Step 1: Add GitHub secrets through repository settings**

The human adds or confirms `GEMINI_API_KEY`, optional `GEMINI_API_KEY2`, and
`CF_API_TOKEN`. Never request that secret values be pasted into chat or logs.

- [ ] **Step 2: Run workflow_dispatch in dry-run mode**

Verify source discovery, build resolution, all translations, tests, website
build, artifacts, and issue handling. Expected: no commit, tag, CurseForge
upload, or Netlify production change.

- [ ] **Step 3: Inspect the audit artifact manually**

Confirm all source URLs are official Blizzard URLs, every extracted bullet is
present and correctly categorized, all ten non-English locales passed, and no
secret or unrelated page content appears.

- [ ] **Step 4: Run one explicitly authorized live dispatch**

Only after the dry run is reviewed, enable publishing and dispatch once. If no
qualifying data exists, expect a clean no-change result. If data exists, verify
the single bot commit, synchronized version, release tag, CurseForge file ID,
Netlify production deploy, and closed failure issue.

- [ ] **Step 5: Observe the next scheduled run**

Confirm it starts at approximately 04:07 Europe/Copenhagen, remains idempotent,
does not overlap, and either reports no change or follows the same verified
release path.

## Self-review result

- The plan covers the Blizzard-only source boundary, timezone-aware schedule,
  all-locale stop gate, deterministic extraction, build policy, 14-day window,
  no-change restoration, version synchronization, exact-SHA CurseForge release,
  Netlify deployment, bounded retries, artifacts, and failure issue lifecycle.
- It explicitly moves required automation code, tests, skills, configuration,
  and documentation into Git while retaining the unchanged runtime-only
  CurseForge ZIP allowlist.
- All new production behavior begins with a failing Given/When/Then test and an
  explicit expected failure.
- Shared names are consistent across tasks: `SourceRegistry`,
  `SourceDocument`, `ExtractedChange`, `RefreshOutcome`, `NO_CHANGE`, `BLOCKED`,
  and `RELEASE_READY`.
- Implementation commit checkpoints remain subject to explicit user
  authorization and exclude the existing unrelated package-lock modification.
