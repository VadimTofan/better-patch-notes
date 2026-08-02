import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webAppDirectory = resolve(scriptDirectory, "..");
const defaultSourcePath = resolve(
  webAppDirectory,
  "..",
  "data",
  "retail-patch-notes.json",
);
const defaultOutputPath = resolve(
  webAppDirectory,
  "src",
  "generated",
  "patch-notes.json",
);

function validatePatchNotes(data) {
  if (data?.schemaVersion !== 5) {
    throw new Error("Patch-note schemaVersion must be 5.");
  }

  if (!Array.isArray(data.changes)) {
    throw new Error("Patch-note changes must be an array.");
  }

  for (const change of data.changes) {
    const englishChange = change?.localizations?.en?.change;

    if (
      typeof change?.id !== "string" ||
      !Array.isArray(englishChange) ||
      englishChange.length === 0 ||
      englishChange.some((item) => typeof item !== "string" || !item.trim())
    ) {
      throw new Error(`Invalid patch-note record: ${change?.id ?? "unknown"}.`);
    }
  }
}

export async function preparePatchNotes({
  sourcePath = defaultSourcePath,
  outputPath = defaultOutputPath,
} = {}) {
  const source = await readFile(sourcePath, "utf8");
  const data = JSON.parse(source);
  validatePatchNotes(data);

  await mkdir(dirname(outputPath), { recursive: true });

  const temporaryPath = `${outputPath}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
  await rename(temporaryPath, outputPath);

  return data;
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : "";
if (invokedPath === fileURLToPath(import.meta.url)) {
  const data = await preparePatchNotes();
  console.log(`Prepared ${data.changes.length} patch-note records.`);
}
