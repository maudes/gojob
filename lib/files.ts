/**
 * Resume files on disk. Each scope ("pending" upload, "master" profile resume, "jd-<id>"
 * tailored copy) holds either the original .docx or, for other formats, the full raw text.
 * These keep the contact details so downloads are complete; they are never sent to a model.
 */
import { promises as fs } from "node:fs";
import path from "node:path";
import { applyChangesToDocx, textToDocx } from "./docx";
import { applyToText } from "./text";

const DIR = path.join(process.cwd(), "data", "files");
const file = (scope: string, ext: "docx" | "txt") => path.join(DIR, `${scope.replace(/[^a-z0-9-]/gi, "")}.${ext}`);

const read = (p: string) => fs.readFile(p).then((b) => new Uint8Array(b), () => null);

export async function saveSource(scope: string, kind: "docx" | "other", bytes: Uint8Array | string) {
  await fs.mkdir(DIR, { recursive: true });
  await Promise.all([fs.rm(file(scope, "docx"), { force: true }), fs.rm(file(scope, "txt"), { force: true })]);
  await fs.writeFile(file(scope, kind === "docx" ? "docx" : "txt"), bytes);
}

export async function copySource(from: string, to: string) {
  await fs.mkdir(DIR, { recursive: true });
  for (const ext of ["docx", "txt"] as const) {
    await fs.rm(file(to, ext), { force: true });
    await fs.copyFile(file(from, ext), file(to, ext)).catch(() => undefined);
  }
}

export const hasSource = async (scope: string) =>
  (await read(file(scope, "docx"))) != null || (await read(file(scope, "txt"))) != null;

/** Apply accepted changes to the stored file for a scope. Returns finds that could not be placed. */
export async function applyToSource(scope: string, changes: { find: string; replace: string }[]): Promise<string[]> {
  const docx = await read(file(scope, "docx"));
  if (docx) {
    const result = await applyChangesToDocx(docx, changes);
    await fs.writeFile(file(scope, "docx"), result.bytes);
    return result.missed;
  }
  const raw = await fs.readFile(file(scope, "txt"), "utf8").catch(() => null);
  if (raw == null) return [];
  const result = applyToText(raw, changes);
  await fs.writeFile(file(scope, "txt"), result.text);
  return result.missed;
}

/** The resume as a .docx: the edited original when there is one, otherwise a clean rebuild. */
export async function exportDocx(scope: string, fallbackText: string): Promise<Uint8Array> {
  const docx = await read(file(scope, "docx"));
  if (docx) return docx;
  const raw = await fs.readFile(file(scope, "txt"), "utf8").catch(() => null);
  return textToDocx(raw ?? fallbackText);
}

export async function removeSource(scope: string) {
  await Promise.all([fs.rm(file(scope, "docx"), { force: true }), fs.rm(file(scope, "txt"), { force: true })]);
}
