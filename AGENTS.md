codex resume 019fbd62-2363-74e0-84b2-37ae3e27a799

# BetterPatchNotes Agent Guidance

## Class Browser Behavior

Keep all 13 class icons visible beside the Live and PTR tabs. Use Blizzard's
built-in class artwork, and show the localized class name in each icon's hover
tooltip. Dim icons without class changes in the active channel, but keep them
selectable.

For the player's actual class, retain the player-focused layout: current
specialization and class-wide notes expanded, with other specializations
collapsed. For any other selected class, display all specialization-specific
and class-wide changes together in one expanded class section. Dungeon and
raid sections remain independent of class selection. Switching Live/PTR must
preserve the selected class for that open window. Closing and reopening the
window must reset to the player's actual class.

Class browsing is transient UI state. It must not be added to SavedVariables,
and closing the window must not mark the browsed class as seen. Seen-state
updates always use the player's actual class.

## Language and Locale Policy

Treat `data/retail-patch-notes.json` as the authority for which patch-note
languages are actually populated. The valid canonical patch-note locales are
`deDE`, `en`, `esES`, `esMX`, `frFR`, `itIT`, `koKR`, `ptBR`, `ruRU`, `zhCN`,
and `zhTW`. Do not add another locale without updating the schema validators,
runtime mapping, localization tables, terminology registry, skills, and tests.

Store English once: enUS and enGB clients map to `en`. Agents must never store
separate `enUS` or `enGB` localizations. At runtime, normalize those English
client codes to `en`, then select the exact client locale when that
localization exists. Otherwise, display the canonical English fallback and its
fallback indicator.

Keep regional variants independent. `esES` and `esMX` remain separate; do not
copy one regional Spanish localization into the other. `zhCN` and `zhTW`
remain separate; do not copy them, merge them, or use automatic character
conversion as a substitute for a verified localization. Regional vocabulary
and official WoW terminology must be verified for the exact locale.

Interface labels and patch-note content are separate localization layers. The
presence of translated buttons, tabs, headings, or class names does not mean
that the bundled notes are translated. In particular, interface localization
does not prove patch-note localization. Before reporting language coverage,
inspect every record's `localizations` object in the canonical JSON. An agent
must not claim that every language has patch-note content unless that data
inspection proves it.

Use this trust order for every non-English locale:

1. A current official Blizzard localization that matches the English baseline.
2. A validated unofficial translation grounded in official localized game
   terminology.
3. A documented English fallback when neither localized option can be safely
   published.

English is the authoritative comparison baseline and final fallback, not the
preferred result for non-English clients. Agent translations must preserve
numbers, percentages, durations, bullet order, conditions, and semantic
direction. Store their provenance using `translationType`, `translatedFrom`,
and `terminologySourceUrls`. Official localized text always replaces an agent
translation; an agent translation must never replace official text. Source
names and URLs remain internal provenance and must not appear in the addon UI.

For every refresh, record exactly one outcome per target locale in the locale
completion matrix: official localization, validated unofficial translation,
or documented English fallback with a reason. The agent must not complete a
refresh until every target locale is classified. Uncertain game terminology
must remain English and be reported; never guess a localized game term.

## Public Website Policy

The public Vue website lives in `web-app/` and is deployed by Netlify. It reads
the same canonical `data/retail-patch-notes.json` used to generate the addon
data. Generated website data under `web-app/src/generated/` must remain
untracked and must be created during development and production builds.

A web-only push must not trigger the CurseForge release workflow and does not
require an addon version bump. The CurseForge workflow must use GitHub path
filters limited to addon runtime and changelog files. A push containing an
addon runtime or packaged-data change is still an addon release and must
follow every version, validation, and changelog gate below.

## GitHub Push Release Rule

Every push to GitHub that includes addon runtime or packaged-data changes
automatically deploys to CurseForge and is therefore an addon release. Before
such a push:

1. Compare the local version with `origin/main`.
2. Increment the semantic version's patch component exactly once.
3. Keep `BetterPatchNotes.toc`, `Addon.lua`, and the version shown in
   `README.md` synchronized.
4. Add a newest-first, user-relevant entry to `changelog.txt` for that version.
5. Run the complete test suite and confirm the synchronized version is newer
   than `origin/main`.

Refuse to push when the version still matches `origin/main`, when the version
files disagree, when the changelog entry is missing, or when tests fail.

## Exact Refresh Command Authorization

Treat either of these case-insensitive messages, after trimming surrounding
whitespace, as an exact release command:

- the standalone command `refresh`
- the standalone command `refresh data`

Either command is explicit authorization for `git add`, `git commit`, and
`git push origin main` only as part of the complete patch-note refresh workflow
below. No additional confirmation is required before those Git operations when
qualifying packaged data changed and every release gate passed.

Other wording is not this release command. Requests such as "check for
updates", "are there new notes?", "scan the sources", or "fetch and report"
are read-only unless the user separately authorizes modification and release.
Do not infer release authorization from acknowledgements, shorthand, or
positive feedback.

## Patch-Note Refresh Release Workflow

For an exact refresh command, complete these phases in order. Never skip a
phase and never release data that has not been manually reviewed.

### 1. Preflight

1. Confirm the repository is on `main`, inspect `git status`, fetch
   `origin/main`, and compare local and remote history. Stop if the branch has
   diverged or is not safe to update.
2. Preserve all existing user changes. If tracked changes would overlap or be
   mixed into the refresh release, stop and report them. Do not stash, reset,
   discard, or include unrelated work.
3. Record the versions in `origin/main`, `BetterPatchNotes.toc`, `Addon.lua`,
   `README.md`, and the newest `changelog.txt` entry before editing anything.

### 2. Research and generate data

1. Read and follow `skills/fetch-retail-patch-notes/SKILL.md` in full. Its
   Blizzard-first source priority, canonical-source review, localization,
   current-build retention, content-safety, and validation rules are
   mandatory.
2. Read and follow `skills/translate-patch-notes/SKILL.md` in full whenever a
   current official Blizzard localization is unavailable. Agent-generated text
   must be marked as an unofficial translation from `en`, grounded in
   official Blizzard terminology, and validated before publication.
3. Determine the installed Retail build from `.build.info`, the refresh date,
   and the rolling 14-day window. Live records must match the installed Retail
   patch exactly. PTR records may target only a newer patch.
4. Search both Live and PTR sources and every supported official locale. Use
   official Blizzard notes whenever available. Secondary sources may fill a
   verified gap but must never replace or override Blizzard.
5. Apply a localization-first workflow. English is the fallback language and
   the authoritative comparison baseline, not the preferred player-facing
   result. Collect `en`, then seek an official localization for every target
   locale and compare it with `en` for scope, dates, numbers, direction, and
   omissions. If official localized notes are unavailable or incomplete, make
   a validated unofficial translation. Use an English fallback only if both
   options fail, and record a documented fallback reason.
   The canonical data has one English locale: enUS and enGB clients map to
   `en`; never store separate `enUS` or `enGB` localizations.
6. Maintain this completion matrix for every target locale:

   ```text
   locale | official | agent translation | English fallback | reason
   ```

   Exactly one result column must apply per locale. The agent must not complete
   the refresh until every locale is classified and each English fallback has
   a documented fallback reason.
7. Preserve the pre-refresh JSON and Lua contents, collect qualifying class,
   dungeon, and raid records, and run the skill's refresh command. Treat
   `data/retail-patch-notes.json` as canonical; never edit
   `PatchNotesData.lua` manually.
8. Retain only effective dates inside the rolling 14-day window. In schema
   version 5, every localized `change` value must be a non-empty array of
   strings, including a one-item change.
9. Confirm the command published synchronized JSON and Lua. Review its
   `added`, `skipped`, `promoted`, `localized`, `ambiguous`, and `removed`
   counts. Review the translation report's official and agent translation
   counts, English fallbacks, and uncertain terminology. Keep source names and
   URLs as internal provenance; they must not appear in the addon UI.

### 3. No-change stop condition

Compare meaningful packaged content with the pre-refresh data. A
timestamp-only difference is not a packaged data change.

If no qualifying packaged data changed, restore any timestamp-only or
generated-file differences to their exact pre-refresh contents and stop the
entire operation. Report the installed build, Live and PTR channels, searched
date range, sources checked, locales and English fallbacks, and refresh counts.
Do not bump the version. Do not modify `changelog.txt`. Do not stage, commit,
or push. Do not create a manual release archive, and leave the working tree
clean apart from user changes that existed before the refresh.

### 4. Prepare a real data release

Only continue when reviewed packaged data actually changed.

1. You must increment the semantic version's patch component exactly once
   relative to `origin/main`, such as `0.2.5` to `0.2.6`.
2. Synchronize the new version in `BetterPatchNotes.toc`, `Addon.lua`, the
   version displayed in `README.md`, and the newest `changelog.txt` entry. Do
   not change the TOC interface number merely to bump the addon version; the
   interface number tracks WoW client compatibility separately.
3. Add a newest-first changelog entry in this format:

   ```text
   Version 0.2.6 - YYYY-MM-DD
   - Data: Live 12.0.7; PTR 12.1
   - Added or updated: concise description and record counts
   - Removed: concise reason and record count, or "None"
   - Locales: official and agent translations added; identify English fallbacks
   ```

   Include only verified, player-relevant changes. Never add an empty release
   entry.

### 5. Validate before Git operations

1. Run `python -m unittest discover -s tests -v`.
2. Confirm `PatchNotesData.lua` matches canonical JSON exactly and the refresh
   command left no temporary files.
3. Confirm all release versions agree, the new version is newer than
   `origin/main`, the changelog entry exists, and `git diff --check` passes.
4. Review the complete diff. Confirm that runtime release files only may be
   shipped by CI:
   `BetterPatchNotes.toc`, `Addon.lua`, `Localization.lua`,
   `PatchNotesData.lua`, `Data.lua`, `State.lua`, `Window.lua`,
   `MinimapButton.lua`, `Core.lua`, and `changelog.txt`. Do not include
   development files such as `tests`, `skills`, `data`, `AGENTS.md`, caches,
   or Git metadata in the packaged addon.
5. Stop without staging when any test or release gate fails. Report the exact
   failure and preserve the working files for diagnosis.

### 6. Stage, commit, and push

1. Use explicit paths with `git add`. Stage only the tracked files required by
   this data release, normally `PatchNotesData.lua`, `BetterPatchNotes.toc`,
   `Addon.lua`, `README.md`, and `changelog.txt`. Do not stage unrelated files.
2. Inspect `git diff --cached --check`, the staged diff, and staged file list.
   Refuse to continue if the scope or versions are wrong.
3. Create one focused commit with this subject, replacing the date:

   ```text
   data: refresh retail patch notes for YYYY-MM-DD
   ```

4. Push exactly with `git push origin main`. The version must not be bumped a
   second time between commit and push.

### 7. Verify GitHub and CurseForge

1. Monitor the triggered GitHub Actions release run until it completes. A
   successful Git push alone is not a successful release.
2. On success, inspect the run log and confirm the CurseForge file ID and the
   new `vVERSION` release tag. Confirm local `main` matches `origin/main`, then
   report the commit, version, test count, workflow result, CurseForge file ID,
   release tag, and whether the file is awaiting CurseForge review.
3. On failure, retrieve the exact failing step, HTTP status, and safe response
   body. Follow systematic debugging and report the root cause. Do not make
   another push, create another version bump, or blindly rerun the workflow
   until the failure is understood.

GitHub Actions creates the runtime-only ZIP and uploads it to CurseForge. Do
not create a manual release archive or a Desktop ZIP during this workflow.

## Automatic Blizzard-Only Refresh

GitHub Actions runs the unattended refresh every day at **04:07
Europe/Copenhagen**. This automation is Blizzard-only: it may read only the
reviewed official hosts and sources declared in `automation/sources.json`.
Wowhead, MMO-Champion, search results, videos, and other secondary sources are
never eligible for an automatic release.

The automated release is all-or-nothing. English is collected as the factual
baseline, Gemini may translate it, and all locales must pass terminology and
translation validation. An English fallback, missing locale, unverified class
or specialization terminology, unknown Blizzard author, unknown document
structure, unsafe redirect, mismatched build, or ambiguous category blocks
publication. Unknown ability, boss, NPC, encounter, dungeon, or raid names may
remain exactly English as a preserved English terminology warning. Such
warnings do not block publication, but numbers, direction, conditions, and
protected terms must remain unchanged. Record warning counts per locale in the
audit artifact, GitHub summary, and release changelog.

If there is no meaningful packaged-data change after ignoring only the
top-level `updatedAt`, the workflow must restore the original release bytes and
stop. It must not bump a version, edit the changelog, commit, tag, upload to
CurseForge, or cause a Netlify data release.

The workflow uses the repository `GITHUB_TOKEN` and must not use a personal
access token. Required repository secrets are `GEMINI_API_KEY` and
`CF_API_TOKEN`; `GEMINI_API_KEY2` is an optional translation fallback. Secret
values must never enter logs, artifacts, issues, data files, or commits.

### Exact automated commit allowlist

An automatic data-release commit may change only:

- `BetterPatchNotes.toc`
- `Addon.lua`
- `README.md`
- `changelog.txt`
- `PatchNotesData.lua`
- `data/retail-patch-notes.json`

The workflow must stage these as explicit paths and must never use
`git add .`. GitHub Actions calls the CurseForge workflow with the exact
committed SHA. The existing runtime-only package allowlist remains separate
and must not include automation, source data, tests, skills, or documentation.

If deployment fails after the release commit, the workflow must not create a
second version bump or another data commit. It must preserve the commit, update
the marked automation issue with safe diagnostics, and wait for a reviewed
retry of that exact release state.

Any parser or source-shape failure requires manual parser review. Compare the
current official Blizzard response with the captured fixture, update only the
minimal adapter and fixture needed for the reviewed structure, run every test,
and use a dry run before publication. Never relax fail-closed checks merely to
make a scheduled run pass.
