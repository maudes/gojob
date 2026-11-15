/**
 * Interview coach: one question at a time, a 30-second and a 2-minute version,
 * short feedback on English and content, and a history that brings weak areas back more often.
 */
import { hasCredentials, MAIN_MODEL, runJSON } from "./claude";
import { demoAudit, withAudit } from "./pipeline";
import type { Lang } from "./prompts";
import { profileBlock } from "./prompts";
import {
  CoachFeedback,
  CoachQuestion,
  CoachReport,
  type AnalysisRecord,
  type AuditResult,
  type CoachCategory,
  type CoachData,
  type CoachItem,
  type CoachMode,
  type CoachPrompt,
  type Profile,
} from "./schemas";
import { isVerbatim, redact } from "./text";

export const CATEGORIES: CoachCategory[] = ["self_intro", "behavioral", "general", "story", "jd", "product"];
/** Roughly what fits when spoken at a calm pace. */
export const TARGET_WORDS: Record<CoachMode, [number, number]> = { "30s": [55, 90], "2min": [230, 320] };
const DAY = 86400000;

const COACH_AUDIT_NOTE =
  "This is interview coaching. The sources are RESUME, STORY BANK, ANSWER and (when present) JD and LOG. Check: every quote of the candidate's words is word for word from ANSWER; nothing states a fact about the candidate (number, result, name, situation) that the sources do not contain, placeholders such as [X] are allowed; labels and tags match what the answer actually says; the output fits the PROFILE. Tick jdQuotesVerbatim when no JD text is quoted. Judgements about quality are opinions; do not flag them.";

const langRule = (lang: Lang) =>
  lang === "zh"
    ? "Write explanations and notes in Taiwan Traditional Chinese. The interview question, corrected English and the tightened answer stay in English, because the interview is in English."
    : "Write everything in English.";

const COACH_RULES = `You are an English interview coach for a job seeker. Be direct, specific and brief.
Hard rules:
- Use only facts the candidate has given: the RESUME, the STORY BANK and the ANSWER. Never invent numbers, results, names or situations. Where a number is missing write [X] and list it under facts to confirm.
- No emoji, no em dashes, no generic encouragement.`;

/**
 * Pick the next category: the least practised in the last 14 days, with categories
 * that scored low counted as less practised so they come back more often.
 */
export function pickCategory(items: CoachItem[], hasJD: boolean, now = Date.now()): CoachCategory {
  const recent = items.filter((i) => now - Date.parse(i.at) < 14 * DAY);
  const last = items[0]?.category;
  let best: CoachCategory = "self_intro";
  let bestWeight = Infinity;
  for (const c of CATEGORIES) {
    if (c === "jd" && !hasJD) continue;
    const mine = recent.filter((i) => i.category === c);
    const avg = mine.length ? mine.reduce((a, i) => a + i.feedback.score, 0) / mine.length : 100;
    const weight = mine.length - (avg < 70 ? 1.5 : 0) + (c === last ? 0.5 : 0);
    if (weight < bestWeight) {
      best = c;
      bestWeight = weight;
    }
  }
  return best;
}

/** The weaknesses that showed up most in the last 14 days. */
export function topWeaknesses(items: CoachItem[], now = Date.now()): [string, number][] {
  const counts = new Map<string, number>();
  for (const i of items) {
    if (now - Date.parse(i.at) > 14 * DAY) continue;
    for (const w of i.feedback.weaknesses) counts.set(w, (counts.get(w) ?? 0) + 1);
  }
  return [...counts].sort((a, b) => b[1] - a[1]).slice(0, 3);
}

const CATEGORY_BRIEF: Record<CoachCategory, string> = {
  self_intro: "Self introduction, or a variation of it (tell me about yourself, walk me through your background, why this kind of role).",
  behavioral: "Behavioural: strengths, weaknesses, why this region or country, why you left a job, conflict, failure, feedback you received.",
  general: "General interview questions: motivation, working style, what you look for in a team or manager, career direction.",
  story: "Story-centred: ask about one specific story from the STORY BANK or one specific experience in the RESUME, and name it in the question.",
  jd: "JD-related: a question this specific job's interviewer would ask, built on the JD's requirements.",
  product: "Product questions: a feature decision, choosing metrics, improving a feature or product, prioritisation trade-offs.",
};

const DEMO_QUESTIONS: Record<CoachCategory, string> = {
  self_intro: "Tell me about yourself and why you are looking at product roles now.",
  behavioral: "What is a weakness you are actively working on, and what have you changed because of it?",
  general: "What kind of team do you do your best work in?",
  story: "Pick one project from your resume. What was the hardest decision you made on it?",
  jd: "Which requirement in this job description are you least sure you meet, and how would you close that gap?",
  product: "Choose a feature you use every day. How would you decide whether to improve it or remove it?",
};

function fromModuleTwo(records: AnalysisRecord[], asked: Set<string>): CoachPrompt | null {
  for (const r of records) {
    const q = r.actions.interview?.output.questions.find((x) => !asked.has(x.question));
    if (q)
      return {
        category: "jd",
        source: `${r.analysis.output.meta.company || "JD"} · ${q.interviewer}`,
        question: q.question,
        storyHint: q.keyElements.join(" · "),
        why: q.why,
        demo: r.actions.interview?.demo ?? false,
      };
  }
  return null;
}

export async function nextQuestion(opts: {
  profile: Profile;
  coach: CoachData;
  records: AnalysisRecord[];
  category: CoachCategory | "auto";
  lang: Lang;
}): Promise<CoachPrompt> {
  const { profile, coach, records } = opts;
  const category = opts.category === "auto" ? pickCategory(coach.items, records.length > 0) : opts.category;
  const asked = new Set(coach.items.map((i) => i.question));

  // JD practice starts with the questions already prepared for that job in module 2.
  if (category === "jd") {
    const ready = fromModuleTwo(records, asked);
    if (ready) return ready;
  }
  const jd = records[0];
  const source = category === "jd" && jd ? jd.analysis.output.meta.company || "JD" : category === "story" && coach.storyBank.text ? "Story bank" : "";

  if (!hasCredentials())
    return { category, source, question: DEMO_QUESTIONS[category], storyHint: "Sample question. Add an API key for questions built from your story bank and JDs.", why: "", demo: true, audit: demoAudit() };

  const weak = topWeaknesses(coach.items).map(([w, n]) => `${w} (${n}x)`).join(", ") || "none recorded";
  const recent = coach.items.slice(0, 30).map((i) => `- ${i.question}`).join("\n") || "(none)";
  const context = `Category: ${CATEGORY_BRIEF[category]}\nRecurring weaknesses (last 14 days): ${weak}\n\n<RECENT_QUESTIONS>\n${recent}\n</RECENT_QUESTIONS>\n${profileBlock(profile)}\n<STORY_BANK>\n${redact(coach.storyBank.text) || "(not provided)"}\n</STORY_BANK>${category === "jd" && jd ? `\n<JD>\n${jd.jdText}\n</JD>` : ""}`;
  const produce = (extra: string) => runJSON({
    schema: CoachQuestion,
    model: MAIN_MODEL,
    effort: "low",
    system: `${COACH_RULES}\n${langRule(opts.lang)}\n\nTask: write ONE interview question for the category below.\n- Do not repeat or lightly reword any question in RECENT QUESTIONS.\n- The candidate's recurring weaknesses are listed. When it fits, choose a question that makes them practise the top one.\n- storyHint: one line naming which story or experience from the STORY BANK or RESUME fits this question best. Empty if none fits.\n- why: one sentence on what an interviewer learns from this question.`,
    user: context + extra,
  });
  const { output: out, ...audit } = await withAudit({ produce, context, lang: opts.lang, note: `${COACH_AUDIT_NOTE} The OUTPUT is one interview question with a hint. It must not repeat a question in RECENT QUESTIONS and must not assert anything about the candidate that the sources do not show.` });
  return { category, source, ...out, demo: false, audit };
}

export async function giveFeedback(opts: {
  profile: Profile;
  coach: CoachData;
  prompt: CoachPrompt;
  mode: CoachMode;
  answer: string;
  seconds: number;
  jdText: string;
  lang: Lang;
}): Promise<{ feedback: CoachFeedback; audit: AuditResult }> {
  const count = opts.answer.trim().split(/\s+/).filter(Boolean).length;
  const [lo, hi] = TARGET_WORDS[opts.mode];
  if (!hasCredentials()) {
    const long = count > hi;
    const short = count < lo;
    const feedback: CoachFeedback = {
      score: long || short ? 62 : 78,
      headline: "Sample feedback. Add an API key for real coaching on your answer.",
      content: (["situation", "challenge", "decision", "impact", "relevance"] as const).map((element) => ({ element, present: element !== "impact", note: "Sample note." })),
      english: [],
      delivery: `${count} words. Target for the ${opts.mode === "30s" ? "30-second" : "2-minute"} version is ${lo} to ${hi}.`,
      tighter: "",
      weaknesses: [...(long ? (["too_long"] as const) : []), ...(short ? (["too_short"] as const) : []), "no_impact"],
      confirm: [],
    };
    return { feedback, audit: demoAudit() };
  }
  const context = `Question (${opts.prompt.category}): ${opts.prompt.question}\nVersion: ${opts.mode === "30s" ? "30 seconds" : "2 minutes"}\nWord count: ${count}${opts.seconds ? `\nTime taken: ${opts.seconds} seconds` : ""}\n\n<ANSWER>\n${redact(opts.answer)}\n</ANSWER>\n${profileBlock(opts.profile)}\n<STORY_BANK>\n${redact(opts.coach.storyBank.text) || "(not provided)"}\n</STORY_BANK>${opts.jdText ? `\n<JD>\n${opts.jdText}\n</JD>` : ""}`;
  const produce = (extra: string) => runJSON({
    schema: CoachFeedback,
    model: MAIN_MODEL,
    effort: "medium",
    system: `${COACH_RULES}\n${langRule(opts.lang)}\n\nTask: give concise feedback on one spoken interview answer (typed or dictated, so ignore punctuation and capitalisation slips).\n- score: 0 to 100 for how well this answer would land in a real interview at this length.\n- headline: the single most useful thing to change, in one sentence.\n- content: judge each of situation, challenge, decision, impact and relevance to the role. present is true only when the answer actually states it. One short note each. When it suits the question, also check the order Skill, then Success, then Relevance.\n- english: up to 4 corrections that matter (grammar, unnatural phrasing, vague wording). Quote the candidate's exact words in "original".\n- delivery: one sentence comparing length with the target (${lo} to ${hi} words; the 30-second version is about 5 sentences).\n- tighter: the same answer reworked to hit the target length, using only the candidate's own facts and wording where possible. Missing facts become [X]. Empty string if the answer is already good.\n- weaknesses: the tags that apply. Use too_long or too_short only when outside the target.\n- confirm: facts the candidate should confirm before using this answer (numbers, dates, scope they stated loosely).`,
    user: context + extra,
  });
  const answer = redact(opts.answer);
  const { output: out, ...audit } = await withAudit({
    produce,
    context,
    lang: opts.lang,
    note: COACH_AUDIT_NOTE,
    // Code-level proof: every English correction must quote the candidate's own words.
    check: (o) => {
      const quotes = o.english.map((e) => e.original).filter((q) => q.trim());
      const failed = quotes.filter((q) => !isVerbatim(q, answer)).map((quote) => ({ source: "answer", quote }));
      return { total: quotes.length, verified: quotes.length - failed.length, failed };
    },
  });
  return { feedback: { ...out, score: Math.max(0, Math.min(100, Math.round(out.score))) }, audit };
}

export async function weeklyReport(coach: CoachData, lang: Lang, now = Date.now()): Promise<NonNullable<CoachData["report"]>> {
  const week = coach.items.filter((i) => now - Date.parse(i.at) < 7 * DAY);
  const counts: Record<string, number> = {};
  for (const i of week) counts[i.category] = (counts[i.category] ?? 0) + 1;
  const base = { at: new Date(now).toISOString(), counts, total: week.length };
  if (!hasCredentials() || week.length === 0)
    return {
      ...base,
      demo: true,
      audit: demoAudit(),
      output: {
        strengths: week.length ? ["Sample: add an API key for a written review of your week."] : [],
        weakAreas: topWeaknesses(coach.items, now).map(([w, n]) => `${w} (${n}x)`),
        prepare: [],
        delivery30: "",
        delivery2min: "",
      },
    };
  const log = week
    .map((i) => `[${i.at.slice(0, 10)}] ${i.category} · ${i.mode} · score ${i.feedback.score} · ${i.answer.trim().split(/\s+/).length} words · weaknesses: ${i.feedback.weaknesses.join(", ") || "none"}\nQ: ${i.question}\nCoach: ${i.feedback.headline}`)
    .join("\n\n");
  const context = `<LOG>\n${log}\n</LOG>`;
  const produce = (extra: string) => runJSON({
    schema: CoachReport,
    model: MAIN_MODEL,
    effort: "medium",
    system: `${COACH_RULES}\n${langRule(lang)}\n\nTask: weekly practice review from the log below. Each list has at most 4 short items.\n- strengths: what recurs and works.\n- weakAreas: what recurs and hurts, most frequent first.\n- prepare: topics, stories or materials to prepare next week.\n- delivery30 and delivery2min: one sentence each on whether that length is improving across the week, citing the scores or word counts in the log. Say "not practised" when there is no data.`,
    user: context + extra,
  });
  const { output, ...audit } = await withAudit({ produce, context, lang, note: "The only source is LOG, the candidate's practice log. Every strength, weak area and delivery statement must be supported by entries in LOG, and any score or word count cited must appear there. Tick the two quote checks when nothing is quoted, and alignedWithProfile when nothing contradicts the log." });
  return { ...base, demo: false, output, audit };
}

/** A Markdown log of practice sessions, for the user's own records. */
export function sessionLog(items: CoachItem[]): string {
  const byDay = new Map<string, CoachItem[]>();
  for (const i of items) byDay.set(i.at.slice(0, 10), [...(byDay.get(i.at.slice(0, 10)) ?? []), i]);
  return [...byDay]
    .map(([day, list]) =>
      [`# Interview practice ${day}`, ...list.map((i) => `## ${i.category} · ${i.mode} · score ${i.feedback.score}\n\n**Q:** ${i.question}\n\n**Answer:** ${i.answer}\n\n**Coach:** ${i.feedback.headline}\n\n**Weaknesses:** ${i.feedback.weaknesses.join(", ") || "none"}`)].join("\n\n"),
    )
    .join("\n\n---\n\n");
}
