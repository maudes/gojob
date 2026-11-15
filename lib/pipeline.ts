import { promises as fs } from "node:fs";
import path from "node:path";
import type { z } from "zod";
import { AgentError, hasCredentials, MAIN_MODEL, REVIEWER_MODEL, runJSON, runWithSearch } from "./claude";
import * as demo from "./demo";
import * as P from "./prompts";
import {
  Audit,
  CoverLetter,
  FineTune,
  HealthCheck,
  Interview,
  JDAnalysis,
  Networking,
  PanelScore,
  type ActionKind,
  type AnalysisRecord,
  type AuditResult,
  type Gate,
  type Profile,
  type QuoteCheck,
  type Reviewed,
} from "./schemas";
import { isVerbatim, redact } from "./text";

type Sources = { resume: string; jd: string };

export const AUDITOR_COUNT = P.AUDIT_FOCUS.length;
/** Every auditor must score strictly above this. */
export const AUDIT_PASS_ABOVE = 95;

/* ---------- Deterministic proof: every quote must exist in its source ---------- */

export function checkQuotes(output: unknown, sources: Sources): QuoteCheck {
  const found: { source: "resume" | "jd"; quote: string }[] = [];
  const walk = (node: unknown, key = "") => {
    if (Array.isArray(node)) {
      for (const item of node) {
        if (typeof item === "string" && (key === "orderedBullets" || key === "drop"))
          found.push({ source: "resume", quote: item });
        else walk(item, key);
      }
      return;
    }
    if (!node || typeof node !== "object") return;
    const obj = node as Record<string, unknown>;
    if (typeof obj.quote === "string" && (obj.source === "resume" || obj.source === "jd"))
      found.push({ source: obj.source, quote: obj.quote });
    if (typeof obj.find === "string" && typeof obj.replace === "string")
      found.push({ source: "resume", quote: obj.find });
    for (const [k, v] of Object.entries(obj)) walk(v, k);
  };
  walk(output);
  const real = found.filter((f) => f.quote.trim());
  const failed = real.filter((f) => !isVerbatim(f.quote, sources[f.source]));
  return { total: real.length, verified: real.length - failed.length, failed };
}

/* ---------- Five lightweight auditors ---------- */

async function runAudits(context: string, output: unknown, lang: P.Lang, note = ""): Promise<Audit[]> {
  const user = `${context}\n${note ? `<AUDIT_NOTE>\n${note}\n</AUDIT_NOTE>\n` : ""}<OUTPUT>\n${JSON.stringify(output, null, 1)}\n</OUTPUT>`;
  const audits = await Promise.all(
    P.AUDIT_FOCUS.map((focus) =>
      runJSON({
        schema: Audit,
        model: REVIEWER_MODEL,
        system: `${P.auditRole(focus)}\n\n${lang === "zh" ? "Write issues in Taiwan Traditional Chinese." : "Write issues in English."}`,
        user,
        effort: "low",
      }),
    ),
  );
  return audits.map((a) => ({ ...a, score: Math.max(0, Math.min(100, Math.round(a.score))) }));
}

/** Approved only when all five auditors score above 95, tick every box, and every quote is verbatim. */
export function isApproved(audits: Audit[], quoteCheck: QuoteCheck): boolean {
  return (
    audits.length === AUDITOR_COUNT &&
    audits.every((a) => a.score > AUDIT_PASS_ABOVE && Object.values(a.checks).every(Boolean)) &&
    quoteCheck.failed.length === 0
  );
}

export const demoAudit = (): AuditResult => ({ audits: demo.audits, quoteCheck: { total: 0, verified: 0, failed: [] }, approved: true, demo: true });

/**
 * The one path every AI output takes: the capable writer produces it, five light auditors
 * check it against the sources on the fixed checklist, and the code-level quote check runs.
 * If it fails, the flagged items go back to the writer once and all five audit again.
 */
export async function withAudit<T>(opts: {
  produce: (extra: string) => Promise<T>;
  context: string;
  lang: P.Lang;
  check?: (output: T) => QuoteCheck;
  note?: string;
  repair?: boolean;
}): Promise<AuditResult & { output: T }> {
  const check = opts.check ?? (() => ({ total: 0, verified: 0, failed: [] }));
  let output = await opts.produce("");
  let audits = await runAudits(opts.context, output, opts.lang, opts.note);
  let quoteCheck = check(output);
  if (opts.repair !== false && !isApproved(audits, quoteCheck)) {
    const problems = [
      ...audits.flatMap((a) => a.issues),
      ...quoteCheck.failed.map((f) => `This text is attributed to the ${f.source} but is not found there word for word: "${f.quote}"`),
    ];
    if (problems.length) {
      output = await opts.produce(
        `\n<PREVIOUS_OUTPUT>\n${JSON.stringify(output)}\n</PREVIOUS_OUTPUT>\n<REVIEW_ISSUES>\n${[...new Set(problems)].map((p) => `- ${p}`).join("\n")}\n</REVIEW_ISSUES>\nProduce the output again. Keep everything the reviewers did not flag. Fix or remove each flagged item so that it is fully supported by the sources.`,
      );
      audits = await runAudits(opts.context, output, opts.lang, opts.note);
      quoteCheck = check(output);
    }
  }
  return { output, audits, quoteCheck, approved: isApproved(audits, quoteCheck), demo: false };
}

async function reviewed<S extends z.ZodType>(opts: {
  schema: S;
  role: string;
  context: string;
  sources: Sources;
  lang: P.Lang;
  runs: number;
}): Promise<Reviewed<z.infer<S>>> {
  const result = await withAudit<z.infer<S>>({
    produce: (extra) => runJSON({ schema: opts.schema, model: MAIN_MODEL, system: P.system(opts.role, opts.lang), user: opts.context + extra, effort: "high" }),
    context: opts.context,
    lang: opts.lang,
    check: (output) => checkQuotes(output, opts.sources),
  });
  return { ...result, runs: opts.runs, generatedAt: new Date().toISOString() };
}

export const demoReviewed = <T>(output: T, runs: number): Reviewed<T> => ({
  output,
  audits: demo.audits,
  quoteCheck: { total: 0, verified: 0, failed: [] },
  approved: true,
  runs,
  demo: true,
  generatedAt: new Date().toISOString(),
});

/* ---------- Three scoring reviewers ---------- */

const PANEL_NOTE =
  "The OUTPUT is three reviewers' scores with their verdicts, strengths and gaps. Judge whether each verdict, strength and gap is supported by the sources and whether every proof quote is word for word. A score is an opinion: flag it only when its own verdict contradicts the evidence it cites.";

/** The three scoring reviewers, whose own output is then audited like everything else. */
async function runPanel(context: string, target: "profile" | "jd", lang: P.Lang, sources: Sources) {
  const result = await withAudit({
    produce: (extra) =>
      Promise.all(
        P.PANEL_LENSES.map(async ({ id, lens }) => {
          const score = await runJSON({ schema: PanelScore, model: MAIN_MODEL, system: P.system(P.panelRole(lens, target), lang), user: context + extra, effort: "medium" });
          return { ...score, score: Math.max(0, Math.min(100, Math.round(score.score))), reviewer: id };
        }),
      ),
    context,
    lang,
    check: (output) => checkQuotes(output, sources),
    note: PANEL_NOTE,
  });
  const { output: panel, ...panelAudit } = result;
  return { panel, panelAudit };
}

export function gate(scores: number[], needAverage: number, needMin: number): Gate {
  const average = Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 10) / 10;
  const min = Math.min(...scores);
  return { kind: "panel", scores, average, min, needAverage, needMin, green: average >= needAverage && min >= needMin };
}

/* ---------- Public entry points ---------- */

export async function healthCheck(profile: Profile, lang: P.Lang, runs: number) {
  if (!hasCredentials()) {
    return {
      check: demoReviewed(demo.health(profile.resumeText), runs),
      panel: demo.panel([72, 84, 78]),
      panelAudit: demoAudit(),
      gate: gate([72, 84, 78], 80, 70),
      profileSavedAt: profile.savedAt,
    };
  }
  const context = `${P.profileBlock(profile)}\n${P.targetJDsBlock(profile)}`;
  const sources = { resume: redact(profile.resumeText), jd: profile.targetJDs.map((j) => j.text).join("\n") };
  const [check, { panel, panelAudit }] = await Promise.all([
    reviewed({ schema: HealthCheck, role: P.HEALTH_ROLE, context, sources, lang, runs }),
    runPanel(context, "profile", lang, sources),
  ]);
  return { check, panel, panelAudit, gate: gate(panel.map((p) => p.score), 80, 70), profileSavedAt: profile.savedAt };
}

/** Matching assessment for one JD. `resumeText` is the tailored version when there is one. */
export async function analyzeJD(profile: Profile, resumeText: string, jdText: string, lang: P.Lang, runs: number, improved = false) {
  if (!hasCredentials()) {
    const scores = improved ? [82, 85, 82] : [68, 76, 71];
    return { analysis: demoReviewed(demo.jdAnalysis, runs), panel: demo.panel(scores), panelAudit: demoAudit(), gate: gate(scores, 80, 60) };
  }
  const context = `${P.profileBlock(profile, resumeText)}\n${P.jdBlock(jdText)}`;
  const sources = { resume: redact(resumeText), jd: jdText };
  const [analysis, { panel, panelAudit }] = await Promise.all([
    reviewed({ schema: JDAnalysis, role: P.JD_ROLE, context, sources, lang, runs }),
    runPanel(context, "jd", lang, sources),
  ]);
  return { analysis, panel, panelAudit, gate: gate(panel.map((p) => p.score), 80, 60) };
}

export function parseLooseJSON(text: string, what = "networking agent"): unknown {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  try {
    if (start < 0 || end <= start) throw new Error();
    return JSON.parse(text.slice(start, end + 1));
  } catch {
    throw new AgentError(`The ${what} did not return a usable list. Retry.`);
  }
}

/** Search the web for people at one company and draft two first-contact messages each. */
export async function findPeople(context: string, where: { company: string; title: string; location: string }, lang: P.Lang, runs: number): Promise<Reviewed<Networking>> {
  if (!hasCredentials()) return demoReviewed(demo.actions.networking, runs);
  const text = await runWithSearch({
    system: P.system(P.NETWORKING_ROLE, lang),
    user: `${context}\nCompany: ${where.company}\nRole: ${where.title}\nLocation: ${where.location}`,
    maxSearches: 8,
    maxTokens: 16000,
  });
  const parsed = Networking.safeParse(parseLooseJSON(text));
  if (!parsed.success) throw new AgentError("The networking agent did not return a usable list. Retry.");
  const result = await withAudit({
    produce: async () => parsed.data,
    context,
    lang,
    repair: false,
    note: "Names, titles and profileUrl values come from web search and are outside the sources; do not flag them. Judge what the messages say about the candidate and the JD, and whether each message keeps the outreach rules (75 words or fewer, one question mark, no job opening, no referral request).",
  });
  return { ...result, runs, generatedAt: new Date().toISOString() };
}

export async function runAction(
  kind: ActionKind,
  profile: Profile,
  record: AnalysisRecord,
  lang: P.Lang,
  input: string,
): Promise<AnalysisRecord["actions"][ActionKind]> {
  const runs = (record.actions[kind]?.runs ?? 0) + 1;
  const meta = record.analysis.output.meta;
  const resumeText = record.tailoredText ?? profile.resumeText;

  if (!hasCredentials()) {
    if (kind === "onePager") return { html: demo.onePagerHtml, runs, demo: true, generatedAt: new Date().toISOString(), audit: demoAudit() };
    if (kind === "fineTune") return demoReviewed(demo.fineTune(resumeText), runs);
    if (kind === "coverLetter") return demoReviewed(demo.coverLetter(input), runs);
    return demoReviewed(demo.actions[kind] as never, runs) as never;
  }

  const context = `${P.profileBlock(profile, resumeText)}\n${P.jdBlock(record.jdText)}`;
  const sources = { resume: redact(resumeText), jd: record.jdText };
  const base = { sources, lang, runs };

  switch (kind) {
    case "fineTune":
      return reviewed({ ...base, context, schema: FineTune, role: P.FINE_TUNE_ROLE });
    case "interview":
      return reviewed({ ...base, context, schema: Interview, role: P.INTERVIEW_ROLE });
    case "coverLetter":
      return reviewed({
        ...base,
        schema: CoverLetter,
        role: P.COVER_LETTER_ROLE,
        context: `${context}\n<MOTIVATION note="written by the candidate, treat as confirmed">\n${redact(input) || "(nothing provided)"}\n</MOTIVATION>`,
      });
    case "networking":
      return findPeople(context, { company: meta.company, title: meta.title, location: meta.location }, lang, runs);
    case "onePager": {
      const template = await fs.readFile(path.join(process.cwd(), "prompts", "one-pager.md"), "utf8");
      const background = [
        `Target roles: ${profile.roles.join(", ")}`,
        `Domains: ${profile.domains.join(", ")}`,
        `Resume:\n${redact(resumeText)}`,
      ].join("\n");
      const prompt = template
        .replace("{{company}}", meta.company || "(see JD)")
        .replace("{{title}}", meta.title || profile.roles[0] || "")
        .replace("{{department}}", `${meta.location || profile.regions.join(", ")}`)
        .replace("{{round}}", input.trim() || "Not yet")
        .replace("{{background}}", background);
      const html = await runWithSearch({
        system:
          "Return only the HTML document, starting with <!DOCTYPE html>. No commentary and no code fences. Statements about the candidate come only from the background provided." +
          (lang === "en" ? " Write the report in English instead of Chinese." : ""),
        user: `${prompt}\n\n${P.jdBlock(record.jdText)}`,
        maxSearches: 15,
        maxTokens: 64000,
      });
      const cleaned = html.replace(/^[\s\S]*?(?=<!DOCTYPE|<html)/i, "").replace(/```\s*$/, "");
      const finalHtml = cleaned || html;
      // Auditors read the report as text and judge only what it says about the candidate.
      const { output: _text, ...audit } = await withAudit({
        produce: async () => finalHtml.replace(/<(script|style)[\s\S]*?<\/\1>/gi, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " "),
        context,
        lang,
        repair: false,
        note: "The OUTPUT is a company research report built from web sources. Company facts, figures and citations are outside the sources; do not flag them. Flag only statements about the candidate (background, experience, skills, results) that RESUME and PROFILE do not support.",
      });
      return { html: finalHtml, runs, demo: false, generatedAt: new Date().toISOString(), audit };
    }
  }
}
