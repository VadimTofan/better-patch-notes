import assert from "node:assert/strict";
import { test } from "node:test";

import { shouldIgnoreBuild } from "./netlify-ignore.mjs";

// Describe: Netlify repository change detection
test("deploys for every website dependency", () => {
  // Given changes to each input that can affect the public website
  const websiteDependencies = [
    "web-app/src/App.vue",
    "data/retail-patch-notes.json",
    "netlify.toml",
  ];

  // When each changed path is evaluated
  const decisions = websiteDependencies.map((path) =>
    shouldIgnoreBuild([path]),
  );

  // Then Netlify is instructed to continue every build
  assert.deepEqual(decisions, [false, false, false]);
});

test("ignores an unrelated addon-only change", () => {
  // Given a commit that changes only addon runtime code
  const changedPaths = ["Window.lua"];

  // When the changed path is evaluated
  const shouldIgnore = shouldIgnoreBuild(changedPaths);

  // Then Netlify can skip the unaffected website build
  assert.equal(shouldIgnore, true);
});
