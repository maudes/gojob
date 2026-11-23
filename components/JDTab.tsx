"use client";

import { useEffect, useRef, useState } from "react";
import type { ActionKind, AnalysisRecord, TrackerRow } from "@/lib/schemas";
import { fill, tier, today, trackerTSV } from "@/lib/text";
import { PeopleList } from "./People";
import { ResumeReview, type Accepted } from "./ResumeReview";
import { api, AuditBox, Btn, copy, download, LabelBadge, Quote, RetryButton, Reviewers, saveBlob, send, useApp, Working } from "./ui";

const TABS: [ActionKind, string][] = [
  ["fineTune", "Fine tune"],
  ["coverLetter", "Cover letter"],
  ["interview", "Interview"],
  ["onePager", "One-pager"],
  ["networking", "Networking"],
];
const TIER = { apply: ["dot on", "Apply now"], tune: ["dot mid", "Fine-tune first, then re-assess"], risky: ["dot", "Risky. Suggest not applying"] } as const;
const VERDICT = { green: "good", mint: "good", yellow: "warn", orange: "warn", red: "bad" } as const;
const FIT = { ok: "good", risk: "bad", unknown: "warn" } as const;
const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;

export function JDTab() {
  const { state, t, jdLink } = useApp();
  const [selected, setSelected] = useState<string | null>(state.analyses[0]?.id ?? null);
  // A link sent from the wish list opens the empty form with that link filled in.
  useEffect(() => {
    if (jdLink) setSelected(null);
  }, [jdLink]);
  const record = state.analyses.find((a) => a.id === selected) ?? null;

  return (
    <div className="layout">
      <div className="side">
        <button type="button" className="entry" aria-current={record == null} onClick={() => setSelected(null)}>
          <span className="t1">+ {t("New JD")}</span>
        </button>
        {state.analyses.map((a) => (
          <button type="button" key={a.id} className="entry" aria-current={a.id === selected} onClick={() => setSelected(a.id)}>
            <span className="t1">{a.analysis.output.meta.company || t("Untitled")}</span>
            <span className="sub">{a.gate.average.toFixed(1)} · {a.analysis.output.meta.title}</span>
          </button>
        ))}
      </div>
      <div className="plain">
        {!state.profile.savedAt && <p className="note">{t("Save your profile first. Every JD assessment is based on it.")}</p>}
        {record ? <Result key={record.id} record={record} onDeleted={() => setSelected(null)} /> : <NewJD onDone={setSelected} />}
      </div>
    </div>
  );
}

/* ---------- Landing: link or pasted text ---------- */

function NewJD({ onDone }: { onDone: (id: string) => void }) {
  const { t, run, lang, putRecord, state, jdLink, openJD } = useApp();
  const [url, setUrl] = useState(jdLink);
  useEffect(() => {
    if (jdLink) setUrl(jdLink);
  }, [jdLink]);
  const [text, setText] = useState("");
  const [fallback, setFallback] = useState(false);

  const analyse = () =>
    run("analyze", async () => {
      let jdText = text.trim();
      if (!jdText && url.trim()) {
        const r = await send<{ ok: boolean; text?: string }>("POST", "/api/jd-fetch", { url: url.trim() });
        if (!r.ok || !r.text) {
          setFallback(true);
          return;
        }
        jdText = r.text;
        setText(jdText);
      }
      setFallback(false);
      const r = await send<{ record: AnalysisRecord }>("POST", "/api/run", { kind: "analyze", lang, jdUrl: url.trim(), jdText });
      putRecord(r.record);
      if (jdLink) openJD("");
      onDone(r.record.id);
    });

  return (
    <div className="card">
      <h2>{t("Target JD")}</h2>
      <div className="f">
        <label htmlFor="jd-url">{t("Job link")}</label>
        <input type="url" id="jd-url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
      </div>
      <div className="f">
        <label htmlFor="jd-text">{t("Job description")}</label>
        <textarea id="jd-text" style={{ minHeight: 160 }} placeholder={t("Optional if the link can be read")} value={text} onChange={(e) => setText(e.target.value)} />
      </div>
      {fallback && <p className="note">{t("This page could not be read. Paste the job description above, then run the analysis again.")}</p>}
      <div className="row">
        <Btn primary busyKey="analyze" disabled={!state.profile.savedAt || (!url.trim() && text.trim().length < 300)} onClick={analyse}>{t("Analysis")}</Btn>
      </div>
      <Working busyKey="analyze" />
    </div>
  );
}

/* ---------- Matching assessment + follow-ups ---------- */

function Result({ record, onDeleted }: { record: AnalysisRecord; onDeleted: () => void }) {
  const app = useApp();
  const { state, t, run, lang, putRecord, patch, toast, go } = app;
  const [tab, setTab] = useState<ActionKind>("fineTune");
  const fileRef = useRef<HTMLInputElement>(null);
  const a = record.analysis.output;
  const failed = record.analysis.quoteCheck.failed;
  const resume = record.tailoredText ?? state.profile.resumeText;
  const changed = resume !== record.assessedText;
  const [dotClass, tierLabel] = TIER[tier(record.gate.average, record.gate.min, state.config.thresholds.jd)];
  const first = record.history[0]?.average ?? record.gate.average;
  const delta = record.gate.average - first;

  const reassess = () =>
    run("reassess", async () => {
      const r = await send<{ record: AnalysisRecord; changed: boolean }>("POST", "/api/run", { kind: "reanalyze", lang, id: record.id });
      putRecord(r.record);
      const h = r.record.history;
      if (r.changed && h.length > 1) toast(`${t("Re-assessed with the revised resume")}: ${h[h.length - 2].average.toFixed(1)} → ${h[h.length - 1].average.toFixed(1)}`);
    });

  const uploadRevised = (file: File) =>
    run("upload-jd", async () => {
      const form = new FormData();
      form.append("file", file);
      const r = await api<{ record: AnalysisRecord }>(`/api/upload?id=${record.id}`, { method: "POST", body: form });
      putRecord(r.record);
      toast(t("Revised resume loaded for this JD. Re-assess to see the new score."));
    });

  const logApplication = async () => {
    const row: Omit<TrackerRow, "id"> = {
      company: a.meta.company,
      position: a.meta.title,
      location: a.meta.location,
      jobLink: record.jdUrl,
      oneLine: a.meta.oneLine,
      matchingScore: record.gate.average.toFixed(1),
      applyDate: today(),
      networkTarget: record.networkTarget,
      status: "Apply",
      notes: "",
    };
    // Copy and open the sheet first, while the click still counts as a user action.
    const copied = await copy(trackerTSV(row));
    if (state.profile.sheetUrl) window.open(state.profile.sheetUrl, "_blank", "noopener");
    const r = await run("log", () => send<{ tracker: TrackerRow[] }>("POST", "/api/tracker", row));
    if (!r) return;
    patch({ tracker: r.tracker });
    go("tracker");
    toast(
      !copied ? t("Row added to the tracker. Copying was blocked; use Copy row there.")
        : state.profile.sheetUrl ? t("Row added and copied. Paste it into the first empty row of your sheet.")
        : t("Row added and copied. Add your Google Sheet link in the tracker to open it automatically."),
    );
  };

  const remove = () =>
    run("delete", async () => {
      await api(`/api/run?id=${record.id}`, { method: "DELETE" });
      patch({ analyses: state.analyses.filter((x) => x.id !== record.id) });
      onDeleted();
    });

  return (
    <>
      <div className="card">
        <div className="row">
          <div className="grow">
            <h2>{a.meta.title || t("Untitled")}</h2>
            <p className="sub">
              {[a.meta.company, a.meta.location].filter(Boolean).join(" · ")}
              {record.jdUrl && <> · <a href={record.jdUrl} target="_blank" rel="noopener noreferrer">{t("Job link")}</a></>}
            </p>
          </div>
          <input ref={fileRef} type="file" hidden accept=".docx,.pdf,.txt,.md" onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadRevised(f); e.target.value = ""; }} />
          <Btn small busyKey="upload-jd" onClick={() => fileRef.current?.click()}>{t("Upload revised resume")}</Btn>
          {changed ? (
            <Btn small primary busyKey="reassess" onClick={reassess}>{t("Re-assess")}</Btn>
          ) : (
            <RetryButton runs={record.analysis.runs} feature="jd-assessment" busyKey="reassess" onRetry={reassess} />
          )}
          <Btn primary busyKey="log" onClick={logApplication}>{t("Log application")}</Btn>
        </div>
        <Working busyKey="reassess" />
        {changed && <p className="note info">{t("The resume for this JD changed since the last assessment. Re-assess to update everything below.")}</p>}
        {record.ceiling && <p className="note bad">{ceilingText(record.ceiling, t)}</p>}
        <div className="gate">
          <div className="big">{record.gate.average.toFixed(1)}</div>
          <div className="grow">
            <div className="light"><span className={dotClass} />{t(tierLabel)}</div>
            <div className="sub">{fill(t("Apply: average ≥ {average} and every reviewer ≥ {min} · fine-tune and re-assess: average {tuneFrom} or more · below {tuneFrom} risky, suggest not applying"), state.config.thresholds.jd)}</div>
            <div className="sub">
              {t("Assessment history")}: {record.history.map((h, i) => `v${i + 1} ${h.average.toFixed(1)}`).join(" → ")}
              {record.history.length > 1 && ` (${delta >= 0 ? "+" : ""}${delta.toFixed(1)})`}
            </div>
          </div>
        </div>
        <Reviewers panel={record.panel} />
        {record.panelAudit && <AuditBox r={record.panelAudit} title="Review of the three scores" />}
        <p className="sub">{a.companyContext}</p>
        <div className="tw">
          <table>
            <thead><tr><th>{t("Metric")}</th><th>{t("Assessment")}</th><th>{t("Basis")}</th></tr></thead>
            <tbody>
              <tr><td>{t("Strategy verdict")}</td><td><span className={`badge ${VERDICT[a.strategy.verdict]}`}>{a.strategy.verdict}</span></td><td>{a.strategy.instruction}</td></tr>
              <tr><td>{t("Current ATS match")}</td><td className="n">{Math.round(a.atsMatch.score)}%</td><td>{a.atsMatch.basis}</td></tr>
              <tr><td>{t("Recruiter interview probability")}</td><td className="n">{Math.round(a.recruiterProbability.score)}%</td><td>{a.recruiterProbability.basis}</td></tr>
              <tr><td>{t("Projected ATS after revisions")}</td><td className="n">{Math.round(a.projectedAts.score)}%</td><td>{a.projectedAts.basis}</td></tr>
            </tbody>
          </table>
        </div>
        <div className="tw">
          <table>
            <thead><tr><th>{t("JD requirement")}</th><th>{t("Your evidence")}</th><th>{t("Label")}</th><th>{t("Note")}</th></tr></thead>
            <tbody>
              {a.requirements.map((r, i) => (
                <tr key={i}><td><Quote e={r.requirement} failed={failed} /></td><td><Quote e={r.evidence} failed={failed} /></td><td><LabelBadge label={r.label} /></td><td>{r.note}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="tw">
          <table>
            <thead><tr><th>{t("Missing keyword")}</th><th>{t("Where to add")}</th><th>{t("Why")}</th><th>{t("Label")}</th></tr></thead>
            <tbody>
              {a.missingKeywords.map((k) => (
                <tr key={k.keyword}><td><b>{k.keyword}</b></td><td>{k.whereToAdd}</td><td>{k.reason}</td><td><LabelBadge label={k.label} /></td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="row sub">
          <b>{t("Profile fit")}</b>
          {a.profileFit.map((f) => <span key={f.item} className={`badge ${FIT[f.status]}`} title={f.note}>{f.item.replace("_", " ")} {f.status === "ok" ? "✓" : f.status === "risk" ? "✕" : "?"}</span>)}
        </div>
        <AuditBox r={record.analysis} title="Review of the assessment" />
        <div><button type="button" className="btn s" onClick={remove}>{t("Delete this analysis")}</button></div>
      </div>

      <div className="card">
        <div className="row">
          <h2 className="grow">{t("Follow-up actions")}</h2>
          <div className="pills sm" role="tablist">
            {TABS.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{t(label)}</button>)}
          </div>
        </div>
        <FollowUp key={tab} record={record} kind={tab} resume={resume} onReassess={reassess} changed={changed} />
      </div>
    </>
  );
}

const CEILING_TEXT = {
  no_evidence_left: "Tuning has reached its ceiling. Every remaining suggestion needs experience the resume does not show, so rewording cannot raise the score.",
  score_plateau: "Tuning has reached its ceiling. The last resume change raised the score by less than 1 point, so more rewording will not help.",
} as const;

function ceilingText(c: NonNullable<AnalysisRecord["ceiling"]>, t: (s: string) => string) {
  const gain = c.gain === undefined ? "" : ` (${c.gain >= 0 ? "+" : ""}${c.gain.toFixed(1)})`;
  return `${t(CEILING_TEXT[c.reason])}${gain} ${t("Add real experience to the resume and upload it, or choose another job.")}`;
}

function FollowUp({ record, kind, resume, onReassess, changed }: { record: AnalysisRecord; kind: ActionKind; resume: string; onReassess: () => void; changed: boolean }) {
  const { t, run, lang, putRecord, toast } = useApp();
  const [input, setInput] = useState("");
  const busyKey = `action-${kind}`;
  const generate = () =>
    run(busyKey, async () => {
      const r = await send<{ record: AnalysisRecord }>("POST", "/api/run", { kind: "action", lang, id: record.id, action: kind, input });
      putRecord(r.record);
    });
  const retry = (runs: number) => <RetryButton runs={runs} feature={kind} busyKey={busyKey} onRetry={generate} label="Retry this tab only" />;
  const start = (label: string, hint: string) => (
    <div className="plain">
      <div className="row"><Btn primary busyKey={busyKey} onClick={generate}>{t(label)}</Btn><span className="sub">{t(hint)}</span></div>
      <Working busyKey={busyKey} />
    </div>
  );

  if (kind === "fineTune") {
    const r = record.actions.fineTune;
    if (!r && record.ceiling) return <div className="plain"><p className="note bad">{ceilingText(record.ceiling, t)}</p></div>;
    if (!r) return start("Fine-tune my resume for this JD", "Goes through every line and suggests tracked changes in the JD's language.");
    const applyChanges = (accepted: Accepted[], rejected: string[]) =>
      run("apply-jd", async () => {
        const res = await send<{ record: AnalysisRecord; missedInFile: string[] }>("POST", "/api/resume-apply", { scope: "jd", id: record.id, accepted, rejected });
        putRecord(res.record);
        toast(res.missedInFile.length ? t("Saved. Some changes could not be placed in the original file; check the download.") : t("Saved to the resume for this JD. Re-assess to see whether the score improved."));
      });
    const o = r.output;
    return (
      <div className="plain">
        <div className="row"><b>{t("Headline tags")}</b>{o.headlineTags.map((x) => <span className="chip" key={x}>{x}</span>)}<span className="grow" />{record.ceiling ? <span className="sub">{t("Ceiling reached")}</span> : retry(r.runs)}</div>
        <Working busyKey={busyKey} />
        <p className="sub">{t("The full resume tailored to this JD. Accept, reject or edit each change, then re-assess to see whether the score improved.")}</p>
        <ResumeReview text={resume} changes={o.changes} exportQuery={`scope=jd&id=${record.id}`} busyKey="apply-jd" onApply={applyChanges} />
        <div className="row">
          <Btn primary={changed} busyKey="reassess" disabled={!changed} onClick={onReassess}>{t("Re-assess with this resume")}</Btn>
          <span className="sub">{t("Re-runs the whole assessment above: score, three reviewers, table, proof and fidelity review. Never limited after a resume change.")}</span>
        </div>
        {o.bulletOrder.length > 0 && (
          <div className="it">
            <h3>{t("Suggested bullet order")}</h3>
            {o.bulletOrder.map((b) => (
              <div key={b.section}>
                <p><b>{b.section}</b> <span className="sub">{b.reason}</span></p>
                <ol>{b.orderedBullets.map((x) => <li key={x}>{x}</li>)}</ol>
                {b.drop.length > 0 && <p className="sub">{t("Consider dropping")}: {b.drop.join(" / ")}</p>}
              </div>
            ))}
          </div>
        )}
        {o.additions.length > 0 && (
          <div className="it">
            <h3>{t("Skills and side projects to add")}</h3>
            {o.additions.map((x, i) => <p key={i}><LabelBadge label={x.label} /> {x.suggestion} <span className="sub">{x.basis}</span></p>)}
          </div>
        )}
        <AuditBox r={r} />
      </div>
    );
  }

  if (kind === "coverLetter") {
    const r = record.actions.coverLetter;
    const o = r?.output;
    return (
      <div className="plain">
        {o && (
          <div className="it">
            <h3>{t("Step 1 · What this role needs")}</h3>
            <p><LabelBadge label={o.coreProblem.label} /> <b>{t("Core problem")}</b>: {o.coreProblem.text}</p>
          </div>
        )}
        <div className="it">
          <h3>{t("Step 2 · Your reason")}</h3>
          <div className="f">
            <label htmlFor="cover-story">{t("Why this company and this role?")}</label>
            <textarea id="cover-story" style={{ minHeight: 110 }} placeholder={t("Your view of the company and your reason for applying, in your own words. The letter opens with it.")} value={input} onChange={(e) => setInput(e.target.value)} />
          </div>
          <div className="row">
            <Btn primary busyKey={busyKey} onClick={generate}>{t("Write cover letter")}</Btn>
            {r && retry(r.runs)}
          </div>
          <Working busyKey={busyKey} />
          {o?.needsStory && <p className="note">{o.storyRequest}</p>}
        </div>
        {o && !o.needsStory && r && (
          <div className="it">
            <div className="row">
              <h3 className="grow">{t("Step 3 · Draft letter")}</h3>
              <span className="sub">{words(o.letter)} {t("words")}</span>
              <button type="button" className="btn s" onClick={async () => toast(t((await copy(o.letter)) ? "Copied" : "Copying was blocked by the browser."))}>{t("Copy")}</button>
              <button type="button" className="btn s" onClick={() => download(`/api/export?kind=letter&id=${record.id}&format=docx`, toast)}>{t("Download .docx")}</button>
              <button type="button" className="btn s" onClick={() => download(`/api/export?kind=letter&id=${record.id}&format=pdf`, toast)}>{t("Download PDF")}</button>
            </div>
            <div className="paper msg">{o.letter}</div>
            <h3>{t("Fact-check before sending")}</h3>
            <div className="tw">
              <table>
                <thead><tr><th>{t("Claim in the letter")}</th><th>{t("Label")}</th><th>{t("Source")}</th></tr></thead>
                <tbody>{o.factCheck.map((f, i) => <tr key={i}><td>{f.claim}</td><td><LabelBadge label={f.label} /></td><td>{f.proof.source === "profile" ? f.proof.quote : <Quote e={f.proof} failed={r.quoteCheck.failed} />}</td></tr>)}</tbody>
              </table>
            </div>
            <AuditBox r={r} />
          </div>
        )}
      </div>
    );
  }

  if (kind === "interview") {
    const r = record.actions.interview;
    if (!r) return start("Prepare interview questions", "At least 12 in-depth questions from the product lead and the team, with the key points expected.");
    const groups = new Map<string, typeof r.output.questions>();
    for (const q of r.output.questions) {
      const key = /lead|head|manager|director|vp/i.test(q.interviewer) ? "Product lead interview" : "Team interview";
      groups.set(key, [...(groups.get(key) ?? []), q]);
    }
    let n = 0;
    return (
      <div className="plain" id="iv">
        <div className="row">
          <span className="sub grow">{t("Tap a card to see what a strong answer contains")}</span>
          <button type="button" className="btn s" onClick={() => document.querySelectorAll<HTMLDetailsElement>("#iv details.qcard").forEach((d) => (d.open = true))}>{t("Open all")}</button>
          <button type="button" className="btn s" onClick={() => document.querySelectorAll<HTMLDetailsElement>("#iv details.qcard").forEach((d) => (d.open = false))}>{t("Close all")}</button>
          {retry(r.runs)}
        </div>
        <Working busyKey={busyKey} />
        {[...groups].map(([group, qs]) => (
          <div className="plain" key={group}>
            <div className="grp">{t(group)}</div>
            <div className="qgrid">
              {qs.map((q) => (
                <details className="qcard" key={q.question}>
                  <summary>
                    <span className="row"><span className="num">Q{++n}</span><span className="badge">{q.interviewer}</span></span>
                    <span className="qq">{q.question}</span>
                    <span className="hint">{t("Show key points")} ▾</span>
                  </summary>
                  <div className="back">
                    <b>{t("Key elements expected")}</b>
                    <ul>{q.keyElements.map((k) => <li key={k}>{k}</li>)}</ul>
                    <p className="sub"><b>{t("Must prove")}</b>: {q.mustProve}</p>
                    <b>{t("Your evidence")}</b>
                    {q.evidence.quote.trim() ? <Quote e={q.evidence} failed={r.quoteCheck.failed} /> : <p className="sub"><span className="badge bad">{t("Needs confirmation")}</span> {t("No resume evidence. Prepare a real example or state your scope plainly.")}</p>}
                    <p className="sub"><b>{t("Likely concern")}</b>: {q.concern}</p>
                  </div>
                </details>
              ))}
            </div>
          </div>
        ))}
        <details>
          <summary style={{ cursor: "pointer", fontWeight: 600 }}>{t("Risk map")}</summary>
          <div className="tw" style={{ marginTop: 8 }}>
            <table>
              <thead><tr><th>{t("JD requirement")}</th><th>{t("Your evidence")}</th><th>{t("Likely question")}</th><th>{t("Risk")}</th><th>{t("Preparation")}</th></tr></thead>
              <tbody>{r.output.riskMap.map((x, i) => <tr key={i}><td><Quote e={x.requirement} failed={r.quoteCheck.failed} /></td><td><Quote e={x.evidence} failed={r.quoteCheck.failed} /></td><td>{x.likelyQuestion}</td><td>{x.risk}</td><td>{x.preparation}</td></tr>)}</tbody>
            </table>
          </div>
        </details>
        <AuditBox r={r} />
      </div>
    );
  }

  if (kind === "onePager") {
    const r = record.actions.onePager;
    const company = record.analysis.output.meta.company || "company";
    return (
      <div className="plain">
        <div className="row">
          <Btn primary={!r} busyKey={busyKey} onClick={generate}>{t(r ? "Generate again" : "Generate one-pager")}</Btn>
          <span className="sub">{t("No input needed. Company, role and your background come from the JD and your saved profile.")}</span>
        </div>
        <details className="sub">
          <summary>{t("Optional: tailor to an interview round")}</summary>
          <div className="f" style={{ marginTop: 8 }}>
            <label htmlFor="one-round">{t("Interview round / interviewer level")}</label>
            <input type="text" id="one-round" placeholder={t("e.g. Round 2, Head of Product")} value={input} onChange={(e) => setInput(e.target.value)} />
            <small>{t("Only changes the question sections (likely questions, rebuttals, questions to ask). Leave empty before you have an interview.")}</small>
          </div>
        </details>
        <p className="sub">{t("The one-pager researches the company on the web, so it can take several minutes.")}</p>
        <Working busyKey={busyKey} />
        {r && (
          <>
            <div className="row">
              {r.demo && <span className="badge warn">{t("Sample output")}</span>}
              <span className="grow" />
              <button type="button" className="btn s" onClick={() => window.open(URL.createObjectURL(new Blob([r.html], { type: "text/html" })), "_blank")}>{t("Open full page")}</button>
              <button type="button" className="btn s" onClick={() => saveBlob(new Blob([r.html], { type: "text/html" }), `One-pager - ${company}.html`)}>{t("Download .html")}</button>
            </div>
            <iframe className="onepager" title={t("One-pager")} sandbox="allow-scripts allow-popups" srcDoc={r.html} />
            {r.audit && <AuditBox r={r.audit} title="Review of what the report says about you" />}
            <p className="sub">{t("Company facts come from web sources and are outside what the auditors can verify. Check the numbered sources before quoting a figure.")}</p>
          </>
        )}
      </div>
    );
  }

  const r = record.actions.networking;
  if (!r) return start("Search for people", "Searches the web for people at this company and drafts two messages for each.");
  const setTarget = (target: string) =>
    run("target", async () => {
      const res = await send<{ record: AnalysisRecord }>("POST", "/api/run", { kind: "setTarget", lang, id: record.id, target });
      putRecord(res.record);
      toast(t("Saved. This person now fills the Network target column for this job in the tracker."));
    });
  return (
    <div className="plain">
      <div className="row"><span className="sub grow">{t("Found through public web search. Titles can be out of date, so open each profile before sending.")}</span>{retry(r.runs)}</div>
      <Working busyKey={busyKey} />
      {record.networkTarget && <p className="sub"><b>{t("Contact for this job")}</b>: {record.networkTarget}</p>}
      <PeopleList targets={r.output.targets} action={(p) => <Btn small busyKey="target" onClick={() => setTarget(`${p.name} · ${p.title}`)}>{t("Save to tracker as my contact for this job")}</Btn>} />
      <p className="sub">{r.output.note}</p>
      <AuditBox r={r} />
    </div>
  );
}
