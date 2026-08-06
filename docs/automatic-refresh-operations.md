# Automatic Refresh Operations

Better Patch Notes runs `.github/workflows/scheduled-refresh.yml` each day at
04:07 Europe/Copenhagen. It collects only allowlisted Blizzard news and forum
responses, resolves the current Retail build, keeps class/dungeon/raid changes
from the inclusive 14-day window, translates the English baseline, validates
all locales, and publishes one synchronized release when meaningful data
changed.

## Repository setup

Configure these encrypted GitHub Actions secrets in the repository settings:

- `GEMINI_API_KEY`: required Gemini authorization key.
- `GEMINI_API_KEY2`: optional fallback authorization key.
- `CF_API_TOKEN`: required CurseForge project token.

Do not store those values in Git, workflow inputs, issues, artifacts, or chat.
Google standard API keys cease to be accepted for this production workflow in
September 2026; migrate the Gemini secret to an authorization key before then.
The workflow uses the repository `GITHUB_TOKEN` for its bot commit and GitHub
issue lifecycle. It does not require or permit a personal access token.

## Manual dispatch and dry runs

Open **Actions → Refresh Blizzard patch notes → Run workflow**. Enable
`dry_run` for the first production check or after changing discovery,
extraction, translation, or release logic. A dry run performs collection and
coordination against temporary release-file copies. It creates no commit, tag,
CurseForge upload, or Netlify data deployment.

Download the `refresh-audit-RUN_ID` artifact and inspect:

- `automation-result.json` for outcome, current patch, counts, rejections, and
  official source URLs;
- `sources/` for the exact untrusted Blizzard responses parsed by the run;
- the workflow logs for test and build results without secret values.

An acceptable dry run ends in `NO_CHANGE` or `RELEASE_READY`. `BLOCKED` must be
understood and fixed before live publication.

## Outcomes

- `NO_CHANGE`: exact original release bytes are restored. No version,
  changelog, commit, tag, upload, or deploy is created.
- `RELEASE_READY`: the workflow validates the exact changed-file allowlist,
  commits once to `main`, invokes CurseForge for that exact SHA, and lets
  Netlify build the same commit.
- `BLOCKED`: the workflow uploads its audit and creates or updates the single
  issue containing `better-patch-notes-automation`.

A later successful or no-change run closes the marked issue. If CurseForge
fails after the bot commit, retain that commit and version. Diagnose and retry
the exact release state; never create another bump merely to retry deployment.

## Parser maintenance

Blizzard layout and endpoint changes intentionally fail closed. For a source
shape failure:

1. Open the URL from the audit using a read-only request.
2. Confirm the author, channel, patch, timestamps, headings, list hierarchy,
   and canonical URL directly on Blizzard.
3. Minimize the response into `tests/fixtures/blizzard/` and update its
   provenance manifest without cookies, tokens, or unrelated content.
4. Write a failing Given/When/Then regression test.
5. Make the smallest adapter change, run the complete Python and website
   suites, and complete a manual dry run.

Never solve a parser failure by accepting arbitrary authors, hosts, headings,
categories, redirects, MIME types, or response sizes.

## Release verification

For a real data change, verify the bot commit contains only the six approved
release paths, versions agree, the GitHub release job reports a CurseForge file
ID and `vVERSION` tag, and Netlify deploys the same commit. CurseForge may hold
the uploaded file for review. Publishing cannot force players' addon managers
to install the new file immediately.

Rollback is a new reviewed release, not a force-push or tag rewrite. Correct
the canonical data, bump once, validate again, and publish through the normal
release path.
