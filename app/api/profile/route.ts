import { NextResponse } from "next/server";
import { htmlToText, isSafeUrl } from "@/lib/extract";
import { copySource, hasSource, saveSource } from "@/lib/files";
import { emptyProfile, Profile } from "@/lib/schemas";
import { readDB, updateDB } from "@/lib/store";
import { redact } from "@/lib/text";

async function scan(url: string): Promise<string> {
  const safe = isSafeUrl(url);
  if (!safe) return "";
  try {
    const res = await fetch(safe, { headers: { "user-agent": "Mozilla/5.0 (compatible; profile-reader)" }, signal: AbortSignal.timeout(12000) });
    return res.ok ? htmlToText(await res.text()).slice(0, 12000) : "";
  } catch {
    return "";
  }
}

export async function PUT(req: Request) {
  const body = await req.json();
  const parsed = Profile.safeParse({ ...emptyProfile, ...body, fullTimeOnly: true });
  if (!parsed.success) return NextResponse.json({ error: "Invalid profile." }, { status: 400 });
  const previous = (await readDB()).profile;
  const p = parsed.data;

  // A newly uploaded file becomes the master copy only when the profile is saved.
  if (body.promoteUpload && (await hasSource("pending"))) await copySource("pending", "master");
  else if (!(await hasSource("master")) || (!body.promoteUpload && p.resumeText !== previous.resumeText)) {
    // Resume was pasted or edited as text: the text itself is the source for downloads.
    await saveSource("master", "other", p.resumeText);
    p.resumeFormat = "other";
  }

  const websiteText =
    p.websiteUrl && (p.websiteUrl !== previous.websiteUrl || !previous.websiteText) ? await scan(p.websiteUrl) : p.websiteUrl ? previous.websiteText : "";

  const profile = {
    ...p,
    // Contact details are stripped on the way in, so they are never shown or sent to a model.
    resumeText: redact(p.resumeText),
    linkedinText: redact(p.linkedinText),
    websiteText: redact(websiteText),
    resumeUpdatedAt:
      body.promoteUpload || redact(p.resumeText) !== previous.resumeText || !previous.resumeUpdatedAt
        ? new Date().toISOString()
        : previous.resumeUpdatedAt,
    savedAt: new Date().toISOString(),
  };
  await updateDB((db) => {
    db.profile = profile;
  });
  return NextResponse.json({ profile, websiteScanned: Boolean(websiteText) });
}
