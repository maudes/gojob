/**
 * Step 2: the headhunter scan. A capable agent searches the web for openings and companies
 * that fit the saved profile; the app then opens every job link itself, checks every resume
 * quote, and five auditors review what the report says about the candidate.
 */
import { AgentError, hasCredentials, runWithSearch } from "./claude";
import { isSafeUrl } from "./extract";
import { readJobPage } from "./jobpage";
import { checkQuotes, demoAudit, parseLooseJSON, withAudit } from "./pipeline";
import * as P from "./prompts";
import {
  CompanyOpenings,
  ScoutReport,
  type AuditResult,
  type LinkStatus,
  type Profile,
  type ScoutData,
  type ScoutRun,
  type ScoutSettings,
  type WatchCompany,
  type WatchOpening,
} from "./schemas";
import { redact } from "./text";

export const MAX_JOBS = 8;
export const MAX_COMPANIES = 5;

export const defaultSettings = (profile: Profile): ScoutSettings => ({
  regions: profile.regions.length ? profile.regions : ["Global remote"],
  languages: ["English"],
  notes: "",
});

const AUDIT_NOTE =
  "The OUTPUT is a job-market scan built from web search. Companies, postings, links, dates, visa notes and market signals come from the web and are outside the sources; do not flag them. Flag only: a statement about the candidate (experience, skills, results, level) that RESUME and PROFILE do not support; a resume proof quote that is not word for word; a wrong confirmed / inference / needs_confirmation label on a candidate statement; and an item that breaks PROFILE (a role family, work type or sponsorship need the profile rules out).";

/** Keep only real web addresses, so a made-up or empty link never reaches the table. */
export function keepLinked<T extends { url: string }>(items: T[]): { kept: T[]; dropped: number } {
  const kept = items.filter((i) => isSafeUrl(i.url.trim()) != null);
  return { kept, dropped: items.length - kept.length };
}

/** Open each link from this computer. "verified" means it read like an open job posting. */
export async function verifyLinks(urls: string[]): Promise<Record<string, LinkStatus>> {
  const unique = [...new Set(urls)];
  const results = await Promise.all(unique.map((u) => readJobPage(u).then((page) => (page ? "verified" : "unverified") as LinkStatus, () => "unverified" as LinkStatus)));
  return Object.fromEntries(unique.map((u, i) => [u, results[i]]));
}

function demoReport(profile: Profile, settings: ScoutSettings): ScoutReport {
  const role = profile.roles[0] || "Product Manager";
  const domain = profile.domains[0] || "your domain";
  const line = profile.resumeText.split("\n").map((l) => l.trim()).find((l) => l.length > 40) ?? "";
  const proof = line ? ({ source: "resume", quote: redact(line) } as const) : ({ source: "none", quote: "" } as const);
  return {
    headline: "Sample result. A real scan searches each region for openings and market signals that fit your profile.",
    regions: settings.regions.map((region, i) => ({
      region,
      heat: (["steady", "warming", "unknown"] as const)[i % 3],
      summary: "Sample text. A real scan summarises hiring activity, funding and layoffs for this region, with a source link.",
      label: "inference" as const,
      sourceUrl: "",
    })),
    jobs: [
      { tier: "A", company: "Sample Devices Co", title: `Senior ${role}`, location: `${settings.regions[0] ?? "Remote"} · Hybrid`, visa: "offered", visaNote: "Sample: posting states relocation support.", posted: "unverified", url: "https://example.com/jobs/sample-1", fit: `Sample: direct match with your ${domain} background.`, proof, label: "inference" },
      { tier: "B", company: "Sample Networks Ltd", title: `${role}, Platform`, location: "Remote", visa: "not_mentioned", visaNote: "Sample: visa not mentioned, confirm with the recruiter.", posted: "unverified", url: "https://example.com/jobs/sample-2", fit: "Sample: adjacent industry where the same platform skills transfer.", proof, label: "inference" },
      { tier: "C", company: "Sample AI Labs", title: `${role}, Developer Platform`, location: "Remote", visa: "needs_confirmation", visaNote: "Sample: hiring location unclear.", posted: "unverified", url: "https://example.com/jobs/sample-3", fit: "Sample: your experience is a lever in a different field.", proof, label: "needs_confirmation" },
    ],
    companies: [
      { company: "Sample Home Robotics", url: "https://example.com/careers", signal: "Sample: recent funding round and a new product line.", signalUrl: "", why: `Sample: building in ${domain} with no matching opening yet.`, roleType: role, approach: "Sample: reach a product lead with a question about their roadmap, not a job request.", proof, label: "inference" },
    ],
    weekly: "",
    priorities: ["Sample: save one job to your wish list and analyse it in step 3."],
    unreachable: [],
  };
}

export async function runScout(profile: Profile, settings: ScoutSettings, history: ScoutData["history"], lang: P.Lang, runs: number): Promise<ScoutRun> {
  const at = new Date().toISOString();
  if (!hasCredentials()) {
    const output = demoReport(profile, settings);
    return { ...demoAudit(), output, links: Object.fromEntries(output.jobs.map((j) => [j.url, "sample" as LinkStatus])), dropped: 0, at, runs };
  }
  const weekAgo = Date.now() - 7 * 86400000;
  const previous = history
    .filter((h) => Date.parse(h.at) >= weekAgo)
    .map((h) => `${h.at.slice(0, 10)}: ${h.headline} | ${h.regions.map((r) => `${r.region}=${r.heat}`).join(", ")}`)
    .join("\n");
  const context = `${P.profileBlock(profile)}\n${P.scoutSettingsBlock(settings, previous)}`;
  const text = await runWithSearch({ system: P.system(P.SCOUT_ROLE, lang), user: context, maxSearches: Math.min(30, 8 + settings.regions.length * 4), maxTokens: 24000 });
  const parsed = ScoutReport.safeParse(parseLooseJSON(text, "headhunter agent"));
  if (!parsed.success) throw new AgentError("The headhunter agent did not return a usable list. Retry.");
  const jobs = keepLinked(parsed.data.jobs);
  const output: ScoutReport = { ...parsed.data, jobs: jobs.kept.slice(0, MAX_JOBS), companies: parsed.data.companies.slice(0, MAX_COMPANIES) };
  const sources = { resume: redact(profile.resumeText), jd: "" };
  const [audit, links] = await Promise.all([
    withAudit({ produce: async () => output, context, lang, repair: false, note: AUDIT_NOTE, check: (o) => checkQuotes(o, sources) }),
    verifyLinks(output.jobs.map((j) => j.url)),
  ]);
  const { output: _same, ...result } = audit;
  return { ...result, output, links, dropped: jobs.dropped, at, runs };
}

/** Re-check one target company. Openings not seen before are marked new. */
export async function checkCompany(profile: Profile, company: WatchCompany, lang: P.Lang): Promise<{ openings: WatchOpening[]; note: string; audit: AuditResult }> {
  const now = new Date().toISOString();
  if (!hasCredentials()) {
    const seen = company.openings.some((o) => o.url === "https://example.com/jobs/sample-watch");
    return {
      openings: [{ title: `Sample: ${profile.roles[0] || "Product Manager"}`, location: "Remote", url: "https://example.com/jobs/sample-watch", fit: "Sample opening. A real check searches this company's careers page.", firstSeen: seen ? company.openings[0].firstSeen : now, isNew: !seen, link: "sample" }],
      note: "Sample result. Add an API key to search this company's current openings.",
      audit: demoAudit(),
    };
  }
  const context = `${P.profileBlock(profile)}\n<COMPANY>\nName: ${company.company}\nCareers page: ${company.careersUrl || "(not given, search for it)"}\n</COMPANY>`;
  const text = await runWithSearch({ system: P.system(P.COMPANY_WATCH_ROLE, lang), user: context, maxSearches: 6, maxTokens: 8000 });
  const parsed = CompanyOpenings.safeParse(parseLooseJSON(text, "headhunter agent"));
  if (!parsed.success) throw new AgentError("The headhunter agent did not return a usable list. Retry.");
  const output = { ...parsed.data, openings: keepLinked(parsed.data.openings).kept.slice(0, 6) };
  const sources = { resume: redact(profile.resumeText), jd: "" };
  const [audited, links] = await Promise.all([
    withAudit({ produce: async () => output, context, lang, repair: false, note: AUDIT_NOTE, check: (o) => checkQuotes(o, sources) }),
    verifyLinks(output.openings.map((o) => o.url)),
  ]);
  const { output: _same, ...audit } = audited;
  const before = new Map(company.openings.map((o) => [o.url, o.firstSeen]));
  return {
    openings: output.openings.map((o) => ({ title: o.title, location: o.location, url: o.url, fit: o.fit, firstSeen: before.get(o.url) ?? now, isNew: !before.has(o.url), link: links[o.url] ?? "unverified" })),
    note: output.note,
    audit,
  };
}
