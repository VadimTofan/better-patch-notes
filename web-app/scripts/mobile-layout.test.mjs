import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readSource(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

// Describe: simple centered application shell
test("shell stays centered and keeps the locale control compact", () => {
  // Given the application shell
  const appSource = readSource("../src/App.vue");

  // When its Tailwind layout is inspected
  const usesCenteredContent = appSource.includes("mx-auto max-w-4xl");
  const hidesTheMobileLabel = appSource.includes("hidden text-muted sm:inline");

  // Then the page is centered and the locale label yields on narrow screens
  assert.equal(usesCenteredContent, true);
  assert.equal(hidesTheMobileLabel, true);
});

// Describe: responsive class and channel navigation
test("navigation uses a compact responsive class grid", () => {
  // Given the patch-note view
  const viewSource = readSource("../src/views/PatchNotesView.vue");

  // When its navigation utilities are inspected
  const classGrid = "grid grid-cols-4 gap-2 sm:grid-cols-7 lg:grid-cols-13";
  const channelButton = "rounded-lg px-4 py-2 font-semibold text-muted";

  // Then classes reflow at standard breakpoints and channel controls stay simple
  assert.equal(viewSource.includes(classGrid), true);
  assert.equal(viewSource.includes(channelButton), true);
});

// Describe: readable patch-note cards on narrow viewports
test("patch-note cards stack metadata before the small breakpoint", () => {
  // Given the patch-section component
  const sectionSource = readSource("../src/components/PatchSection.vue");

  // When its card layout is inspected
  const responsiveHeader = "flex flex-col gap-2 sm:flex-row sm:justify-between";
  const compactCard =
    "rounded-lg border border-line-soft bg-surface-raised p-4";

  // Then card metadata stacks and the card uses concise standard spacing
  assert.equal(sectionSource.includes(responsiveHeader), true);
  assert.equal(sectionSource.includes(compactCard), true);
});

// Describe: patch-note list markers after Tailwind Preflight
test("patch-note changes retain bullet markers", () => {
  // Given the Tailwind-styled patch section
  const sectionSource = readSource("../src/components/PatchSection.vue");

  // When the changes list utilities are inspected
  const preservesBullets = sectionSource.includes("list-disc");

  // Then each patch-note change keeps its visible bullet
  assert.equal(preservesBullets, true);
});

// Describe: details disclosure marker after Tailwind Preflight
test("patch-note summaries use only the custom disclosure marker", () => {
  // Given the Tailwind-styled patch section
  const sectionSource = readSource("../src/components/PatchSection.vue");

  // When the summary utilities are inspected
  const hidesNativeMarker = sectionSource.includes("list-none");

  // Then the native marker does not duplicate the custom chevron
  assert.equal(hidesNativeMarker, true);
});
