# Parallel Locale Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire and retain English patch-note data as an artifact, translate ten locales in isolated sequential jobs, and publish one atomic release only after every locale validates.

**Architecture:** Split the current coordinator into acquisition, single-locale translation, and aggregation commands. GitHub Actions passes immutable JSON artifacts between an acquisition job, a ten-entry matrix limited to one active job, and one aggregation/release job; no English-only data is committed. Sequential matrix execution preserves per-locale logs and timeouts while enforcing the repository-wide Gemini request-start limit.

**Tech Stack:** Python 3.12, GitHub Actions matrix jobs and artifacts, existing Gemini translation scripts, `unittest`.

---

### Task 1: Add an English acquisition command

**Files:**
- Create: `automation/acquisition.py`
- Modify: `automation/runner.py`
- Test: `tests/test_automation_acquisition.py`

- [ ] **Step 1: Write failing Given/When/Then tests** proving acquisition writes `english-document.json`, `runtime-terminology.json`, and `acquisition-result.json`; reports `NO_CHANGE` when meaningful English content matches canonical data; and reports `DATA_CHANGED` without editing release files when it differs.
- [ ] **Step 2: Run `python -m unittest tests.test_automation_acquisition -v` and confirm failure because `automation.acquisition` does not exist.**
- [ ] **Step 3: Extract the existing collection, qualification, official-localization, and runtime-terminology preparation into a side-effect-bounded function:**

```python
@dataclass(frozen=True, slots=True)
class AcquisitionOutcome:
    status: str
    current_patch: str
    accepted: int


def acquire_english(*, output_directory: Path, now: datetime) -> AcquisitionOutcome:
    """Write immutable acquisition artifacts without editing release files."""
```

The command must compare meaningful incoming English records with canonical English records while ignoring only `updatedAt`. It must never invoke Gemini, bump versions, or write packaged files.
- [ ] **Step 4: Run the focused tests and confirm they pass.**

### Task 2: Restrict translation generation to one locale

**Files:**
- Modify: `skills/translate-patch-notes/scripts/generate_translations.py`
- Modify: `skills/translate-patch-notes/scripts/validate_translations.py`
- Test: `tests/test_translation_generation.py`
- Test: `tests/test_translation_validation.py`

- [ ] **Step 1: Add failing tests** showing `--locale deDE` generates only `deDE`, rejects unsupported locale values, and single-locale validation classifies only its requested locale rather than treating the other nine as fallbacks.
- [ ] **Step 2: Run the four new focused test cases and verify the expected failures.**
- [ ] **Step 3: Add the minimal explicit CLI arguments and pure filtering:**

```python
parser.add_argument(
    "--locale",
    choices=sorted(SUPPORTED_TRANSLATION_LOCALES),
)
```

Pass the selected locale set into generation and validation. Preserve current all-locale behavior when the argument is absent so local/manual callers remain compatible.
- [ ] **Step 4: Rerun translation-generation and validation tests and confirm they pass.**

### Task 3: Add a single-locale worker command

**Files:**
- Create: `automation/translate_locale.py`
- Modify: `automation/runner.py`
- Test: `tests/test_automation_translate_locale.py`

- [ ] **Step 1: Write failing Given/When/Then tests** for a successful locale artifact, a Gemini timeout artifact, a validation failure artifact, and rejection of an artifact whose declared locale differs from `--locale`.
- [ ] **Step 2: Run `python -m unittest tests.test_automation_translate_locale -v` and verify failure because the worker is absent.**
- [ ] **Step 3: Implement one worker interface:**

```python
def translate_locale(
    *,
    locale: str,
    english_path: Path,
    terminology_path: Path,
    output_path: Path,
) -> int:
    """Return zero only when this locale is complete and validated."""
```

The output must contain `locale`, `status`, `reason`, `localizations`, `semanticApprovals`, and `uncertainTerms`. Redact secrets from errors. Give each process its own 25-minute budget and checkpoint path so jobs cannot overwrite one another.
- [ ] **Step 4: Run the focused tests and confirm they pass.**

### Task 4: Add atomic locale aggregation

**Files:**
- Create: `automation/aggregate_translations.py`
- Modify: `automation/coordinator.py`
- Test: `tests/test_automation_aggregate_translations.py`
- Test: `tests/test_automation_coordinator.py`

- [ ] **Step 1: Write failing tests** proving aggregation rejects a missing, duplicate, failed, mismatched, or invalid locale artifact; merges exactly ten passing locale artifacts; reruns complete cross-locale validation; and only then calls existing release-file/version logic.
- [ ] **Step 2: Run the focused aggregation tests and verify they fail for the missing module/API.**
- [ ] **Step 3: Implement a pure merge boundary:**

```python
def aggregate_locale_artifacts(
    english_document: dict[str, object],
    locale_documents: tuple[dict[str, object], ...],
) -> dict[str, object]:
    """Return one batch only when every supported locale passed."""
```

Keep `coordinate_release` responsible for snapshots, canonical refresh, version bump, and release summaries. Add an entry point that accepts the already validated combined batch instead of reacquiring or retranslating it.
- [ ] **Step 4: Run the focused tests and confirm they pass.**

### Task 5: Replace the monolithic workflow with gated jobs

**Files:**
- Modify: `.github/workflows/scheduled-refresh.yml`
- Modify: `tests/test_scheduled_refresh_workflow.py`

- [ ] **Step 1: Add failing workflow-contract tests** requiring jobs named `acquire`, `translate`, and `aggregate`; a ten-locale matrix with `max-parallel: 1`; acquisition and per-locale artifacts; `needs.acquire.outputs.outcome == 'DATA_CHANGED'`; aggregation depending on both earlier jobs; and release depending only on successful aggregation.
- [ ] **Step 2: Run `python -m unittest tests.test_scheduled_refresh_workflow -v` and confirm the new assertions fail against the monolithic workflow.**
- [ ] **Step 3: Implement the workflow data flow:**

```yaml
translate:
  needs: acquire
  if: needs.acquire.outputs.outcome == 'DATA_CHANGED'
  strategy:
    fail-fast: false
    max-parallel: 1
    matrix:
      locale: [deDE, esES, esMX, frFR, itIT, koKR, ptBR, ruRU, zhCN, zhTW]
```

`acquire` uploads English and terminology artifacts. Every matrix job downloads them and uploads `translation-${locale}` with `if: always()`. Matrix jobs run sequentially so independently started Gemini processes cannot violate the shared five-request-starts-per-minute policy. `aggregate` uses `if: always()` so it can produce one complete diagnostic result, but it may modify release files only when all ten artifacts say `PASS`. Preserve dry-run behavior: validate and build the release state without committing, pushing, tagging, or uploading to CurseForge.
- [ ] **Step 4: Run workflow-contract tests and confirm they pass.**

### Task 6: Verify the complete release contract

**Files:**
- Modify only if a failing contract exposes a required correction.

- [ ] **Step 1: Run `python -m unittest discover -s tests -v` and require zero failures.**
- [ ] **Step 2: Run `git diff --check`.**
- [ ] **Step 3: Review the complete diff and confirm acquisition cannot write release files, English-only artifacts cannot be committed, matrix jobs are independent, and aggregation fails closed.**
- [ ] **Step 4: Dispatch one manual dry run and verify acquisition, all ten locale jobs, aggregation diagnostics, artifact retention, and absence of commits/releases.**

### Task 7: Prepare the separately authorized delivery

**Files:**
- Stage only the files listed in Tasks 1–5 after the human explicitly authorizes staging and committing.

- [ ] **Step 1: Report the verified diff and dry-run evidence to the human.**
- [ ] **Step 2: Await explicit authorization before `git add`, `git commit`, or `git push`.**
- [ ] **Step 3: If authorized, create one focused Conventional Commit such as `fix(automation): translate locales in parallel`.**
- [ ] **Step 4: Push only after rechecking the repository’s addon-release path filters and confirming this automation-only change cannot trigger CurseForge.**
