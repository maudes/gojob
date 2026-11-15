import { NextResponse } from "next/server";
import { AgentError } from "@/lib/claude";
import { removeSource } from "@/lib/files";
import { analyzeJD, healthCheck, runAction } from "@/lib/pipeline";
import type { ActionKind, AnalysisRecord, ScorePoint } from "@/lib/schemas";
import { newId, readDB, updateDB } from "@/lib/store";

export const maxDuration = 800;

type Lang = "en" | "zh";
type Body =
  | { kind: "health"; lang: Lang }
  | { kind: "analyze"; lang: Lang; jdUrl: string; jdText: string }
  | { kind: "reanalyze"; lang: Lang; id: string }
  | { kind: "action"; lang: Lang; id: string; action: ActionKind; input?: string }
  | { kind: "setTarget"; lang: Lang; id: string; target: string };

const ACTIONS: ActionKind[] = ["fineTune", "coverLetter", "interview", "networking", "onePager"];
const fail = (error: string, status = 400) => NextResponse.json({ error }, { status });
const point = (g: { average: number; scores: number[] }): ScorePoint => ({ at: new Date().toISOString(), average: g.average, scores: g.scores });

export async function POST(req: Request) {
  const body = (await req.json()) as Body;
  const lang = body.lang === "zh" ? "zh" : "en";
  const db = await readDB();
  const profile = db.profile;
  // Eval rule 1: every assessment runs on the saved profile, nothing else.
  if (!profile.savedAt || profile.resumeText.trim().length < 200) return fail("Save your profile with a resume first.");

  try {
    if (body.kind === "health") {
      if (profile.targetJDs.length < 3) return fail("Add at least 3 target JDs first.");
      const same = db.health?.profileSavedAt === profile.savedAt;
      const runs = same ? db.healthRuns + 1 : 1;
      const health = await healthCheck(profile, lang, runs);
      await updateDB((d) => {
        d.health = health;
        d.healthRuns = runs;
      });
      return NextResponse.json({ health });
    }

    if (body.kind === "analyze") {
      const jdText = (body.jdText ?? "").trim();
      if (jdText.length < 300) return fail("The job description is too short to analyse.");
      const result = await analyzeJD(profile, profile.resumeText, jdText, lang, 1);
      const record: AnalysisRecord = {
        id: newId(),
        jdUrl: body.jdUrl ?? "",
        jdText,
        createdAt: new Date().toISOString(),
        tailoredText: null,
        assessedText: profile.resumeText,
        history: [point(result.gate)],
        networkTarget: "",
        ...result,
        actions: {},
      };
      await updateDB((d) => {
        d.analyses.unshift(record);
      });
      return NextResponse.json({ record });
    }

    const existing = db.analyses.find((a) => a.id === body.id);
    if (!existing) return fail("Analysis not found.", 404);
    const save = (fn: (r: AnalysisRecord) => void) =>
      updateDB((d) => {
        const target = d.analyses.find((a) => a.id === body.id)!;
        fn(target);
        return target;
      });

    if (body.kind === "reanalyze") {
      const resume = existing.tailoredText ?? profile.resumeText;
      // A changed resume is a new assessment (never limited). The same resume is a retry (counted).
      const changed = resume !== existing.assessedText;
      const runs = changed ? 1 : existing.analysis.runs + 1;
      const result = await analyzeJD(profile, resume, existing.jdText, lang, runs, changed || existing.history.length > 1);
      const record = await save((r) => {
        Object.assign(r, result);
        r.assessedText = resume;
        if (changed) r.history.push(point(result.gate));
        else r.history[r.history.length - 1] = point(result.gate);
      });
      return NextResponse.json({ record, changed });
    }

    if (body.kind === "setTarget") {
      const record = await save((r) => {
        r.networkTarget = String(body.target ?? "").slice(0, 200);
      });
      return NextResponse.json({ record });
    }

    if (body.kind === "action" && ACTIONS.includes(body.action)) {
      const output = await runAction(body.action, profile, existing, lang, body.input ?? "");
      const record = await save((r) => {
        (r.actions as Record<string, unknown>)[body.action] = output;
      });
      return NextResponse.json({ record });
    }
    return fail("Unknown request.");
  } catch (err) {
    if (err instanceof AgentError) return fail(err.message, 502);
    console.error(err);
    return fail("Something went wrong while running the agents.", 500);
  }
}

export async function DELETE(req: Request) {
  const id = new URL(req.url).searchParams.get("id") ?? "";
  await updateDB((d) => {
    d.analyses = d.analyses.filter((a) => a.id !== id);
  });
  await removeSource(`jd-${id}`);
  return NextResponse.json({ ok: true });
}
