import { NextResponse } from "next/server";
import { docxToPdf, textToDocx } from "@/lib/docx";
import { exportDocx, hasSource } from "@/lib/files";
import { readDB } from "@/lib/store";

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

/** Download the resume or cover letter as .docx or PDF. */
export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  const db = await readDB();
  const record = db.analyses.find((a) => a.id === q.get("id"));
  const company = (record?.analysis.output.meta.company || "").replace(/[^\w -]/g, "").trim();
  let docx: Uint8Array;
  let name: string;

  if (q.get("kind") === "letter") {
    const letter = record?.actions.coverLetter?.output.letter;
    if (!letter) return NextResponse.json({ error: "No cover letter yet." }, { status: 404 });
    docx = await textToDocx(letter);
    name = `Cover letter${company ? ` - ${company}` : ""}`;
  } else {
    const jdScope = `jd-${record?.id}`;
    const useJd = Boolean(record) && (await hasSource(jdScope));
    docx = await exportDocx(useJd ? jdScope : "master", record?.tailoredText ?? db.profile.resumeText);
    name = `Resume${company ? ` - ${company}` : ""}`;
  }

  if (q.get("format") === "pdf") {
    const pdf = await docxToPdf(docx);
    if (!pdf)
      return NextResponse.json(
        { error: "PDF export needs LibreOffice on this computer (free: brew install --cask libreoffice). Until then, download the .docx and export it as PDF from Google Docs or Word." },
        { status: 501 },
      );
    return new NextResponse(Buffer.from(pdf), { headers: { "content-type": "application/pdf", "content-disposition": `attachment; filename="${name}.pdf"` } });
  }
  return new NextResponse(Buffer.from(docx), { headers: { "content-type": DOCX, "content-disposition": `attachment; filename="${name}.docx"` } });
}
