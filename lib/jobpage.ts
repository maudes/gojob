/**
 * Read a job posting from its link. Ported from the first-generation job-hunt-ai reader.
 *
 * Order: 1. the job board's own public API (cleanest), 2. the page itself,
 * 3. Jina Reader, a third-party service that renders JavaScript pages.
 * Step 3 sends the job link (nothing else) to r.jina.ai; set JD_READER_FALLBACK=off to skip it.
 */
import { htmlToText, isSafeUrl } from "./extract";

export type JobPage = { text: string; via: string };

const HEADERS = { "user-agent": "Mozilla/5.0 (compatible; job-page-reader)" };
const MIN_CHARS = 600;

async function getJSON(url: string, init: RequestInit = {}): Promise<Record<string, any> | null> {
  try {
    const res = await fetch(url, { ...init, headers: { ...HEADERS, accept: "application/json", ...(init.headers ?? {}) }, signal: AbortSignal.timeout(10000) });
    return res.ok ? ((await res.json()) as Record<string, any>) : null;
  } catch {
    return null;
  }
}

const withTitle = (title: unknown, company: unknown, location: unknown, body: string) =>
  [[title, company, location].filter((x) => typeof x === "string" && x).join("\n"), body].filter(Boolean).join("\n\n");

/** https://job-boards.greenhouse.io/company/jobs/12345 */
async function greenhouse(url: string): Promise<string | null> {
  const m = /https:\/\/(?:job-boards|boards)\.greenhouse\.io\/([^/]+)\/jobs\/(\d+)/.exec(url);
  if (!m) return null;
  const data = await getJSON(`https://boards-api.greenhouse.io/v1/boards/${m[1]}/jobs/${m[2]}?questions=false`);
  if (!data) return null;
  // Greenhouse returns its HTML entity-encoded, so decode once before stripping tags.
  const html = String(data.content ?? data.description ?? "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
  return withTitle(data.title, data.company_name, data.location?.name, htmlToText(html));
}

/** https://jobs.ashbyhq.com/company/uuid */
async function ashby(url: string): Promise<string | null> {
  const m = /https:\/\/jobs\.ashbyhq\.com\/([^/]+)\/([a-f0-9-]{36})/.exec(url);
  if (!m) return null;
  const data = await getJSON(`https://api.ashbyhq.com/posting-api/job-board/${m[1]}`);
  const job = (data?.jobs as Record<string, any>[] | undefined)?.find((j) => String(j.jobUrl ?? "").includes(m[2]));
  if (!job) return null;
  return withTitle(job.title, m[1], job.location, htmlToText(String(job.descriptionHtml ?? "")) || String(job.descriptionPlain ?? ""));
}

/** https://tenant.wd3.myworkdayjobs.com/locale/Board/job/Location/Title_JR123 */
async function workday(url: string): Promise<string | null> {
  const m = /https:\/\/([^.]+\.\w+)\.myworkdayjobs\.com\/(?:[a-z]{2}-[A-Z]{2}\/)?([^/]+)\/job\/([^?#]+)/.exec(url);
  if (!m) return null;
  const [, host, board, path] = m;
  const tenant = host.split(".")[0];
  const data = await getJSON(`https://${host}.myworkdayjobs.com/wday/cxs/${tenant}/${board}/job/${path}`);
  const info = data?.jobPostingInfo;
  if (!info) return null;
  return withTitle(info.title, data?.hiringOrganization?.name ?? tenant, info.location, htmlToText(String(info.jobDescription ?? "")));
}

/** https://jobs.lever.co/company/uuid */
async function lever(url: string): Promise<string | null> {
  const m = /https:\/\/jobs\.(?:eu\.)?lever\.co\/([^/]+)\/([a-f0-9-]{36})/.exec(url);
  if (!m) return null;
  const api = url.includes("jobs.eu.lever.co") ? "api.eu.lever.co" : "api.lever.co";
  const data = await getJSON(`https://${api}/v0/postings/${m[1]}/${m[2]}`);
  if (!data) return null;
  const parts = [String(data.descriptionPlain ?? "")];
  for (const section of (data.lists as Record<string, any>[] | undefined) ?? []) parts.push(`${section.text ?? ""}\n${htmlToText(String(section.content ?? ""))}`);
  if (data.additional) parts.push(htmlToText(String(data.additional)));
  return withTitle(data.text, m[1], data.categories?.location, parts.filter(Boolean).join("\n\n"));
}

/** https://jobs.smartrecruiters.com/Company/744000113104547-job-title */
async function smartrecruiters(url: string): Promise<string | null> {
  const m = /https:\/\/jobs\.smartrecruiters\.com\/([^/]+)\/([^/?#]+)/.exec(url);
  if (!m) return null;
  const id = /^(\d+)/.exec(m[2])?.[1] ?? m[2];
  const data = await getJSON(`https://api.smartrecruiters.com/v1/companies/${m[1]}/postings/${id}`);
  const sections = data?.jobAd?.sections;
  if (!sections) return null;
  const body = ["companyDescription", "jobDescription", "qualifications", "additionalInformation"]
    .map((k) => htmlToText(String(sections[k]?.text ?? "")))
    .filter(Boolean)
    .join("\n\n");
  return withTitle(data.name, data.company?.name ?? m[1], data.location?.city, body);
}

async function direct(url: URL): Promise<string | null> {
  try {
    const res = await fetch(url, { headers: { ...HEADERS, accept: "text/html" }, signal: AbortSignal.timeout(12000), redirect: "follow" });
    // A closed posting often redirects to the company home page; that is not the job.
    if (!res.ok || new URL(res.url).hostname !== url.hostname) return null;
    return htmlToText(await res.text());
  } catch {
    return null;
  }
}

const TAIL_CUTS = ["### 類似職缺", "### Similar Jobs", "## 聯絡方式", "這些工作也很適合你"];

async function jina(url: string): Promise<string | null> {
  if ((process.env.JD_READER_FALLBACK ?? "").toLowerCase() === "off") return null;
  try {
    const key = process.env.JINA_API_KEY;
    const res = await fetch(`https://r.jina.ai/${url}`, { headers: key ? { authorization: `Bearer ${key}` } : {}, signal: AbortSignal.timeout(25000) });
    if (!res.ok) return null;
    let text = await res.text();
    // Jina reports the address it ended on. A different site means the posting redirected away.
    const landed = /Final URL:\s*(\S+)/.exec(text)?.[1];
    try {
      if (landed && new URL(landed).hostname !== new URL(url).hostname) return null;
    } catch {
      /* unparseable address: keep the text */
    }
    for (const cut of TAIL_CUTS) if (text.includes(cut)) text = text.slice(0, text.indexOf(cut));
    // A short page that still says "Loading" was not rendered.
    if (text.includes("Loading") && text.length < 1500) return null;
    return text.trim() || null;
  } catch {
    return null;
  }
}

const SIGNALS = [
  "responsibilit", "requirement", "qualification", "experience", "skills", "about the role", "what you", "we are looking", "you will", "apply", "team",
  "工作內容", "條件", "職責", "資格", "經驗", "技能", "aufgaben", "profil", "erfahrung", "expérience", "compétences", "poste",
];
const CLOSED = ["職缺已關閉", "no longer available", "no longer accepting", "position has been filled", "job has expired", "posting has closed", "page not found"];

/** A fetched page counts only if it reads like an open job posting. Board APIs are trusted with fewer signals. */
function looksLikeJob(text: string, trusted: boolean): boolean {
  const lower = text.toLowerCase();
  if (CLOSED.some((c) => lower.slice(0, 600).includes(c.toLowerCase()))) return false;
  return SIGNALS.filter((x) => lower.includes(x)).length >= (trusted ? 2 : 4);
}

const BOARDS: [string, (url: string) => Promise<string | null>][] = [
  ["Greenhouse", greenhouse],
  ["Ashby", ashby],
  ["Workday", workday],
  ["Lever", lever],
  ["SmartRecruiters", smartrecruiters],
];

export async function readJobPage(raw: string): Promise<JobPage | null> {
  const url = isSafeUrl(raw);
  if (!url) return null;
  const good = (text: string | null, trusted = false): text is string => text != null && text.trim().length >= MIN_CHARS && looksLikeJob(text, trusted);
  for (const [via, read] of BOARDS) {
    const text = await read(url.toString());
    if (good(text, true)) return { text: text.slice(0, 30000), via };
  }
  const page = await direct(url);
  if (good(page)) return { text: page.slice(0, 30000), via: "page" };
  const rendered = await jina(url.toString());
  if (good(rendered)) return { text: rendered.slice(0, 30000), via: "Jina Reader" };
  return null;
}
