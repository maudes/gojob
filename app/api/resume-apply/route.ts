import { NextResponse } from "next/server";
import { applyToSource, copySource, hasSource } from "@/lib/files";
import { updateDB } from "@/lib/store";
import { applyToText } from "@/lib/text";

type Change = { find: string; replace: string };
type Body = { scope: "profile" | "jd"; id?: string; accepted: Change[]; rejected?: string[] };

/** Write the accepted tracked changes into the resume text and into the stored file. */
export async function POST(req: Request) {
  const body = (await req.json()) as Body;
  const accepted = (body.accepted ?? []).filter((c) => c && typeof c.find === "string" && typeof c.replace === "string" && c.find);
  const handled = new Set([...accepted.map((c) => c.find), ...(body.rejected ?? [])]);
  const jdScope = `jd-${body.id}`;
  if (body.scope === "jd" && accepted.length && !(await hasSource(jdScope))) await copySource("master", jdScope);
  const missedInFile = accepted.length ? await applyToSource(body.scope === "jd" ? jdScope : "master", accepted) : [];

  const result = await updateDB((db) => {
    if (body.scope === "profile") {
      const applied = applyToText(db.profile.resumeText, accepted);
      db.profile.resumeText = applied.text;
      if (accepted.length) db.profile.savedAt = db.profile.resumeUpdatedAt = new Date().toISOString();
      if (db.health) db.health.check.output.changes = db.health.check.output.changes.filter((c) => !handled.has(c.find));
      return { profile: db.profile, health: db.health, missedInText: applied.missed };
    }
    const record = db.analyses.find((a) => a.id === body.id);
    if (!record) return null;
    const applied = applyToText(record.tailoredText ?? db.profile.resumeText, accepted);
    if (accepted.length) record.tailoredText = applied.text;
    const ft = record.actions.fineTune;
    if (ft) ft.output.changes = ft.output.changes.filter((c) => !handled.has(c.find));
    return { record, missedInText: applied.missed };
  });
  if (!result) return NextResponse.json({ error: "Analysis not found." }, { status: 404 });
  return NextResponse.json({ ...result, missedInFile });
}
