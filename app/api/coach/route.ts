import { NextResponse } from "next/server";
import { AgentError } from "@/lib/claude";
import { giveFeedback, nextQuestion, sessionLog, weeklyReport } from "@/lib/coach";
import type { CoachCategory, CoachItem, CoachMode, CoachPrompt } from "@/lib/schemas";
import { newId, readDB, updateDB } from "@/lib/store";

export const maxDuration = 300;

type Lang = "en" | "zh";
type Body =
  | { kind: "next"; lang: Lang; category: CoachCategory | "auto"; jdIds: string[] }
  | { kind: "feedback"; lang: Lang; prompt: CoachPrompt; mode: CoachMode; answer: string; seconds: number; jdIds: string[] }
  | { kind: "report"; lang: Lang };

const fail = (error: string, status = 400) => NextResponse.json({ error }, { status });

export async function POST(req: Request) {
  const body = (await req.json()) as Body;
  const lang = body.lang === "zh" ? "zh" : "en";
  const db = await readDB();
  if (!db.profile.savedAt) return fail("Save your profile with a resume first.");
  const records = "jdIds" in body ? db.analyses.filter((a) => (body.jdIds ?? []).includes(a.id)) : [];
  try {
    if (body.kind === "next") {
      if (body.category === "jd" && records.length === 0) return fail("Tick at least one job to practise JD questions.");
      return NextResponse.json({ prompt: await nextQuestion({ profile: db.profile, coach: db.coach, records, category: body.category, lang }) });
    }
    if (body.kind === "feedback") {
      const answer = String(body.answer ?? "").trim();
      if (answer.split(/\s+/).length < 8) return fail("The answer is too short to coach. Say a little more.");
      const { feedback, audit } = await giveFeedback({
        profile: db.profile, coach: db.coach, prompt: body.prompt, mode: body.mode, answer,
        seconds: Number(body.seconds) || 0, jdText: body.prompt.category === "jd" ? records[0]?.jdText ?? "" : "", lang,
      });
      const item: CoachItem = { ...body.prompt, id: newId(), at: new Date().toISOString(), mode: body.mode, answer, seconds: Number(body.seconds) || 0, feedback, feedbackAudit: audit };
      const coach = await updateDB((d) => {
        d.coach.items.unshift(item);
        return d.coach;
      });
      return NextResponse.json({ coach, item });
    }
    if (body.kind === "report") {
      const report = await weeklyReport(db.coach, lang);
      const coach = await updateDB((d) => {
        d.coach.report = report;
        return d.coach;
      });
      return NextResponse.json({ coach });
    }
    return fail("Unknown request.");
  } catch (err) {
    if (err instanceof AgentError) return fail(err.message, 502);
    console.error(err);
    return fail("Something went wrong while running the coach.", 500);
  }
}

/** Download the practice log as Markdown. */
export async function GET() {
  const db = await readDB();
  return new NextResponse(sessionLog(db.coach.items), {
    headers: { "content-type": "text/markdown; charset=utf-8", "content-disposition": 'attachment; filename="interview-practice-log.md"' },
  });
}

/** Remove one practice item. */
export async function DELETE(req: Request) {
  const id = new URL(req.url).searchParams.get("id");
  const coach = await updateDB((d) => {
    d.coach.items = d.coach.items.filter((i) => i.id !== id);
    return d.coach;
  });
  return NextResponse.json({ coach });
}
