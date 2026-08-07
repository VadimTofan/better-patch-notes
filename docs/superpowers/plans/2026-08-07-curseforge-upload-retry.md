# CurseForge Upload Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retry one failed CurseForge upload after 10 minutes when the first
response has an HTTP status from 500 through 599.

**Architecture:** Keep the retry policy inside the existing release workflow's
upload step. Run at most two upload attempts, rebuild the metadata pipe for
each attempt, and leave validation, packaging, response parsing, and tag
publication unchanged.

**Tech Stack:** GitHub Actions YAML, Bash, curl, Python `unittest`

---

### Task 1: Specify the retry contract

**Files:**
- Modify: `tests/test_release_workflow.py`
- Test: `tests/test_release_workflow.py`

- [ ] **Step 1: Write the failing workflow contract test**

Add this test to `ReleaseWorkflowTests`:

```python
    def test_upload_retries_one_server_error_after_ten_minutes(self) -> None:
        # Given a transient CurseForge server failure
        expected_phrases = (
            "upload_attempt=1",
            '[[ "$upload_status" =~ ^5[0-9][0-9]$ ]]',
            '[ "$upload_attempt" -eq 1 ]',
            "sleep 600",
            "upload_attempt=2",
        )

        # When the CurseForge upload retry policy is inspected
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        # Then one retry is allowed after ten minutes for HTTP 5xx responses
        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
python -m unittest \
  tests.test_release_workflow.ReleaseWorkflowTests.test_upload_retries_one_server_error_after_ten_minutes \
  -v
```

Expected: `FAIL` because `upload_attempt=1` and the retry policy are absent.

### Task 2: Implement the bounded retry

**Files:**
- Modify: `.github/workflows/release.yml:216`
- Test: `tests/test_release_workflow.py`

- [ ] **Step 1: Replace the single upload attempt with a two-attempt loop**

Use this control flow around the existing `printf | curl` upload command:

```bash
          upload_attempt=1
          while true; do
            if upload_status="$(printf '%s' "$metadata" | \
              curl --fail-with-body --silent --show-error \
              --request POST \
              --output "$upload_response_file" \
              --write-out "%{http_code}" \
              --header "X-Api-Token: $CF_API_TOKEN" \
              --form "metadata=<-" \
              --form "file=@$archive" \
              "https://wow.curseforge.com/api/projects/1635519/upload-file")"
            then
              break
            fi

            echo "CurseForge upload failed with HTTP $upload_status"
            print_api_error "$upload_response_file"

            if [[ "$upload_status" =~ ^5[0-9][0-9]$ ]] \
              && [ "$upload_attempt" -eq 1 ]
            then
              echo "Retrying CurseForge upload in 10 minutes"
              sleep 600
              upload_attempt=2
              continue
            fi

            exit 1
          done
```

- [ ] **Step 2: Run the focused workflow tests**

Run:

```bash
python -m unittest tests.test_release_workflow -v
```

Expected: all release workflow tests pass.

- [ ] **Step 3: Run the complete Python suite**

Run:

```bash
python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 4: Verify the final diff**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only the workflow, its contract test, and this
plan are changed by this task. Do not stage, commit, or push any files.
