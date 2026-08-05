/// <reference types="node" />

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const projectRoot = process.cwd();

function resolveProjectFile(relativePath: string): string {
  return resolve(projectRoot, relativePath);
}

function readProjectFile(relativePath: string): string {
  return readFileSync(resolveProjectFile(relativePath), "utf8");
}

describe("Tailwind styling migration", () => {
  it("builds Tailwind through Vite", () => {
    // Given the web app package and Vite configuration
    const packageJson = JSON.parse(readProjectFile("package.json")) as {
      devDependencies: Record<string, string>;
    };
    const viteConfig = readProjectFile("vite.config.ts");

    // When their Tailwind integration is inspected
    const tailwindVersion = packageJson.devDependencies.tailwindcss;
    const tailwindViteVersion =
      packageJson.devDependencies["@tailwindcss/vite"];

    // Then Tailwind and its Vite plugin are configured
    expect(tailwindVersion).toBe("4.3.0");
    expect(tailwindViteVersion).toBe("4.3.0");
    expect(viteConfig).toContain('from "@tailwindcss/vite"');
    expect(viteConfig).toContain("tailwindcss()");
  });

  it("uses one Tailwind theme entry file", () => {
    // Given the global style entry points
    const mainSource = readProjectFile("src/main.ts");
    const tailwindPath = resolveProjectFile("src/styles/tailwind.css");

    // When their source is inspected
    const tailwindEntryExists = existsSync(tailwindPath);

    // Then main imports the one Tailwind theme entry
    expect(tailwindEntryExists).toBe(true);

    const tailwindSource = readFileSync(tailwindPath, "utf8");

    expect(mainSource).toContain('import "@/styles/tailwind.css"');
    expect(tailwindSource).toContain('@import "tailwindcss"');
    expect(tailwindSource).toContain("@theme");
  });

  it("keeps component styling in utility classes", () => {
    // Given every styled Vue component
    const componentPaths = [
      "src/App.vue",
      "src/views/PatchNotesView.vue",
      "src/components/PatchSection.vue",
    ];

    // When their source is inspected
    const componentSources = componentPaths.map(readProjectFile);

    // Then none contains a style block or inline style binding
    for (const componentSource of componentSources) {
      expect(componentSource).not.toContain("<style");
      expect(componentSource).not.toContain(":style=");
    }
  });

  it("removes the Sass styling system", () => {
    // Given the package manifest and legacy style paths
    const packageJson = JSON.parse(readProjectFile("package.json")) as {
      devDependencies: Record<string, string>;
    };
    const globalScssPath = resolveProjectFile("src/styles/global.scss");
    const tokensScssPath = resolveProjectFile("src/styles/_tokens.scss");

    // When their state is inspected
    const sassVersion = packageJson.devDependencies.sass;

    // Then Sass and SCSS files are absent
    expect(sassVersion).toBeUndefined();
    expect(existsSync(globalScssPath)).toBe(false);
    expect(existsSync(tokensScssPath)).toBe(false);
  });
});
