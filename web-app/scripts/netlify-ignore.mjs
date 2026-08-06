import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptDirectory, "..", "..");

const exactWebsiteDependencies = new Set([
  "data/retail-patch-notes.json",
  "netlify.toml",
]);

function affectsWebsite(path) {
  return (
    path === "web-app" ||
    path.startsWith("web-app/") ||
    exactWebsiteDependencies.has(path)
  );
}

export function shouldIgnoreBuild(changedPaths) {
  return !changedPaths.some(affectsWebsite);
}

function readChangedPaths(cachedCommit, currentCommit) {
  const output = execFileSync(
    "git",
    ["diff", "--name-only", cachedCommit, currentCommit, "--"],
    {
      cwd: repositoryRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  return output.split(/\r?\n/u).filter(Boolean);
}

function getExitCode() {
  const cachedCommit = process.env.CACHED_COMMIT_REF;
  const currentCommit = process.env.COMMIT_REF;

  if (!cachedCommit || !currentCommit) {
    return 1;
  }

  try {
    const changedPaths = readChangedPaths(cachedCommit, currentCommit);

    return shouldIgnoreBuild(changedPaths) ? 0 : 1;
  } catch {
    return 1;
  }
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : "";
if (invokedPath === fileURLToPath(import.meta.url)) {
  process.exitCode = getExitCode();
}
