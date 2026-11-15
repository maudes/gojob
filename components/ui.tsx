"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import type { AnalysisRecord, Audit, AuditResult, CoachData, Evidence, Gate, HealthRecord, Label, PanelScore, Profile, QuoteCheck, ScoutData, TrackerRow } from "@/lib/schemas";
import { ZH } from "./zh";

/* ---------- App state shared by the three screens ---------- */

export type Lang = "en" | "zh";
export type Config = { live: boolean; mainModel: string; reviewerModel: string; tests: { name: string; pass: boolean }[] };
export type AppState = { profile: Profile; health: HealthRecord | null; analyses: AnalysisRecord[]; tracker: TrackerRow[]; coach: CoachData; scout: ScoutData; config: Config };

export type App = {
  state: AppState;
  patch: (p: Partial<AppState>) => void;
  putRecord: (r: AnalysisRecord) => void;
  lang: Lang;
  t: (en: string) => string;
  toast: (msg: string) => void;
  /** Run a server call with a busy flag and error toast. Returns undefined on failure. */
  run: <T>(key: string, fn: () => Promise<T>) => Promise<T | undefined>;
  busy: string | null;
  go: (tab: "profile" | "scout" | "jd" | "tracker" | "coach") => void;
  /** A job link handed from the wish list to the Target JD screen. */
  jdLink: string;
  openJD: (url: string) => void;
};

export const AppCtx = createContext<App | null>(null);
export const useApp = () => useContext(AppCtx)!;
export const translate = (lang: Lang, en: string) => (lang === "zh" && ZH[en]) || en;

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data as T;
}
export const send = <T,>(method: string, path: string, body: unknown) =>
  api<T>(path, { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

/** Fetch a file and save it, so a server-side problem shows as a message instead of a broken page. */
export async function download(url: string, toast: (m: string) => void) {
  const res = await fetch(url);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    toast(data.error || "Download failed.");
    return;
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? "download";
  saveBlob(await res.blob(), name);
}
export function saveBlob(blob: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

export async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/* ---------- Small pieces ---------- */

export function Btn(props: { busyKey?: string; primary?: boolean; small?: boolean; disabled?: boolean; onClick: () => void; children: ReactNode }) {
  const { busy } = useApp();
  const mine = props.busyKey != null && busy === props.busyKey;
  return (
    <button
      type="button"
      className={`btn${props.primary ? " p" : ""}${props.small ? " s" : ""}`}
      disabled={props.disabled || busy != null}
      onClick={props.onClick}
    >
      {mine && <span className="spin" aria-hidden />}
      {props.children}
    </button>
  );
}

export function Working({ busyKey }: { busyKey: string }) {
  const { busy, t } = useApp();
  if (busy !== busyKey) return null;
  return <p className="note info">{t("The agents are working. This usually takes one to three minutes; keep this tab open.")}</p>;
}

export function Chips(props: { id: string; items: string[]; max: number; onChange: (items: string[]) => void }) {
  const { t } = useApp();
  const [value, setValue] = useState("");
  const add = () => {
    const v = value.trim();
    if (v && props.items.length < props.max && !props.items.includes(v)) props.onChange([...props.items, v]);
    setValue("");
  };
  return (
    <div className="chips">
      {props.items.map((it, i) => (
        <span className="chip" key={it}>
          {it}
          <button type="button" aria-label={`Remove ${it}`} onClick={() => props.onChange(props.items.filter((_, j) => j !== i))}>
            ×
          </button>
        </span>
      ))}
      {props.items.length >= props.max ? (
        <small className="sub">{t("Limit reached")}</small>
      ) : (
        <input
          id={props.id}
          type="text"
          value={value}
          placeholder={t("Type and press Enter")}
          onChange={(e) => setValue(e.target.value)}
          onBlur={add}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
      )}
    </div>
  );
}

const LABELS: Record<Label, [string, string]> = {
  confirmed: ["Confirmed", "good"],
  inference: ["Inference", "warn"],
  needs_confirmation: ["Needs confirmation", "bad"],
};
export function LabelBadge({ label }: { label: Label }) {
  const { t } = useApp();
  const [text, cls] = LABELS[label];
  return <span className={`badge ${cls}`}>{t(text)}</span>;
}

/** A verbatim source quote. Turns red when the code-level check could not find it in the source. */
export function Quote({ e, failed }: { e: Evidence; failed?: QuoteCheck["failed"] }) {
  const { t } = useApp();
  if (!e.quote.trim()) return <span className="sub">{t("No evidence in resume. Not added.")}</span>;
  const bad = failed?.some((f) => f.quote === e.quote);
  return (
    <span className={`q${bad ? " fail" : ""}`}>
      <i>{e.source === "jd" ? "JD" : e.source === "resume" ? t("Resume") : t("Profile")}</i>
      {e.quote}
      {bad && <span className="badge bad" style={{ marginLeft: 6 }}>{t("Not found word for word")}</span>}
    </span>
  );
}

export function Reviewers({ panel }: { panel: (PanelScore & { reviewer: string })[] }) {
  const { t } = useApp();
  return (
    <div className="revs">
      {panel.map((p) => (
        <div className="rev" key={p.reviewer}>
          <span>{p.reviewer}</span>
          <b className="n">{p.score}</b>
          <span className="sub">{p.verdict}</span>
          {(p.strengths.length > 0 || p.gaps.length > 0) && (
            <details>
              <summary>{t("Proof")}</summary>
              {p.strengths.map((s, i) => (
                <p key={`s${i}`} style={{ marginTop: 6 }}>
                  + {s.point} <Quote e={s.proof} />
                </p>
              ))}
              {p.gaps.map((s, i) => (
                <p key={`g${i}`} style={{ marginTop: 6 }}>
                  − {s.point} <Quote e={s.proof} />
                </p>
              ))}
            </details>
          )}
        </div>
      ))}
    </div>
  );
}

export function HealthGate({ gate }: { gate: Gate }) {
  const { t } = useApp();
  return (
    <div className="gate">
      <div className="big">{gate.average.toFixed(1)}</div>
      <div className="grow">
        <div className="light">
          <span className={`dot${gate.green ? " on" : ""}`} />
          {t(gate.green ? "Green light" : "Not green yet")}
        </div>
        <div className="sub">
          {t("Green needs average ≥ 80 and no reviewer below 70.")} avg {gate.average.toFixed(1)} · min {gate.min}
        </div>
      </div>
    </div>
  );
}

const CHECKS: [keyof Audit["checks"], string][] = [
  ["resumeQuotesVerbatim", "Resume quotes word for word"],
  ["jdQuotesVerbatim", "JD quotes word for word"],
  ["noInventedFacts", "No invented facts"],
  ["labelsCorrect", "Labels correct"],
  ["alignedWithProfile", "Matches profile"],
];

/** The fidelity gate: five auditors above 95, every box ticked, every quote found in its source. */
export function AuditBox({ r, title = "Fidelity review" }: { r: AuditResult; title?: string }) {
  const { t } = useApp();
  const issues = [...new Set(r.audits.flatMap((a) => a.issues))];
  return (
    <div className="audit">
      <div>
        {r.demo ? <span className="badge warn">{t("Sample output")}</span> : <span className={`badge ${r.approved ? "good" : "bad"}`}>{t(r.approved ? "Approved" : "Not approved")}</span>}{" "}
        <b>{t(title)}</b> · {r.audits.length} {t("auditors")}: {r.audits.map((a) => a.score).join(" · ")}{" "}
        <span className="sub">({t("needs all 5 above 95 and every box ticked")})</span>
      </div>
      <div className="sub">
        {CHECKS.map(([key, label]) => {
          const ok = r.audits.filter((a) => a.checks[key]).length;
          return (
            <span key={key} style={{ marginRight: 12 }}>
              {ok === r.audits.length ? "☑" : "☒"} {t(label)} {ok}/{r.audits.length}
            </span>
          );
        })}
        <span>
          {r.quoteCheck.verified}/{r.quoteCheck.total} {t("quotes found in source")}
        </span>
      </div>
      {!r.demo && !r.approved && <p className="note bad">{t("This result did not pass the fidelity review, even after one automatic repair. Check the flagged items below before relying on it, or retry.")}</p>}
      {issues.length > 0 && (
        <details open={!r.approved}>
          <summary>{t("Flagged by auditors")} ({issues.length})</summary>
          <ul>{issues.map((x) => <li key={x}>{x}</li>)}</ul>
        </details>
      )}
      {r.quoteCheck.failed.length > 0 && (
        <details open>
          <summary>{t("Quotes not found word for word")} ({r.quoteCheck.failed.length})</summary>
          <ul>{r.quoteCheck.failed.map((f, i) => <li key={i}>{f.source}: {f.quote}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

/**
 * Retry with the same inputs. After more than 5 retries it first asks whether
 * something is wrong and stores the feedback (eval rule 3).
 */
export function RetryButton(props: { runs: number; feature: string; busyKey: string; onRetry: () => void; label?: string }) {
  const { t, toast } = useApp();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const retries = Math.max(0, props.runs - 1);
  return (
    <>
      <Btn small busyKey={props.busyKey} onClick={() => (retries >= 5 ? setOpen(true) : props.onRetry())}>
        ↻ {t(props.label ?? "Retry")}
      </Btn>
      {open && (
        <div className="dlg">
          <div role="dialog" aria-label={t("Is something going wrong?")}>
            <h2>{t("Is something going wrong?")}</h2>
            <p>{t("You have retried this more than 5 times. Tell us what looks off so it can be fixed.")}</p>
            <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={t("What did you expect to see?")} />
            <div className="row">
              <button
                type="button"
                className="btn p"
                onClick={async () => {
                  if (text.trim()) {
                    await send("POST", "/api/feedback", { feature: props.feature, message: text }).catch(() => undefined);
                    toast(t("Feedback saved. Thank you."));
                  }
                  setText("");
                  setOpen(false);
                }}
              >
                {t("Send feedback")}
              </button>
              <button type="button" className="btn" onClick={() => { setOpen(false); props.onRetry(); }}>
                {t("Retry anyway")}
              </button>
              <button type="button" className="btn" onClick={() => setOpen(false)}>
                {t("Cancel")}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
