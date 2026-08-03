import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readSource(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

function getMobileRules(source) {
  const marker = "@media (max-width: 42rem)";
  const start = source.indexOf(marker);

  assert.notEqual(start, -1, `Expected ${marker} responsive rules`);

  const nextMediaQuery = source.indexOf("@media ", start + marker.length);

  return source.slice(
    start,
    nextMediaQuery === -1 ? source.length : nextMediaQuery,
  );
}

// Describe: compact global shell on mobile viewports
test("mobile shell keeps the sticky header and locale control compact", () => {
  // Given the global website styles
  const globalStyles = readSource("../src/styles/global.scss");

  // When the mobile breakpoint rules are inspected
  const mobileRules = getMobileRules(globalStyles);

  // Then the header and locale selector fit narrow screens
  assert.match(mobileRules, /\.topbar\s*{[^}]*min-height:\s*4rem;/s);
  assert.match(mobileRules, /\.locale__select\s*{[^}]*max-width:\s*9rem;/s);
});

// Describe: class and channel navigation on mobile viewports
test("mobile navigation shows four class columns and equal channel tabs", () => {
  // Given the patch-note view styles
  const viewSource = readSource("../src/views/PatchNotesView.vue");

  // When the mobile breakpoint rules are inspected
  const mobileRules = getMobileRules(viewSource);

  // Then every class remains visible without horizontal scrolling
  assert.match(
    mobileRules,
    /\.classrail__list\s*{[^}]*grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\);/s,
  );
  assert.match(
    mobileRules,
    /\.classrail__list\s*{[^}]*overflow-x:\s*visible;/s,
  );

  // And Live and PTR share the available width
  assert.match(mobileRules, /\.channels\s*{[^}]*width:\s*100%;/s);
  assert.match(
    mobileRules,
    /\.channels__button\s*{[^}]*justify-content:\s*center;[^}]*flex:\s*1;/s,
  );
});

// Describe: readable patch-note cards on mobile viewports
test("mobile patch-note cards use compact stacked metadata", () => {
  // Given the patch-section styles
  const sectionSource = readSource("../src/components/PatchSection.vue");

  // When the mobile breakpoint rules are inspected
  const mobileRules = getMobileRules(sectionSource);

  // Then section chrome and cards use the compact spacing contract
  assert.match(mobileRules, /\.section__summary\s*{[^}]*min-height:\s*4rem;/s);
  assert.match(mobileRules, /\.card\s*{[^}]*padding:\s*1rem;/s);

  // And metadata can wrap beneath the note title
  assert.match(mobileRules, /\.card__meta\s*{[^}]*flex-wrap:\s*wrap;/s);
});
