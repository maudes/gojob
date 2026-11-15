/** Helpers shared by server and browser. No Node-only imports here. */
import { diffWordsWithSpace } from "diff";

const EMAIL = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
const PHONE = /(?<![\w/.-])\+?\d[\d\s().-]{7,}\d(?![\w/-])/g;

/** Replace contact details with placeholders. Applied before any text reaches a model or the screen. */
export function redact(text: string): string {
  return text.replace(EMAIL, "[email]").replace(PHONE, (m) => {
    const digits = m.replace(/\D/g, "");
    // Leave years and year ranges such as "2019 - 2023" alone.
    if (digits.length < 9 || /^\d{4}\s*[-–.]\s*\d{4}$/.test(m.trim())) return m;
    return "[phone]";
  });
}

export function normalise(s: string): string {
  return s
    .toLowerCase()
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[‐‑‒–—]/g, "-")
    .replace(/^[\s•·▪●○◦*\-]+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** True when `quote` appears word for word in `source`, ignoring whitespace and bullet glyphs. */
export function isVerbatim(quote: string, source: string): boolean {
  const q = normalise(quote);
  if (!q) return true;
  return normalise(source).includes(q);
}

export type DiffOp = { type: "same" | "del" | "ins"; text: string };

/** Word-level diff showing both what was removed and what was added, like tracked changes. */
export function diffOps(before: string, after: string): DiffOp[] {
  const out: DiffOp[] = [];
  for (const part of diffWordsWithSpace(before, after)) {
    // Whitespace-only edits carry no marks: removed spacing is dropped, added spacing reads as unchanged.
    const blank = !/\S/.test(part.value);
    if (blank && part.removed) continue;
    const type: DiffOp["type"] = blank ? "same" : part.removed ? "del" : part.added ? "ins" : "same";
    const last = out[out.length - 1];
    if (last && last.type === type) last.text += part.value;
    else out.push({ type, text: part.value });
  }
  return out;
}

/** Matching gate tiers for one JD. */
export function tier(average: number, min: number): "apply" | "tune" | "risky" {
  if (average >= 80 && min >= 60) return "apply";
  return average >= 60 ? "tune" : "risky";
}

/** Apply accepted changes to plain text. Returns the new text and the changes that could not be found. */
export function applyToText(text: string, changes: { find: string; replace: string }[]) {
  const missed: string[] = [];
  let out = text;
  for (const c of changes) {
    if (c.find && out.includes(c.find)) out = out.replace(c.find, () => c.replace);
    else missed.push(c.find);
  }
  return { text: out, missed };
}

export const TRACKER_COLUMNS = [
  "company", "position", "location", "jobLink", "oneLine", "matchingScore", "applyDate", "networkTarget", "status", "notes",
] as const;

/** One tab-separated line in the sheet's column order, ready to paste into Google Sheets. */
export function trackerTSV(row: Record<(typeof TRACKER_COLUMNS)[number], string>): string {
  return TRACKER_COLUMNS.map((k) => String(row[k] ?? "").replace(/[\t\n\r]+/g, " ")).join("\t");
}

export function today(): string {
  const d = new Date();
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
