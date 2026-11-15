"use client";

import { useEffect, useRef, useState } from "react";
import type { CoachCategory, CoachData, CoachItem, CoachMode, CoachPrompt } from "@/lib/schemas";
import { api, AuditBox, Btn, download, saveBlob, send, useApp, Working } from "./ui";

const CATS: [CoachCategory | "auto", string][] = [
  ["auto", "Auto (balanced)"],
  ["self_intro", "Self-intro"],
  ["behavioral", "Behavioural"],
  ["general", "General"],
  ["story", "My stories"],
  ["jd", "JD-related"],
  ["product", "Product"],
];
const CAT_NAME = Object.fromEntries(CATS) as Record<string, string>;
const MODES: [CoachMode, string, number, [number, number]][] = [
  ["30s", "30 seconds", 30, [55, 90]],
  ["2min", "2 minutes", 120, [230, 320]],
];
const WEAK: Record<string, string> = {
  too_long: "Too long", too_short: "Too short", unclear_situation: "Situation unclear", no_challenge: "No challenge stated",
  no_decision: "No decision stated", no_impact: "No impact stated", weak_relevance: "Weak link to the role", grammar: "Grammar", vague_wording: "Vague wording",
};
const ELEMENT: Record<string, string> = { situation: "Situation", challenge: "Challenge", decision: "Decision", impact: "Impact", relevance: "Role relevance" };
const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;

type Recognition = { start: () => void; stop: () => void; onresult: ((e: { resultIndex: number; results: { isFinal: boolean; 0: { transcript: string } }[] }) => void) | null; onend: (() => void) | null; continuous: boolean; interimResults: boolean; lang: string };

export function CoachTab() {
  const { state, patch, t, toast, run, lang } = useApp();
  const coach = state.coach;
  const setCoach = (c: CoachData) => patch({ coach: c });

  const [jdIds, setJdIds] = useState<string[]>([]);
  const [category, setCategory] = useState<CoachCategory | "auto">("auto");
  const [mode, setMode] = useState<CoachMode>("30s");
  const [prompt, setPrompt] = useState<CoachPrompt | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<CoachItem | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [running, setRunning] = useState(false);
  const [listening, setListening] = useState(false);
  const [bankMode, setBankMode] = useState<"file" | "link" | "paste">("file");
  const [bankInput, setBankInput] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const rec = useRef<Recognition | null>(null);

  const [, modeLabel, limit, [lo, hi]] = MODES.find((m) => m[0] === mode)!;

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [running]);

  const stopAll = () => {
    setRunning(false);
    rec.current?.stop();
    setListening(false);
  };

  /** Dictation through the browser, when it offers speech recognition (Chrome, Edge, Safari). */
  const dictate = () => {
    if (listening) return stopAll();
    const Ctor = (window as unknown as Record<string, new () => Recognition>).SpeechRecognition ?? (window as unknown as Record<string, new () => Recognition>).webkitSpeechRecognition;
    if (!Ctor) return toast(t("This browser has no dictation. Type your answer, or use Chrome."));
    const r = new Ctor();
    r.continuous = true;
    r.interimResults = false;
    r.lang = "en-US";
    r.onresult = (e) => {
      let text = "";
      for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) text += e.results[i][0].transcript;
      if (text) setAnswer((a) => `${a} ${text}`.trim());
    };
    r.onend = () => setListening(false);
    rec.current = r;
    r.start();
    setListening(true);
    setRunning(true);
  };

  const loadBank = (init: RequestInit) =>
    run("bank", async () => {
      const r = await api<{ coach: CoachData }>("/api/coach/bank", init);
      setCoach(r.coach);
      setBankInput("");
      toast(t("Story bank loaded."));
    });
  const json = (body: unknown): RequestInit => ({ method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

  const next = (cat = category) =>
    run("coach-next", async () => {
      stopAll();
      const r = await send<{ prompt: CoachPrompt }>("POST", "/api/coach", { kind: "next", lang, category: cat, jdIds });
      setPrompt(r.prompt);
      setAnswer("");
      setResult(null);
      setSeconds(0);
    });

  const feedback = () =>
    run("coach-feedback", async () => {
      stopAll();
      const r = await send<{ coach: CoachData; item: CoachItem }>("POST", "/api/coach", { kind: "feedback", lang, prompt, mode, answer, seconds, jdIds });
      setCoach(r.coach);
      setResult(r.item);
    });

  const again = (m: CoachMode) => {
    setMode(m);
    setAnswer("");
    setResult(null);
    setSeconds(0);
  };

  const report = () => run("coach-report", async () => setCoach((await send<{ coach: CoachData }>("POST", "/api/coach", { kind: "report", lang })).coach));
  const removeItem = (id: string) => run("coach-del", async () => setCoach((await api<{ coach: CoachData }>(`/api/coach?id=${id}`, { method: "DELETE" })).coach));

  const count = words(answer);
  const fb = result?.feedback;
  const rep = coach.report;
  const reportMd = rep
    ? [`# Weekly interview practice report ${rep.at.slice(0, 10)}`, `Questions practised: ${rep.total}`, ...Object.entries(rep.counts).map(([k, v]) => `- ${CAT_NAME[k] ?? k}: ${v}`),
        "## Strengths", ...rep.output.strengths.map((x) => `- ${x}`), "## Weak areas", ...rep.output.weakAreas.map((x) => `- ${x}`), "## Prepare next", ...rep.output.prepare.map((x) => `- ${x}`),
        "## Delivery", `- 30 seconds: ${rep.output.delivery30}`, `- 2 minutes: ${rep.output.delivery2min}`].join("\n")
    : "";

  return (
    <div className="plain">
      {!state.profile.savedAt && <p className="note">{t("Save your profile first. The coach uses your resume.")}</p>}

      <div className="card">
        <h2>{t("Practice material")}</h2>
        <div className="g2">
          <div className="f">
            <span>{t("Story bank")}</span>
            {coach.storyBank.text ? (
              <small><span className="badge good">{t("Loaded")}</span> {coach.storyBank.name} · {coach.storyBank.text.length.toLocaleString()} {t("characters")} · {coach.storyBank.updatedAt?.slice(0, 10)}</small>
            ) : (
              <small>{t("Your own stories make the questions and feedback specific to you. Without one the coach uses your resume only.")}</small>
            )}
            <small className="tip">{t("Google Drive: the link only works when the file is shared as \"Anyone with the link\" (Share → General access). Private files cannot be read because the app never signs in to Google; download those and upload the file instead. Google Sheets are read as the first tab unless the link points to another tab.")}</small>
            <div className="pills sm" role="tablist">
              {([["file", "Upload file"], ["link", "Google Drive link"], ["paste", "Paste text"]] as const).map(([id, label]) => (
                <button key={id} role="tab" aria-selected={bankMode === id} onClick={() => { setBankMode(id); setBankInput(""); }}>{t(label)}</button>
              ))}
            </div>
            {bankMode === "file" && (
              <div className="row">
                <input ref={fileRef} type="file" hidden accept=".docx,.pdf,.txt,.md,.csv" onChange={(e) => { const f = e.target.files?.[0]; if (f) { const form = new FormData(); form.append("file", f); loadBank({ method: "POST", body: form }); } e.target.value = ""; }} />
                <Btn small busyKey="bank" onClick={() => fileRef.current?.click()}>{t("Choose file")}</Btn>
                <small>.docx · .pdf · .txt · .md · .csv</small>
              </div>
            )}
            {bankMode === "link" && (
              <>
                <input type="url" id="bank-link" aria-label={t("Google Drive link")} placeholder="https://docs.google.com/…" value={bankInput} onChange={(e) => setBankInput(e.target.value)} />
                <div className="row"><Btn small busyKey="bank" disabled={!bankInput.trim()} onClick={() => loadBank(json({ link: bankInput.trim() }))}>{t("Read link")}</Btn></div>
              </>
            )}
            {bankMode === "paste" && (
              <>
                <textarea id="bank-text" aria-label={t("Paste text")} style={{ minHeight: 120 }} value={bankInput} onChange={(e) => setBankInput(e.target.value)} />
                <div className="row"><Btn small busyKey="bank" disabled={bankInput.trim().length < 80} onClick={() => loadBank(json({ text: bankInput }))}>{t("Save stories")}</Btn></div>
              </>
            )}
          </div>
          <div className="f">
            <span>{t("Jobs to practise for")}</span>
            {state.analyses.length === 0 ? (
              <small>{t("No analysed jobs yet. Analyse a JD in step 3 to practise for it.")}</small>
            ) : (
              state.analyses.map((a) => {
                const n = a.actions.interview?.output.questions.length ?? 0;
                return (
                  <label className="check" key={a.id}>
                    <input type="checkbox" id={`coach-jd-${a.id}`} checked={jdIds.includes(a.id)} onChange={(e) => setJdIds(e.target.checked ? [...jdIds, a.id] : jdIds.filter((x) => x !== a.id))} />
                    <span>{a.analysis.output.meta.company || t("Untitled")} · {a.analysis.output.meta.title} <small>{n ? `${n} ${t("prepared questions from step 3")}` : t("no prepared questions yet; the coach writes them from the JD")}</small></span>
                  </label>
                );
              })
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="row">
          <h2 className="grow">{t("Practice")}</h2>
          <div className="pills sm" role="tablist">
            {MODES.map(([id, label]) => <button key={id} role="tab" aria-selected={mode === id} onClick={() => setMode(id)}>{t(label)}</button>)}
          </div>
        </div>
        <div className="pills sm" role="tablist" style={{ justifySelf: "start" }}>
          {CATS.map(([id, label]) => <button key={id} role="tab" aria-selected={category === id} onClick={() => setCategory(id)}>{t(label)}</button>)}
        </div>
        <div className="row">
          <Btn primary={!prompt} busyKey="coach-next" disabled={!state.profile.savedAt} onClick={() => next()}>{t(prompt ? "Next question" : "Start")}</Btn>
          <span className="sub">{t("One question at a time. Auto balances the categories and brings back what scored low.")}</span>
        </div>

        {prompt && (
          <div className="plain">
            <div className="qcard" style={{ padding: 16, display: "grid", gap: 8 }}>
              <div className="row">
                <span className="badge">{t(CAT_NAME[prompt.category])}</span>
                {prompt.source && <span className="sub">{prompt.source}</span>}
                {prompt.demo && <span className="badge warn">{t("Sample output")}</span>}
              </div>
              <p className="qq" style={{ fontSize: 18, fontWeight: 600, lineHeight: 1.4 }}>{prompt.question}</p>
              {prompt.audit ? (
                <span className="sub">
                  <span className={`badge ${prompt.audit.demo ? "warn" : prompt.audit.approved ? "good" : "bad"}`}>{t(prompt.audit.demo ? "Sample output" : prompt.audit.approved ? "Approved" : "Not approved")}</span>{" "}
                  {prompt.audit.audits.length} {t("auditors")}: {prompt.audit.audits.map((a) => a.score).join(" · ")}
                </span>
              ) : (
                <span className="sub">{t("Prepared and reviewed in step 3.")}</span>
              )}
              {(prompt.storyHint || prompt.why) && (
                <details className="sub">
                  <summary>{t("Hint")}</summary>
                  {prompt.storyHint && <p>{prompt.storyHint}</p>}
                  {prompt.why && <p>{prompt.why}</p>}
                </details>
              )}
            </div>

            {!result && (
              <>
                <div className="row">
                  <button type="button" className="btn" onClick={() => (running ? stopAll() : setRunning(true))}>{t(running ? "Stop timer" : "Start timer")}</button>
                  <button type="button" className="btn" onClick={dictate}>{t(listening ? "Stop dictation" : "Dictate answer")}</button>
                  <b style={{ fontVariantNumeric: "tabular-nums", color: seconds > limit ? "var(--bad)" : "inherit" }}>{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")} / {Math.floor(limit / 60)}:{String(limit % 60).padStart(2, "0")}</b>
                  <span className="sub">{t(modeLabel)}: {lo}–{hi} {t("words")}{mode === "30s" ? ` · ${t("about 5 sentences")}` : ""}</span>
                </div>
                <textarea id="coach-answer" aria-label={t("Your answer")} style={{ minHeight: mode === "30s" ? 120 : 220 }} placeholder={t("Speak with dictation or type your answer in English.")} value={answer} onChange={(e) => setAnswer(e.target.value)} />
                <div className="row">
                  <Btn primary busyKey="coach-feedback" disabled={count < 8} onClick={feedback}>{t("Get feedback")}</Btn>
                  <span className={`sub${count > hi ? " badge bad" : ""}`}>{count} {t("words")}</span>
                </div>
                <p className="sub">{t("Feedback is written by the coach, then checked by five auditors, so it takes a little longer.")}</p>
                <Working busyKey="coach-feedback" />
              </>
            )}

            {result && fb && (
              <div className="plain">
                <div className="gate">
                  <div className="big">{fb.score}</div>
                  <div className="grow">
                    <p><b>{fb.headline}</b></p>
                    <p className="sub">{fb.delivery}</p>
                    <div className="row" style={{ marginTop: 4 }}>{fb.weaknesses.map((w) => <span key={w} className="badge bad">{t(WEAK[w] ?? w)}</span>)}</div>
                  </div>
                </div>
                <div className="revs">
                  {fb.content.map((c) => (
                    <div className="rev" key={c.element}>
                      <span><span className={`badge ${c.present ? "good" : "bad"}`}>{c.present ? "✓" : "✕"}</span> <b>{t(ELEMENT[c.element])}</b></span>
                      <span className="sub">{c.note}</span>
                    </div>
                  ))}
                </div>
                {fb.english.length > 0 && (
                  <div className="it">
                    <h3>{t("English")}</h3>
                    {fb.english.map((e, i) => <p key={i}><del>{e.original}</del> <ins>{e.better}</ins> <span className="sub">{e.why}</span></p>)}
                  </div>
                )}
                {fb.tighter && (
                  <div className="it">
                    <h3>{t("Tighter version, in your own facts")}</h3>
                    <p className="rw msg">{fb.tighter}</p>
                    <p className="sub">{words(fb.tighter)} {t("words")}</p>
                  </div>
                )}
                {fb.confirm.length > 0 && (
                  <div className="it">
                    <h3>{t("Confirm before you use this answer")}</h3>
                    <ul>{fb.confirm.map((x) => <li key={x}>{x}</li>)}</ul>
                  </div>
                )}
                {result.feedbackAudit && <AuditBox r={result.feedbackAudit} title="Review of this feedback" />}
                <details className="sub"><summary>{t("Your answer")}</summary><p className="msg">{result.answer}</p></details>
                <div className="row">
                  <button type="button" className="btn" onClick={() => again(mode)}>{t("Try this question again")}</button>
                  <button type="button" className="btn" onClick={() => again(mode === "30s" ? "2min" : "30s")}>{t(mode === "30s" ? "Now the 2-minute version" : "Now the 30-second version")}</button>
                  <Btn primary busyKey="coach-next" onClick={() => next()}>{t("Next question")}</Btn>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <div className="row">
          <h2 className="grow">{t("History and weekly report")}</h2>
          <Btn small busyKey="coach-report" disabled={coach.items.length === 0} onClick={report}>{t("Write weekly report")}</Btn>
          <button type="button" className="btn s" disabled={coach.items.length === 0} onClick={() => download("/api/coach", toast)}>{t("Download practice log")}</button>
        </div>
        <Working busyKey="coach-report" />
        {rep && (
          <div className="it">
            <div className="row">
              <h3 className="grow">{t("Last 7 days")} · {rep.total} {t("questions")} <span className="sub">{rep.at.slice(0, 10)}</span></h3>
              {rep.demo && <span className="badge warn">{t("Sample output")}</span>}
              <button type="button" className="btn s" onClick={() => saveBlob(new Blob([reportMd], { type: "text/markdown" }), `weekly-report-${rep.at.slice(0, 10)}.md`)}>{t("Download report")}</button>
            </div>
            <div className="row">{Object.entries(rep.counts).map(([k, v]) => <span className="chip" key={k}>{t(CAT_NAME[k] ?? k)} {v}</span>)}</div>
            <div className="revs">
              {([["Recurring strengths", rep.output.strengths], ["Weak areas", rep.output.weakAreas], ["Prepare next", rep.output.prepare]] as const).map(([title, list]) => (
                <div className="rev" key={title}><b>{t(title)}</b>{list.length ? <ul>{list.map((x) => <li key={x}>{t(WEAK[x.replace(/ \(\d+x\)$/, "")] ?? x)}{/ \(\d+x\)$/.exec(x)?.[0] ?? ""}</li>)}</ul> : <span className="sub">–</span>}</div>
              ))}
            </div>
            {rep.output.delivery30 && <p className="sub"><b>{t("30 seconds")}</b>: {rep.output.delivery30}</p>}
            {rep.output.delivery2min && <p className="sub"><b>{t("2 minutes")}</b>: {rep.output.delivery2min}</p>}
            {rep.audit && <AuditBox r={rep.audit} title="Review of this report" />}
          </div>
        )}
        {coach.items.length === 0 ? (
          <p className="sub">{t("No practice yet. Your answers and scores will be listed here.")}</p>
        ) : (
          <div className="tw">
            <table>
              <thead><tr><th>{t("Date")}</th><th>{t("Category")}</th><th>{t("Question")}</th><th>{t("Length")}</th><th>{t("Score")}</th><th /></tr></thead>
              <tbody>
                {coach.items.map((i) => (
                  <tr key={i.id}>
                    <td style={{ whiteSpace: "nowrap" }}>{i.at.slice(0, 10)}</td>
                    <td>{t(CAT_NAME[i.category])}</td>
                    <td>{i.question}<br /><span className="sub">{i.feedback.headline}</span></td>
                    <td style={{ whiteSpace: "nowrap" }}>{t(i.mode === "30s" ? "30 seconds" : "2 minutes")}</td>
                    <td className="n">{i.feedback.score}</td>
                    <td><button type="button" className="btn s" aria-label={t("Delete")} onClick={() => removeItem(i.id)}>✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
