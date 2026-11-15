import { NextResponse } from "next/server";
import { AgentError } from "@/lib/claude";
import { readJobPage } from "@/lib/jobpage";
import { findPeople } from "@/lib/pipeline";
import { profileBlock } from "@/lib/prompts";
import { COMPANY_STATUSES, WISH_DECISIONS, type ScoutSettings, type WatchCompany, type WishJob } from "@/lib/schemas";
import { checkCompany, defaultSettings, runScout } from "@/lib/scout";
import { newId, readDB, updateDB } from "@/lib/store";

export const maxDuration = 800;

const fail = (error: string, status = 400) => NextResponse.json({ error }, { status });
const str = (v: unknown, max = 600) => (typeof v === "string" ? v.slice(0, max) : "");
const list = (v: unknown, max: number) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && !!x.trim()).map((x) => x.trim().slice(0, 60)).slice(0, max) : []);
const sameDay = (a: string | undefined, b: string) => a?.slice(0, 10) === b.slice(0, 10);

const JOB_FIELDS = ["company", "title", "location", "url", "tier", "visa", "posted", "fit", "notes"] as const;
const COMPANY_FIELDS = ["company", "careersUrl", "why", "roleType", "contact", "notes"] as const;

export async function POST(req: Request) {
  const body = (await req.json()) as Record<string, unknown>;
  const lang = body.lang === "zh" ? "zh" : "en";
  const db = await readDB();
  const profile = db.profile;

  try {
    switch (body.kind) {
      case "run": {
        // Eval rule 1: the scan runs on the saved profile, nothing else.
        if (!profile.savedAt || profile.resumeText.trim().length < 200) return fail("Save your profile with a resume first.");
        const base = defaultSettings(profile);
        const input = (body.settings ?? {}) as Record<string, unknown>;
        const regions = list(input.regions, 8);
        const languages = list(input.languages, 4);
        const settings: ScoutSettings = { regions: regions.length ? regions : base.regions, languages: languages.length ? languages : base.languages, notes: str(input.notes, 500) };
        const now = new Date().toISOString();
        const runs = sameDay(db.scout.report?.at, now) ? (db.scout.report?.runs ?? 0) + 1 : 1;
        const report = await runScout(profile, settings, db.scout.history, lang, runs);
        const scout = await updateDB((d) => {
          d.scout.settings = settings;
          d.scout.report = report;
          if (!report.demo) {
            d.scout.history = [
              { at: report.at, headline: report.output.headline, regions: report.output.regions.map((r) => ({ region: r.region, heat: r.heat })) },
              ...d.scout.history.filter((h) => !sameDay(h.at, report.at)),
            ].slice(0, 30);
          }
          return d.scout;
        });
        return NextResponse.json({ scout });
      }

      case "saveJob": {
        const input = (body.job ?? {}) as Record<string, unknown>;
        const job: WishJob = { id: newId(), company: "", title: "", location: "", url: "", tier: "", visa: "", posted: "", fit: "", decision: "Deciding", notes: "", savedAt: new Date().toISOString(), lastChecked: null, open: null };
        for (const f of JOB_FIELDS) job[f] = str(input[f]);
        const scout = await updateDB((d) => {
          if (!job.url || !d.scout.wishlist.some((j) => j.url === job.url)) d.scout.wishlist.unshift(job);
          return d.scout;
        });
        return NextResponse.json({ scout });
      }

      case "saveCompany": {
        const input = (body.company ?? {}) as Record<string, unknown>;
        const row: WatchCompany = { id: newId(), company: "", careersUrl: "", why: "", roleType: "", contact: "", status: "Watching", notes: "", addedAt: new Date().toISOString(), lastChecked: null, openings: [], openingsNote: "" };
        for (const f of COMPANY_FIELDS) row[f] = str(input[f]);
        const scout = await updateDB((d) => {
          const name = row.company.trim().toLowerCase();
          if (!name || !d.scout.companies.some((c) => c.company.trim().toLowerCase() === name)) d.scout.companies.unshift(row);
          return d.scout;
        });
        return NextResponse.json({ scout });
      }

      case "checkJob": {
        const job = db.scout.wishlist.find((j) => j.id === body.id);
        if (!job) return fail("That job is no longer in the wish list.", 404);
        const page = job.url ? await readJobPage(job.url) : null;
        const scout = await updateDB((d) => {
          const row = d.scout.wishlist.find((j) => j.id === body.id);
          if (row) Object.assign(row, { lastChecked: new Date().toISOString(), open: page ? "open" : "unconfirmed" });
          return d.scout;
        });
        return NextResponse.json({ scout });
      }

      case "checkCompany":
      case "people": {
        if (!profile.savedAt || profile.resumeText.trim().length < 200) return fail("Save your profile with a resume first.");
        const company = db.scout.companies.find((c) => c.id === body.id);
        if (!company) return fail("That company is no longer in the list.", 404);
        if (!company.company.trim()) return fail("Give the company a name first.");
        if (body.kind === "checkCompany") {
          const result = await checkCompany(profile, company, lang);
          const scout = await updateDB((d) => {
            const row = d.scout.companies.find((c) => c.id === body.id);
            if (row) Object.assign(row, { openings: result.openings, openingsNote: result.note, openingsAudit: result.audit, lastChecked: new Date().toISOString() });
            return d.scout;
          });
          return NextResponse.json({ scout });
        }
        const people = await findPeople(profileBlock(profile), { company: company.company, title: company.roleType || profile.roles.join(" / "), location: profile.regions.join(", ") }, lang, (company.people?.runs ?? 0) + 1);
        const scout = await updateDB((d) => {
          const row = d.scout.companies.find((c) => c.id === body.id);
          if (row) row.people = people;
          return d.scout;
        });
        return NextResponse.json({ scout });
      }
    }
    return fail("Unknown request.");
  } catch (err) {
    if (err instanceof AgentError) return fail(err.message, 502);
    console.error(err);
    return fail("Something went wrong on the server. Check the terminal for details.", 500);
  }
}

/** Inline edits to a wish list job or a target company. */
export async function PATCH(req: Request) {
  const body = (await req.json()) as Record<string, unknown>;
  const scout = await updateDB((d) => {
    if (body.list === "jobs") {
      const row = d.scout.wishlist.find((j) => j.id === body.id);
      if (row) {
        for (const f of JOB_FIELDS) if (typeof body[f] === "string") row[f] = str(body[f]);
        if (WISH_DECISIONS.includes(body.decision as never)) row.decision = body.decision as WishJob["decision"];
      }
    } else {
      const row = d.scout.companies.find((c) => c.id === body.id);
      if (row) {
        for (const f of COMPANY_FIELDS) if (typeof body[f] === "string") row[f] = str(body[f]);
        if (COMPANY_STATUSES.includes(body.status as never)) row.status = body.status as WatchCompany["status"];
      }
    }
    return d.scout;
  });
  return NextResponse.json({ scout });
}

export async function DELETE(req: Request) {
  const q = new URL(req.url).searchParams;
  const id = q.get("id");
  const scout = await updateDB((d) => {
    if (q.get("list") === "jobs") d.scout.wishlist = d.scout.wishlist.filter((j) => j.id !== id);
    else d.scout.companies = d.scout.companies.filter((c) => c.id !== id);
    return d.scout;
  });
  return NextResponse.json({ scout });
}
