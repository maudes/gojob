import { NextResponse } from "next/server";
import { docxToText } from "@/lib/docx";
import { fileToText } from "@/lib/extract";
import { saveSource } from "@/lib/files";
import { updateDB } from "@/lib/store";
import { redact } from "@/lib/text";

/** Resume upload. Without `id` it is the profile resume (pending until saved); with `id` it is the revised resume for one JD. */
export async function POST(req: Request) {
  const id = new URL(req.url).searchParams.get("id");
  const form = await req.formData();
  const file = form.get("file");
  if (!(file instanceof File)) return NextResponse.json({ error: "No file received." }, { status: 400 });
  if (file.size > 8 * 1024 * 1024) return NextResponse.json({ error: "File is larger than 8 MB." }, { status: 400 });
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const isDocx = file.name.toLowerCase().endsWith(".docx");
    const text = isDocx ? await docxToText(bytes) : await fileToText(file.name, bytes);
    if (text.length < 200)
      return NextResponse.json(
        { error: "Could not read enough text from this file (it may be a scanned image). Upload a .docx or paste the text." },
        { status: 422 },
      );
    const scope = id ? `jd-${id}` : "pending";
    await saveSource(scope, isDocx ? "docx" : "other", isDocx ? bytes : text);
    const clean = redact(text);
    if (id) {
      const record = await updateDB((db) => {
        const r = db.analyses.find((a) => a.id === id);
        if (r) r.tailoredText = clean;
        return r ?? null;
      });
      if (!record) return NextResponse.json({ error: "Analysis not found." }, { status: 404 });
      return NextResponse.json({ record });
    }
    return NextResponse.json({ text: clean, fileName: file.name, format: isDocx ? "docx" : "other" });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Could not read the file." }, { status: 422 });
  }
}
