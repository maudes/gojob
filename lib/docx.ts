/**
 * Edit a .docx in place so the revised resume keeps the fonts and layout of the
 * file the user uploaded. Only the text inside existing runs is touched.
 */
import { execFile } from "node:child_process";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { Document, HeadingLevel, Packer, Paragraph, TextRun } from "docx";
import JSZip from "jszip";

const PARA = /<w:p[ >][\s\S]*?<\/w:p>/g;
/** Text runs and tabs, in document order. */
const PIECE = /<w:t(?:\s[^>]*)?>([^<]*)<\/w:t>|<w:tab\/>|<w:br\/>/g;

const unescapeXml = (s: string) =>
  s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, "&");
const escapeXml = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

type Piece = { start: number; end: number; text: string; editable: boolean };

function pieces(paraXml: string): Piece[] {
  const out: Piece[] = [];
  for (const m of paraXml.matchAll(PIECE)) {
    const editable = m[0].startsWith("<w:t") && !m[0].startsWith("<w:tab");
    out.push({ start: m.index, end: m.index + m[0].length, text: editable ? unescapeXml(m[1] ?? "") : " ", editable });
  }
  return out;
}

async function documentXml(bytes: Uint8Array) {
  const zip = await JSZip.loadAsync(bytes);
  const file = zip.file("word/document.xml");
  if (!file) throw new Error("This .docx file has no document body.");
  return { zip, xml: await file.async("string") };
}

/** Plain text of a .docx, one line per paragraph, built from the same runs we later edit. */
export async function docxToText(bytes: Uint8Array): Promise<string> {
  const { xml } = await documentXml(bytes);
  const lines: string[] = [];
  for (const m of xml.matchAll(PARA)) {
    const line = pieces(m[0]).map((p) => p.text).join("").replace(/\s+/g, " ").trim();
    lines.push(line);
  }
  return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

/** Find `needle` in `hay` ignoring differences in whitespace runs. Returns [start, end) in `hay`. */
function findLoose(hay: string, needle: string): [number, number] | null {
  const exact = hay.indexOf(needle);
  if (exact >= 0) return [exact, exact + needle.length];
  const map: number[] = [];
  let collapsed = "";
  for (let i = 0; i < hay.length; i++) {
    const ch = hay[i];
    if (/\s/.test(ch)) {
      if (collapsed.endsWith(" ") || collapsed === "") continue;
      collapsed += " ";
    } else collapsed += ch;
    map.push(i);
  }
  const want = needle.replace(/\s+/g, " ").trim();
  const at = want ? collapsed.indexOf(want) : -1;
  if (at < 0) return null;
  return [map[at], map[at + want.length - 1] + 1];
}

function replaceInParagraph(paraXml: string, find: string, replace: string): string | null {
  const ps = pieces(paraXml);
  const full = ps.map((p) => p.text).join("");
  const hit = findLoose(full, find);
  if (!hit) return null;
  const [s, e] = hit;
  let offset = 0;
  let placed = false;
  const edits: { piece: Piece; text: string }[] = [];
  for (const p of ps) {
    const pStart = offset;
    const pEnd = offset + p.text.length;
    offset = pEnd;
    if (!p.editable || pEnd <= s || pStart >= e) continue;
    const before = p.text.slice(0, Math.max(0, s - pStart));
    const after = p.text.slice(Math.max(0, Math.min(p.text.length, e - pStart)));
    edits.push({ piece: p, text: before + (placed ? "" : replace) + after });
    placed = true;
  }
  if (!placed) return null;
  let out = paraXml;
  for (const { piece, text } of edits.reverse())
    out = `${out.slice(0, piece.start)}<w:t xml:space="preserve">${escapeXml(text)}</w:t>${out.slice(piece.end)}`;
  return out;
}

export async function applyChangesToDocx(bytes: Uint8Array, changes: { find: string; replace: string }[]) {
  const { zip, xml } = await documentXml(bytes);
  const paras = xml.match(PARA) ?? [];
  const missed: string[] = [];
  const updated = [...paras];
  for (const c of changes) {
    let done = false;
    for (let i = 0; i < updated.length && !done; i++) {
      const next = replaceInParagraph(updated[i], c.find, c.replace);
      if (next != null) {
        updated[i] = next;
        done = true;
      }
    }
    if (!done) missed.push(c.find);
  }
  let i = 0;
  zip.file("word/document.xml", xml.replace(PARA, () => updated[i++]));
  return { bytes: await zip.generateAsync({ type: "uint8array" }), missed };
}

/** A clean, simple .docx for originals that were not Word files, and for cover letters. */
export async function textToDocx(text: string): Promise<Uint8Array> {
  const lines = text.replace(/\r/g, "").split("\n");
  const children = lines.map((raw, i) => {
    const line = raw.trim();
    if (i === 0 && line.length < 60 && !/[.!?]$/.test(line))
      return new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun(line)] });
    if (/^[A-Z][A-Z &/]{2,40}$/.test(line))
      return new Paragraph({ spacing: { before: 240, after: 80 }, children: [new TextRun({ text: line, bold: true })] });
    const bullet = line.match(/^[•·▪●○◦*-]\s+(.*)$/);
    if (bullet) return new Paragraph({ bullet: { level: 0 }, children: [new TextRun(bullet[1])] });
    return new Paragraph({ spacing: { after: line ? 80 : 0 }, children: [new TextRun(line)] });
  });
  const doc = new Document({
    styles: { default: { document: { run: { font: "Calibri", size: 22 } } } },
    sections: [{ properties: { page: { margin: { top: 1000, bottom: 1000, left: 1100, right: 1100 } } }, children }],
  });
  return new Uint8Array(await Packer.toBuffer(doc));
}

const SOFFICE = ["soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice", "/usr/bin/soffice", "/opt/homebrew/bin/soffice"];

/** Convert with LibreOffice when it is installed, so the PDF matches the .docx exactly. */
export async function docxToPdf(docx: Uint8Array): Promise<Uint8Array | null> {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "jhc-"));
  try {
    await fs.writeFile(path.join(dir, "resume.docx"), docx);
    for (const bin of SOFFICE) {
      try {
        await promisify(execFile)(bin, ["--headless", "--convert-to", "pdf", "--outdir", dir, path.join(dir, "resume.docx")], { timeout: 60000 });
        return new Uint8Array(await fs.readFile(path.join(dir, "resume.pdf")));
      } catch {
        /* try the next location */
      }
    }
    return null;
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
}
