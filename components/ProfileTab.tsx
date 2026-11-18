"use client";

import { useRef, useState } from "react";
import type { HealthRecord, Profile } from "@/lib/schemas";
import { ResumeReview, type Accepted } from "./ResumeReview";
import { api, AuditBox, Btn, Chips, HealthGate, Quote, RetryButton, Reviewers, send, useApp, Working } from "./ui";

const MODES = [["remote", "Remote"], ["onsite", "On-site"], ["hybrid", "Hybrid"]] as const;
const newId = () => Math.random().toString(36).slice(2, 10);

/** What is still missing before the profile can be saved. */
function missing(p: Profile): string[] {
  const out: string[] = [];
  if (p.resumeText.trim().length < 200) out.push("Resume");
  if (!p.linkedinUrl.trim() && !p.websiteUrl.trim()) out.push("LinkedIn or website link");
  if (p.roles.length < 1) out.push("Expected role");
  if (p.domains.length < 1) out.push("Domain");
  if (p.regions.length < 1) out.push("Region / country");
  if (p.workModes.length < 1) out.push("Type");
  const good = p.targetJDs.filter((j) => j.text.trim().length >= 300).length;
  if (good < 3 || good !== p.targetJDs.length) out.push("3 to 10 target JDs, each with its full text");
  return out;
}

export function ProfileTab() {
  const { state, patch, t, toast, run, lang } = useApp();
  const [draft, setDraft] = useState<Profile>(state.profile);
  const [uploaded, setUploaded] = useState(false);
  const [showText, setShowText] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const set = (p: Partial<Profile>) => setDraft((d) => ({ ...d, ...p }));
  const same = (p: Profile) => JSON.stringify({ ...p, savedAt: null, sheetUrl: "" });
  const dirty = same(draft) !== same(state.profile) || uploaded;
  const gaps = missing(draft);
  const health = state.health;
  const stale = health != null && health.profileSavedAt !== state.profile.savedAt;

  const upload = (file: File) =>
    run("upload", async () => {
      const form = new FormData();
      form.append("file", file);
      const r = await api<{ text: string; fileName: string; format: "docx" | "other" }>("/api/upload", { method: "POST", body: form });
      set({ resumeText: r.text, resumeFileName: r.fileName, resumeFormat: r.format });
      setUploaded(true);
      if (r.format !== "docx") toast(t("Read successfully. For a revised resume that keeps your exact layout, upload a .docx instead."));
    });

  const fetchLink = () =>
    run("resume-link", async () => {
      const r = await send<{ text: string; fileName: string; format: "docx" | "other" }>("POST", "/api/resume-link", { link: draft.resumeLink.trim() });
      set({ resumeText: r.text, resumeFileName: r.fileName, resumeFormat: r.format });
      setUploaded(true);
      toast(t(r.format === "docx" ? "Read from Google. Save the profile to use this version." : "Read the file, but it is not a Word file, so the revised resume layout will be rebuilt."));
    });

  const save = () =>
    run("save", async () => {
      const r = await send<{ profile: Profile }>("PUT", "/api/profile", { ...draft, sheetUrl: state.profile.sheetUrl, promoteUpload: uploaded });
      patch({ profile: r.profile });
      setDraft(r.profile);
      setUploaded(false);
      toast(t("Profile saved. All JD assessments now use this version."));
    });

  const check = () =>
    run("health", async () => {
      const r = await send<{ health: HealthRecord }>("POST", "/api/run", { kind: "health", lang });
      patch({ health: r.health });
    });

  const applyChanges = (accepted: Accepted[], rejected: string[]) =>
    run("apply-profile", async () => {
      const r = await send<{ profile: Profile; health: HealthRecord | null; missedInFile: string[] }>("POST", "/api/resume-apply", { scope: "profile", accepted, rejected });
      patch({ profile: r.profile, health: r.health });
      setDraft(r.profile);
      toast(r.missedInFile.length ? t("Saved. Some changes could not be placed in the original file; check the download.") : t("Saved to your resume. Run the health check again to see the new score."));
    });

  const roleHint = draft.roles.length === 2 ? t("The agent checks whether these two roles conflict when you run the health check.") : "";
  const out = health?.check.output;

  return (
    <div className="plain">
      <div className="card">
        <h2>{t("Set up your profile")}</h2>
        <div className="g2">
          <div className="f">
            <span>{t("Resume (upload or link)")}</span>
            <div className="row">
              {draft.resumeFileName && <span className="chip">{draft.resumeFileName}</span>}
              <input ref={fileRef} type="file" hidden accept=".docx,.pdf,.txt,.md" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
              <Btn small busyKey="upload" onClick={() => fileRef.current?.click()}>{t(draft.resumeFileName ? "Replace" : "Upload file")}</Btn>
              <button type="button" className="btn s" onClick={() => setShowText((v) => !v)}>{t(showText ? "Hide text" : "View or paste text")}</button>
            </div>
            <div className="row">
              <input className="grow" type="url" id="p-resume-link" aria-label={t("Resume link")} placeholder={t("Optional: link to your resume, e.g. a Google Doc")} value={draft.resumeLink} onChange={(e) => set({ resumeLink: e.target.value })} />
              <Btn small busyKey="resume-link" disabled={!draft.resumeLink.trim()} onClick={fetchLink}>{t("Fetch from link")}</Btn>
            </div>
            <small className="tip">{t("Best result: keep your resume in Google Docs and paste its link above, shared as \"Anyone with the link\" (Share → General access). The app downloads it as Word, so the revised resume keeps your exact fonts and layout. Fetch again whenever you edit the doc. Or upload a .docx (File → Download → Microsoft Word). A PDF also works, but its layout is rebuilt and will not match exactly.")}</small>
            <small>{t("The app can read your Google Doc but cannot edit it: it never signs in to Google. Download the revised resume and paste the changes into your doc.")}</small>
            <small>{t("Contact details are removed on upload and never shown or sent to an agent.")}</small>
            {state.profile.resumeUpdatedAt && <small>{t("Resume last updated")}: {state.profile.resumeUpdatedAt.slice(0, 10)}</small>}
            {showText && <textarea id="p-resume-text" aria-label={t("Resume text")} style={{ minHeight: 220 }} value={draft.resumeText} onChange={(e) => set({ resumeText: e.target.value, resumeFileName: uploaded ? draft.resumeFileName : "" })} />}
          </div>
          <div className="f">
            <label htmlFor="p-li">{t("LinkedIn profile link")}</label>
            <input type="url" id="p-li" placeholder="https://www.linkedin.com/in/…" value={draft.linkedinUrl} onChange={(e) => set({ linkedinUrl: e.target.value })} />
            <small>{t("LinkedIn blocks automatic reading, so you paste your About and Experience text once.")}</small>
            <textarea id="p-li-text" aria-label={t("LinkedIn text")} placeholder={t("Paste your LinkedIn About and Experience here (optional)")} value={draft.linkedinText} onChange={(e) => set({ linkedinText: e.target.value })} />
            <label htmlFor="p-web" style={{ marginTop: 6 }}>{t("Personal website / portfolio link")}</label>
            <input type="url" id="p-web" placeholder="https://your-site.com" value={draft.websiteUrl} onChange={(e) => set({ websiteUrl: e.target.value })} />
            <small>{state.profile.websiteText ? t("Scanned. The agents can read your site.") : t("Scanned automatically when you save.")}</small>
          </div>
          <div className="f">
            <label htmlFor="p-role">{t("Expected role")} <small>(max 2)</small></label>
            <Chips id="p-role" items={draft.roles} max={2} onChange={(roles) => set({ roles })} />
            {out && !stale ? (
              <small><span className={`badge ${out.roleConflict.conflict ? "bad" : "good"}`}>{t(out.roleConflict.conflict ? "Conflict" : "Same job family")}</span> {out.roleConflict.reason}</small>
            ) : (
              roleHint && <small>{roleHint}</small>
            )}
          </div>
          <div className="f">
            <label htmlFor="p-domain">{t("Domain")} <small>(max 3)</small></label>
            <Chips id="p-domain" items={draft.domains} max={3} onChange={(domains) => set({ domains })} />
          </div>
          <div className="f">
            <label htmlFor="p-region">{t("Region / country")} <small>{t("(multiple allowed)")}</small></label>
            <Chips id="p-region" items={draft.regions} max={20} onChange={(regions) => set({ regions })} />
          </div>
          <div className="f">
            <label htmlFor="p-visa">{t("Sponsorship required?")}</label>
            <select id="p-visa" value={draft.sponsorship ? "y" : "n"} onChange={(e) => set({ sponsorship: e.target.value === "y" })}>
              <option value="y">{t("Yes")}</option>
              <option value="n">{t("No")}</option>
            </select>
          </div>
          {draft.sponsorship && (
            <div className="f">
              <label htmlFor="p-auth">{t("Countries where you can already work")} <small>{t("(no visa needed there)")}</small></label>
              <Chips id="p-auth" items={draft.workAuthorized} max={10} onChange={(workAuthorized) => set({ workAuthorized })} />
            </div>
          )}
          <div className="f">
            <span>{t("Type")}</span>
            <div className="row">
              {MODES.map(([id, label]) => (
                <label className="check" key={id}>
                  <input type="checkbox" id={`p-${id}`} checked={draft.workModes.includes(id)} onChange={(e) => set({ workModes: e.target.checked ? [...draft.workModes, id] : draft.workModes.filter((m) => m !== id) })} />
                  {label}
                </label>
              ))}
            </div>
          </div>
          <div className="f">
            <span>{t("Employment")}</span>
            <div><span className="badge">{t("Full time only (fixed)")}</span></div>
          </div>
        </div>

        <div className="f">
          <span>{t("Target JDs for keyword collection")} <small>(3 to 10) · {draft.targetJDs.length} {t("added")}</small></span>
          {draft.targetJDs.map((jd, i) => (
            <details key={jd.id} className="rw" open={jd.text.trim().length < 300}>
              <summary style={{ cursor: "pointer" }}>{jd.title.trim() || `${t("Target JD")} ${i + 1}`} {jd.text.trim().length < 300 && <span className="badge warn">{t("Paste the full text")}</span>}</summary>
              <div className="plain" style={{ marginTop: 8 }}>
                <input type="text" id={`jd-title-${jd.id}`} aria-label={t("Company and job title")} placeholder={t("Company and job title")} value={jd.title} onChange={(e) => set({ targetJDs: draft.targetJDs.map((x) => (x.id === jd.id ? { ...x, title: e.target.value } : x)) })} />
                <textarea id={`jd-text-${jd.id}`} aria-label={t("Job description")} placeholder={t("Paste the full job description")} style={{ minHeight: 140 }} value={jd.text} onChange={(e) => set({ targetJDs: draft.targetJDs.map((x) => (x.id === jd.id ? { ...x, text: e.target.value } : x)) })} />
                <div><button type="button" className="btn s" onClick={() => set({ targetJDs: draft.targetJDs.filter((x) => x.id !== jd.id) })}>{t("Remove")}</button></div>
              </div>
            </details>
          ))}
          {draft.targetJDs.length < 10 && (
            <div><button type="button" className="btn s" onClick={() => set({ targetJDs: [...draft.targetJDs, { id: newId(), title: "", text: "" }] })}>{t("+ Add JD")}</button></div>
          )}
        </div>

        <div className="row">
          <Btn primary busyKey="save" disabled={gaps.length > 0 || !dirty} onClick={save}>{t("Save profile")}</Btn>
          <Btn busyKey="health" disabled={dirty || !state.profile.savedAt} onClick={check}>{t("Run health check")}</Btn>
          <span className="sub">
            {gaps.length > 0 ? `${t("Still needed")}: ${gaps.map(t).join(" · ")}` : dirty ? t("Unsaved changes. Assessments use the last saved version.") : t("You can save and continue whatever the score is.")}
          </span>
        </div>
        <Working busyKey="health" />
      </div>

      {health && out && (
        <div className="card">
          <div className="row">
            <h2 className="grow">{t("Health check: positioning")}</h2>
            <RetryButton runs={health.check.runs} feature="health" busyKey="health" onRetry={check} />
          </div>
          {stale && <p className="note">{t("Your profile changed after this check. Run it again for an up-to-date result.")}</p>}
          <HealthGate gate={health.gate} />
          <Reviewers panel={health.panel} />
          {health.panelAudit && <AuditBox r={health.panelAudit} title="Review of the three scores" />}
          <div className="it">
            <h3>{t("Is the positioning close to the truth and to the target?")}</h3>
            <p>{out.positioning.statement}</p>
            <p className="sub"><b>{t("Truth")}</b>: {out.positioning.closeToTruth}</p>
            <p className="sub"><b>{t("Target")}</b>: {out.positioning.closeToTarget}</p>
          </div>
          <div className="tw">
            <table>
              <thead><tr><th>{t("Keyword")}</th><th>{t("In JDs")}</th><th>{t("Status")}</th><th>{t("Proof from resume")}</th></tr></thead>
              <tbody>
                {out.keywords.map((k) => (
                  <tr key={k.keyword}>
                    <td>{k.keyword}</td>
                    <td className="n">{k.jdCount} / {state.profile.targetJDs.length}</td>
                    <td><span className={`badge ${k.status === "covered" ? "good" : k.status === "terminology_gap" ? "warn" : "bad"}`}>{t(k.status === "covered" ? "Covered" : k.status === "terminology_gap" ? "Wording gap" : "Needs confirmation")}</span></td>
                    <td><Quote e={k.proof} failed={health.check.quoteCheck.failed} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="plain">
            <h3>{t("Suggested resume, full document")}</h3>
            <p className="sub">{t("Reviewed like a contract: deletions and additions are both marked. Accept, reject or edit each one, then download in your original file's format.")}</p>
            <ResumeReview text={state.profile.resumeText} changes={stale ? out.changes.filter((c) => state.profile.resumeText.includes(c.find)) : out.changes} exportQuery="scope=profile" busyKey="apply-profile" onApply={applyChanges} />
          </div>
          <AuditBox r={health.check} title="Review of the assessment and resume changes" />
        </div>
      )}
    </div>
  );
}
