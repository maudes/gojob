import { NextResponse } from "next/server";
import { docxToText } from "@/lib/docx";
import { driveDownloadUrl, fileToText } from "@/lib/extract";
import { updateDB } from "@/lib/store";
import { redact } from "@/lib/text";

const MAX = 120000;
const fail = (error: string, status = 400) => NextResponse.json({ error }, { status });

async function bytesToText(name: string, bytes: Uint8Array): Promise<string> {
  const lower = name.toLowerCase();
  if (lower.endsWith(".docx")) return docxToText(bytes);
  if (lower.endsWith(".csv") || lower.endsWith(".tsv")) return new TextDecoder().decode(bytes).trim();
  return fileToText(name, bytes);
}

async function store(text: string, name: string) {
  if (text.trim().length < 80) return fail("Not enough text was found. Paste your stories instead.", 422);
  if (text.length > MAX) return fail("The story bank is longer than 120,000 characters. Keep the stories you practise with and remove the rest.", 422);
  const coach = await updateDB((db) => {
    db.coach.storyBank = { text: redact(text), name, updatedAt: new Date().toISOString() };
    return db.coach;
  });
  return NextResponse.json({ coach });
}

/** Story bank: an uploaded file, a Google Docs / Sheets / Drive link, or pasted text. */
export async function POST(req: Request) {
  try {
    if ((req.headers.get("content-type") ?? "").includes("multipart/form-data")) {
      const file = (await req.formData()).get("file");
      if (!(file instanceof File)) return fail("No file received.");
      if (file.size > 8 * 1024 * 1024) return fail("File is larger than 8 MB.");
      return store(await bytesToText(file.name, new Uint8Array(await file.arrayBuffer())), file.name);
    }
    const body = (await req.json()) as { link?: string; text?: string };
    if (typeof body.text === "string") return store(body.text, "Pasted text");
    const target = driveDownloadUrl(body.link ?? "");
    if (!target) return fail("That link is not valid.");
    const res = await fetch(target, { redirect: "follow", signal: AbortSignal.timeout(20000) });
    const type = res.headers.get("content-type") ?? "";
    // A private Google file answers with its sign-in page instead of the content.
    if (!res.ok || type.includes("text/html"))
      return fail("This link could not be read. In Google Drive set sharing to \"Anyone with the link\", or download the file and upload it here.", 422);
    const bytes = new Uint8Array(await res.arrayBuffer());
    const name = type.includes("csv") ? "Google Sheet.csv" : type.includes("pdf") ? "Drive file.pdf" : type.includes("wordprocessingml") ? "Drive file.docx" : "Google Doc.txt";
    return store(await bytesToText(name, bytes), name.replace(/\.\w+$/, ""));
  } catch (err) {
    return fail(err instanceof Error ? err.message : "Could not read the story bank.", 422);
  }
}
