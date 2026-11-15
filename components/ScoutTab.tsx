"use client";

import { useState } from "react";
import { COMPANY_STATUSES, WISH_DECISIONS, type LinkStatus, type ScoutData, type ScoutJob, type ScoutSettings, type WatchCompany, type WishJob } from "@/lib/schemas";
import { PeopleList } from "./People";
import { api, AuditBox, Btn, Chips, LabelBadge, Quote, RetryButton, send, useApp, Working } from "./ui";

type View = "scan" | "wish" | "companies";
type Res = { scout: ScoutData };

const VISA = { offered: ["Sponsorship stated", "good"], not_mentioned: ["Visa not mentioned", "warn"], needs_confirmation: ["Visa needs confirmation", "warn"] } as const;
const HEAT = { warming: ["Warming", "good"], steady: ["Steady", ""], cooling: ["Cooling", "bad"], unknown: ["No clear signal", "warn"] } as const;
const LINK: Record<LinkStatus, [string, string]> = { verified: ["Link opened and read", "good"], unverified: ["Could not read the page. Open it to check", "warn"], sample: ["Sample", "warn"] };
const day = (iso: string | null) => (iso ? iso.slice(0, 10) : "");
const isLink = (u: string) => /^https?:\/\//.test(u);

export function ScoutTab() {
  const { state, t } = useApp();
  const [view, setView] = useState<View>("scan");
  const { wishlist, companies } = state.scout;
  const fresh = companies.reduce((n, c) => n + c.openings.filter((o) => o.isNew).length, 0);

  return (
    <div className="plain">
      {!state.profile.savedAt && <p className="note">{t("Save your profile first. The search is based on it.")}</p>}
      <div className="pills" role="tablist">
        <button role="tab" aria-selected={view === "scan"} onClick={() => setView("scan")}>{t("Headhunter scan")}</button>
        <button role="tab" aria-selected={view === "wish"} onClick={() => setView("wish")}>{t("Wish list")} ({wishlist.length})</button>
        <button role="tab" aria-selected={view === "companies"} onClick={() => setView("companies")}>{t("Target companies")} ({companies.length}){fresh > 0 && <> · {fresh} {t("new")}</>}</button>
      </div>
      <div hidden={view !== "scan"}><Scan /></div>
      <div hidden={view !== "wish"}><WishList /></div>
      <div hidden={view !== "companies"}><Companies /></div>
    </div>
  );
}

/* ---------- Headhunter scan ---------- */

function useScout() {
  const app = useApp();
  const apply = (r: Res | undefined) => {
    if (r) app.patch({ scout: r.scout });
    return r;
  };
  const post = (key: string, body: Record<string, unknown>) => app.run(key, async () => apply(await send<Res>("POST", "/api/scout", { lang: app.lang, ...body })));
  return { ...app, scout: app.state.scout, post, apply };
}

function Scan() {
  const { state, scout, t, toast, post } = useScout();
  const p = state.profile;
  const [settings, setSettings] = useState<ScoutSettings>(scout.settings ?? { regions: p.regions.length ? p.regions : ["Global remote"], languages: ["English"], notes: "" });
  const report = scout.report;
  const o = report?.output;
  const saved = new Set(scout.wishlist.map((j) => j.url));
  const watched = new Set(scout.companies.map((c) => c.company.trim().toLowerCase()));

  const scan = () => post("scout", { kind: "run", settings });
  const saveJob = async (j: ScoutJob) => {
    if (await post("save", { kind: "saveJob", job: { ...j, visa: j.visaNote || t(VISA[j.visa][0]) } })) toast(t("Saved to your wish list."));
  };
  const watch = async (company: string, extra: Partial<WatchCompany> = {}) => {
    if (await post("save", { kind: "saveCompany", company: { company, ...extra } })) toast(t("Added to target companies."));
  };

  return (
    <>
      <div className="card">
        <h2>{t("Your headhunter")}</h2>
        <p className="sub">
          {t("Searches the web for openings and companies that fit your saved profile, and reads the market in each region. Roles, domains, work type and sponsorship come from step 1.")}
        </p>
        <div className="f">
          <label htmlFor="scout-regions">{t("Regions to scan")} <small>{t("up to 8, one search round each")}</small></label>
          <Chips id="scout-regions" items={settings.regions} max={8} onChange={(regions) => setSettings({ ...settings, regions })} />
        </div>
        <div className="f">
          <label htmlFor="scout-langs">{t("Working languages you accept")} <small>{t("postings in other languages are excluded")}</small></label>
          <Chips id="scout-langs" items={settings.languages} max={4} onChange={(languages) => setSettings({ ...settings, languages })} />
        </div>
        <div className="f">
          <label htmlFor="scout-notes">{t("Notes for the headhunter")} <small>{t("optional")}</small></label>
          <textarea id="scout-notes" style={{ minHeight: 64 }} maxLength={500} placeholder={t("For example: compare Europe with other regions; include adjacent industries.")} value={settings.notes} onChange={(e) => setSettings({ ...settings, notes: e.target.value })} />
        </div>
        <div className="row">
          {report ? <RetryButton runs={report.runs} feature="scout" busyKey="scout" onRetry={scan} label="Scan again" /> : <Btn primary busyKey="scout" disabled={!p.savedAt} onClick={scan}>{t("Run today's scan")}</Btn>}
          {report && <span className="sub">{t("Last scan")}: {report.at.slice(0, 16).replace("T", " ")}</span>}
        </div>
        <p className="sub">{t("The scan runs when you press the button; the app does not run in the background. A scan takes several minutes.")}</p>
        <Working busyKey="scout" />
      </div>

      {report && o && (
        <>
          <div className="card">
            <h2>{t("Market today")}</h2>
            <p><b>{o.headline}</b></p>
            {o.regions.map((r) => (
              <div className="it" key={r.region}>
                <div className="row">
                  <h3 className="grow">{r.region}</h3>
                  <span className={`badge ${HEAT[r.heat][1]}`}>{t(HEAT[r.heat][0])}</span>
                  <LabelBadge label={r.label} />
                  {isLink(r.sourceUrl) && <a href={r.sourceUrl} target="_blank" rel="noopener noreferrer">{t("Source")}</a>}
                </div>
                <p className="sub">{r.summary}</p>
              </div>
            ))}
            {o.weekly && <><h3>{t("Against the past week")}</h3><p className="sub">{o.weekly}</p></>}
            {o.priorities.length > 0 && <><h3>{t("Do first today")}</h3><ul>{o.priorities.map((x) => <li key={x}>{x}</li>)}</ul></>}
            {o.unreachable.length > 0 && <p className="sub">{t("Could not be opened this run")}: {o.unreachable.join("; ")}</p>}
          </div>

          <div className="card">
            <h2>{t("Openings worth a look")} ({o.jobs.length})</h2>
            <p className="sub">{t("The app opened every link itself. Nothing here is applied to automatically: save what interests you and decide later.")}{report.dropped > 0 && <> {report.dropped} {t("items were removed because they had no real link.")}</>}</p>
            {o.jobs.length === 0 && <p className="sub">{t("Nothing passed the filters today. That is a valid result; the filters were not relaxed.")}</p>}
            {o.jobs.map((j) => {
              const link = LINK[report.links[j.url] ?? "unverified"];
              return (
                <div className="it" key={j.url}>
                  <div className="row">
                    <span className="badge">{t("Tier")} {j.tier}</span>
                    <div className="grow"><h3>{j.title}</h3><p className="sub">{j.company} · {j.location}</p></div>
                    <a href={j.url} target="_blank" rel="noopener noreferrer">{t("Open posting")}</a>
                  </div>
                  <div className="row sub">
                    <span className={`badge ${VISA[j.visa][1]}`}>{t(VISA[j.visa][0])}</span>
                    <span className={`badge ${link[1]}`}>{t(link[0])}</span>
                    <span>{t("Posted")}: {j.posted === "unverified" || !j.posted ? t("date not verified") : j.posted}</span>
                    <LabelBadge label={j.label} />
                  </div>
                  {j.visaNote && <p className="sub">{j.visaNote}</p>}
                  <p>{j.fit}</p>
                  <p><Quote e={j.proof} failed={report.quoteCheck.failed} /></p>
                  <div className="row">
                    <Btn small busyKey="save" disabled={saved.has(j.url)} onClick={() => saveJob(j)}>{t(saved.has(j.url) ? "In wish list" : "Save to wish list")}</Btn>
                    <Btn small busyKey="save" disabled={watched.has(j.company.trim().toLowerCase())} onClick={() => watch(j.company, { roleType: j.title })}>{t(watched.has(j.company.trim().toLowerCase()) ? "Company is tracked" : "Track this company")}</Btn>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="card">
            <h2>{t("Companies worth approaching")} ({o.companies.length})</h2>
            <p className="sub">{t("No exactly matching opening right now, but a close fit with a recent signal.")}</p>
            {o.companies.map((c) => {
              const tracked = watched.has(c.company.trim().toLowerCase());
              return (
                <div className="it" key={c.company}>
                  <div className="row">
                    <h3 className="grow">{c.company}</h3>
                    <LabelBadge label={c.label} />
                    {isLink(c.url) && <a href={c.url} target="_blank" rel="noopener noreferrer">{t("Careers page")}</a>}
                  </div>
                  <p className="sub"><b>{t("Signal")}</b>: {c.signal} {isLink(c.signalUrl) && <a href={c.signalUrl} target="_blank" rel="noopener noreferrer">{t("Source")}</a>}</p>
                  <p>{c.why}</p>
                  <p className="sub"><b>{t("Role to pitch")}</b>: {c.roleType} · <b>{t("How to approach")}</b>: {c.approach}</p>
                  <p><Quote e={c.proof} failed={report.quoteCheck.failed} /></p>
                  <div className="row">
                    <Btn small busyKey="save" disabled={tracked} onClick={() => watch(c.company, { careersUrl: c.url, why: c.why, roleType: c.roleType, contact: c.approach })}>{t(tracked ? "Company is tracked" : "Add to target companies")}</Btn>
                  </div>
                </div>
              );
            })}
            <p className="sub">{t("Jobs, companies and market signals come from web search and are outside what the auditors can verify. The auditors check what is said about you.")}</p>
            <AuditBox r={report} />
          </div>
        </>
      )}
    </>
  );
}

/* ---------- Wish list ---------- */

function WishList() {
  const { scout, t, toast, post, apply, run, patch, state, openJD } = useScout();
  const rows = scout.wishlist;
  const edit = (id: string, change: Partial<WishJob>) => patch({ scout: { ...state.scout, wishlist: rows.map((r) => (r.id === id ? { ...r, ...change } : r)) } });
  const commit = (id: string, change: Partial<WishJob>) => {
    edit(id, change);
    send("PATCH", "/api/scout", { list: "jobs", id, ...change }).catch(() => toast(t("Could not save the change.")));
  };
  const remove = (id: string) => run("wish", async () => apply(await api<Res>(`/api/scout?list=jobs&id=${id}`, { method: "DELETE" })));
  const cell = (row: WishJob, field: "company" | "title" | "location" | "url" | "notes", label: string) => (
    <input type="text" id={`w-${field}-${row.id}`} aria-label={t(label)} value={row[field]} onChange={(e) => edit(row.id, { [field]: e.target.value })} onBlur={(e) => commit(row.id, { [field]: e.target.value })} />
  );

  return (
    <div className="card tracker">
      <h2>{t("Wish list")}</h2>
      <p className="sub">{t("Jobs you are not ready to apply for yet. Come back, check they are still open, and decide. Analyse sends the link to step 3.")}</p>
      <div className="row"><Btn small busyKey="save" onClick={() => post("save", { kind: "saveJob", job: {} })}>{t("+ Add job")}</Btn></div>
      {rows.length === 0 ? (
        <p className="sub">{t("Nothing saved yet. Save an opening from the scan, or add one by hand.")}</p>
      ) : (
        <div className="tw">
          <table>
            <thead>
              <tr>{["Company", "Job position", "Location", "Job link", "Fit", "Decision", "Still open?", "Notes", "Saved"].map((h) => <th key={h}>{t(h)}</th>)}<th /></tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{cell(row, "company", "Company")}</td>
                  <td>{cell(row, "title", "Job position")}</td>
                  <td>{cell(row, "location", "Location")}</td>
                  <td>{cell(row, "url", "Job link")}</td>
                  <td className="sub" style={{ minWidth: 200 }}>{row.tier && <span className="badge">{t("Tier")} {row.tier}</span>} {row.fit}{row.visa && <> · {row.visa}</>}</td>
                  <td>
                    <select id={`w-decision-${row.id}`} aria-label={t("Decision")} value={row.decision} onChange={(e) => commit(row.id, { decision: e.target.value as WishJob["decision"] })}>
                      {WISH_DECISIONS.map((s) => <option key={s} value={s}>{t(s)}</option>)}
                    </select>
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {row.open && <span className={`badge ${row.open === "open" ? "good" : "warn"}`}>{t(row.open === "open" ? "Open" : "Could not confirm")}</span>}{" "}
                    <span className="sub">{day(row.lastChecked)}</span>{" "}
                    <Btn small busyKey={`chk-${row.id}`} disabled={!isLink(row.url)} onClick={() => post(`chk-${row.id}`, { kind: "checkJob", id: row.id })}>{t("Check")}</Btn>
                  </td>
                  <td>{cell(row, "notes", "Notes")}</td>
                  <td className="sub">{day(row.savedAt)}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {isLink(row.url) && <a className="btn s" href={row.url} target="_blank" rel="noopener noreferrer">{t("Open link")}</a>}{" "}
                    <button type="button" className="btn s" disabled={!isLink(row.url)} onClick={() => openJD(row.url)}>{t("Analyse")}</button>{" "}
                    <button type="button" className="btn s" aria-label={t("Delete row")} onClick={() => remove(row.id)}>✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------- Target companies ---------- */

function Companies() {
  const { scout, t, toast, post, apply, run, patch, state } = useScout();
  const rows = scout.companies;
  const [open, setOpen] = useState<string | null>(null);
  const saved = new Set(scout.wishlist.map((j) => j.url));
  const edit = (id: string, change: Partial<WatchCompany>) => patch({ scout: { ...state.scout, companies: rows.map((r) => (r.id === id ? { ...r, ...change } : r)) } });
  const commit = (id: string, change: Partial<WatchCompany>) => {
    edit(id, change);
    send("PATCH", "/api/scout", { list: "companies", id, ...change }).catch(() => toast(t("Could not save the change.")));
  };
  const remove = (id: string) => run("co", async () => apply(await api<Res>(`/api/scout?list=companies&id=${id}`, { method: "DELETE" })));
  const cell = (row: WatchCompany, field: "company" | "careersUrl" | "why" | "contact" | "notes", label: string) => (
    <input type="text" id={`c-${field}-${row.id}`} aria-label={t(label)} value={row[field]} onChange={(e) => edit(row.id, { [field]: e.target.value })} onBlur={(e) => commit(row.id, { [field]: e.target.value })} />
  );
  const detail = rows.find((r) => r.id === open) ?? null;
  const act = async (id: string, kind: "checkCompany" | "people") => {
    setOpen(id);
    await post(`${kind}-${id}`, { kind, id });
  };

  return (
    <>
      <div className="card tracker">
        <h2>{t("Target companies")}</h2>
        <p className="sub">{t("Companies you keep coming back to: check for new openings, and keep track of who you have reached out to.")}</p>
        <div className="row"><Btn small busyKey="save" onClick={() => post("save", { kind: "saveCompany", company: {} })}>{t("+ Add company")}</Btn></div>
        {rows.length === 0 ? (
          <p className="sub">{t("No companies yet. Add one from the scan, or by hand.")}</p>
        ) : (
          <div className="tw">
            <table>
              <thead>
                <tr>{["Company", "Careers page", "Why this company", "Status", "Contact and outreach", "Notes", "Openings", "Last checked"].map((h) => <th key={h}>{t(h)}</th>)}<th /></tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const fresh = row.openings.filter((x) => x.isNew).length;
                  return (
                    <tr key={row.id}>
                      <td>{cell(row, "company", "Company")}</td>
                      <td>{cell(row, "careersUrl", "Careers page")}</td>
                      <td>{cell(row, "why", "Why this company")}</td>
                      <td>
                        <select id={`c-status-${row.id}`} aria-label={t("Status")} value={row.status} onChange={(e) => commit(row.id, { status: e.target.value as WatchCompany["status"] })}>
                          {COMPANY_STATUSES.map((s) => <option key={s} value={s}>{t(s)}</option>)}
                        </select>
                      </td>
                      <td>{cell(row, "contact", "Contact and outreach")}</td>
                      <td>{cell(row, "notes", "Notes")}</td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <button type="button" className="btn s" onClick={() => setOpen(open === row.id ? null : row.id)}>{row.openings.length}{fresh > 0 && <> · {fresh} {t("new")}</>}</button>
                      </td>
                      <td className="sub">{day(row.lastChecked) || t("Never")}</td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <Btn small busyKey={`checkCompany-${row.id}`} disabled={!row.company.trim()} onClick={() => act(row.id, "checkCompany")}>{t("Check openings")}</Btn>{" "}
                        <Btn small busyKey={`people-${row.id}`} disabled={!row.company.trim()} onClick={() => act(row.id, "people")}>{t("Find people")}</Btn>{" "}
                        <button type="button" className="btn s" aria-label={t("Delete row")} onClick={() => remove(row.id)}>✕</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {detail && (
        <div className="card">
          <div className="row"><h2 className="grow">{detail.company || t("Untitled")}</h2><button type="button" className="btn s" onClick={() => setOpen(null)}>{t("Close")}</button></div>
          <Working busyKey={`checkCompany-${detail.id}`} />
          <Working busyKey={`people-${detail.id}`} />
          <h3>{t("Openings")} {detail.lastChecked && <small className="sub">· {t("Last checked")} {day(detail.lastChecked)}</small>}</h3>
          {!detail.lastChecked && <p className="sub">{t("Not checked yet. Check openings searches this company's careers page for roles that fit your profile.")}</p>}
          {detail.lastChecked && detail.openings.length === 0 && <p className="sub">{t("No fitting opening found at the last check.")}</p>}
          {detail.openings.map((x) => (
            <div className="it" key={x.url}>
              <div className="row">
                <div className="grow"><h3>{x.title}</h3><p className="sub">{x.location} · {t("First seen")} {day(x.firstSeen)}</p></div>
                {x.isNew && <span className="badge good">{t("New")}</span>}
                <span className={`badge ${LINK[x.link][1]}`}>{t(LINK[x.link][0])}</span>
                <a href={x.url} target="_blank" rel="noopener noreferrer">{t("Open posting")}</a>
              </div>
              <p className="sub">{x.fit}</p>
              <div><Btn small busyKey="save" disabled={saved.has(x.url)} onClick={() => post("save", { kind: "saveJob", job: { company: detail.company, title: x.title, location: x.location, url: x.url, fit: x.fit } })}>{t(saved.has(x.url) ? "In wish list" : "Save to wish list")}</Btn></div>
            </div>
          ))}
          {detail.openingsNote && <p className="sub">{detail.openingsNote}</p>}
          {detail.openingsAudit && <AuditBox r={detail.openingsAudit} />}

          {detail.people && (
            <>
              <h3>{t("People to reach")}</h3>
              <p className="sub">{t("Found through public web search. Titles can be out of date, so open each profile before sending.")}</p>
              <PeopleList
                targets={detail.people.output.targets}
                action={(p) => <button type="button" className="btn s" onClick={() => { commit(detail.id, { contact: `${p.name} · ${p.title}` }); toast(t("Saved as the contact for this company.")); }}>{t("Save as my contact for this company")}</button>}
              />
              <p className="sub">{detail.people.output.note}</p>
              <AuditBox r={detail.people} />
            </>
          )}
        </div>
      )}
    </>
  );
}
