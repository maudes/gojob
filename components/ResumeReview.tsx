"use client";

import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import type { ResumeChange } from "@/lib/schemas";
import { diffOps } from "@/lib/text";
import { Btn, copy, download, LabelBadge, useApp } from "./ui";

type Decision = { state: "pending" | "accepted" | "rejected" | "editing"; replace: string };
export type Accepted = { find: string; replace: string };

const lineClass = (line: string, index: number) => {
  if (!line.trim()) return "gap";
  if (index === 0) return "name";
  if (/^[A-Z][A-Z &/]{2,40}$/.test(line.trim())) return "sec";
  if (/^[•·▪●○◦*-]\s/.test(line.trim())) return "li";
  return "p";
};

/**
 * The whole resume with suggested edits shown like tracked changes in a contract:
 * removed text struck through, added text underlined, each one accepted, rejected or edited.
 */
export function ResumeReview(props: {
  text: string;
  changes: ResumeChange[];
  exportQuery: string;
  busyKey: string;
  onApply: (accepted: Accepted[], rejected: string[]) => void;
}) {
  const { t, toast } = useApp();
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  useEffect(() => {
    setDecisions((prev) => Object.fromEntries(props.changes.map((c) => [c.find, prev[c.find] ?? { state: "pending", replace: c.replace }])));
  }, [props.changes]);

  const set = (find: string, d: Partial<Decision>) => setDecisions((prev) => ({ ...prev, [find]: { ...prev[find], ...d } }));
  const of = (c: ResumeChange): Decision => decisions[c.find] ?? { state: "pending", replace: c.replace };
  const all = (state: "accepted" | "rejected") =>
    setDecisions((prev) => Object.fromEntries(Object.entries(prev).map(([k, d]) => [k, d.state === "pending" ? { ...d, state } : d])));

  const lines = useMemo(() => props.text.split("\n"), [props.text]);
  // Place each change on the first line that contains its text.
  const placed = useMemo(() => {
    const byLine = new Map<number, ResumeChange[]>();
    const loose: ResumeChange[] = [];
    for (const c of props.changes) {
      const at = lines.findIndex((l) => l.includes(c.find));
      if (at < 0) loose.push(c);
      else byLine.set(at, [...(byLine.get(at) ?? []), c]);
    }
    return { byLine, loose };
  }, [lines, props.changes]);

  const pending = props.changes.filter((c) => of(c).state === "pending" || of(c).state === "editing").length;
  const accepted = props.changes.filter((c) => of(c).state === "accepted");
  const rejected = props.changes.filter((c) => of(c).state === "rejected");

  /** The paragraph as it would read with the chosen changes applied, ready to paste over the old one. */
  const paragraph = (i: number, include: (c: ResumeChange) => boolean): string => {
    const line = lines[i];
    const here = (placed.byLine.get(i) ?? []).slice().sort((a, b) => line.indexOf(a.find) - line.indexOf(b.find));
    let out = "";
    let cursor = 0;
    for (const c of here) {
      const at = line.indexOf(c.find, cursor);
      if (at < 0) continue;
      out += line.slice(cursor, at) + (include(c) ? of(c).replace : c.find);
      cursor = at + c.find.length;
    }
    return (out + line.slice(cursor)).replace(/^\s*[•·▪●○◦*-]\s+/, "").trim();
  };
  const lineOf = (c: ResumeChange) => lines.findIndex((l) => l.includes(c.find));
  const doCopy = async (text: string) =>
    toast(t((await copy(text)) ? "Copied. In your Google Doc, select the old paragraph and paste over it." : "Copying was blocked by the browser."));
  const copyBtn = (c: ResumeChange) => (
    <button type="button" className="cb" aria-label={t("Copy new paragraph")} title={t("Copy new paragraph")} onClick={() => doCopy(lineOf(c) >= 0 ? paragraph(lineOf(c), (x) => x === c || of(x).state === "accepted") : of(c).replace)}>
      {t("Copy")}
    </button>
  );

  const renderChange = (c: ResumeChange): ReactNode => {
    const d = of(c);
    const undo = (
      <button type="button" className="cb" aria-label={t("Undo")} onClick={() => set(c.find, { state: "pending" })}>
        ↺
      </button>
    );
    if (d.state === "accepted") return <><span className="ok">{d.replace}</span>{copyBtn(c)}{undo}</>;
    if (d.state === "rejected") return <>{c.find}{undo}</>;
    return (
      <>
        {diffOps(c.find, d.replace).map((op, i) =>
          op.type === "same" ? <Fragment key={i}>{op.text}</Fragment> : op.type === "del" ? <del key={i}>{op.text}</del> : <ins key={i}>{op.text}</ins>,
        )}
        <button type="button" className="cb" aria-label={t("Accept")} title={t("Accept")} onClick={() => set(c.find, { state: "accepted" })}>✓</button>
        <button type="button" className="cb" aria-label={t("Reject")} title={t("Reject")} onClick={() => set(c.find, { state: "rejected" })}>✕</button>
        <button type="button" className="cb" aria-label={t("Edit")} title={t("Edit")} onClick={() => set(c.find, { state: "editing" })}>✎</button>
        {copyBtn(c)}
      </>
    );
  };

  const renderNotes = (c: ResumeChange): ReactNode => {
    const d = of(c);
    if (d.state === "editing")
      return (
        <div className="why editbox" key={`e${c.find}`}>
          <textarea aria-label={t("Edit")} value={d.replace} onChange={(e) => set(c.find, { replace: e.target.value })} />
          <div className="row">
            <button type="button" className="btn s p" onClick={() => set(c.find, { state: "accepted" })}>{t("Use my wording")}</button>
            <button type="button" className="btn s" onClick={() => set(c.find, { state: "pending", replace: c.replace })}>{t("Cancel")}</button>
          </div>
        </div>
      );
    if (d.state !== "pending") return null;
    return (
      <div className="why" key={`w${c.find}`}>
        <LabelBadge label={c.label} /> {c.reason}
      </div>
    );
  };

  const renderLine = (line: string, i: number): ReactNode => {
    const here = (placed.byLine.get(i) ?? []).slice().sort((a, b) => line.indexOf(a.find) - line.indexOf(b.find));
    const parts: ReactNode[] = [];
    let cursor = 0;
    for (const c of here) {
      const at = line.indexOf(c.find, cursor);
      if (at < 0) continue; // overlaps an earlier change on this line
      parts.push(<Fragment key={`t${at}`}>{line.slice(cursor, at)}</Fragment>, <Fragment key={`c${at}`}>{renderChange(c)}</Fragment>);
      cursor = at + c.find.length;
    }
    parts.push(<Fragment key="end">{line.slice(cursor)}</Fragment>);
    return (
      <Fragment key={i}>
        <div className={`ln ${lineClass(line, i)}`}>{parts}</div>
        {here.map(renderNotes)}
      </Fragment>
    );
  };

  return (
    <div className="plain">
      <div className="row">
        <b>{pending} {t("changes to review")}</b>
        <span className="lg"><del>{t("removed")}</del> <ins>{t("added")}</ins></span>
        <span className="grow" />
        {pending > 0 && <button type="button" className="btn s" onClick={() => all("accepted")}>{t("Accept all")}</button>}
        {pending > 0 && <button type="button" className="btn s" onClick={() => all("rejected")}>{t("Reject all")}</button>}
        <button type="button" className="btn s" onClick={() => download(`/api/export?${props.exportQuery}&format=docx`, toast)}>{t("Download .docx")}</button>
        <button type="button" className="btn s" onClick={() => download(`/api/export?${props.exportQuery}&format=pdf`, toast)}>{t("Download PDF")}</button>
      </div>
      {props.changes.length > 0 && <p className="sub">{t("Copy a changed paragraph and paste it over the old one in your Google Doc. Bullets and skills lines copy without the bullet sign.")}</p>}
      <div className="paper">{lines.map(renderLine)}</div>
      {placed.loose.length > 0 && (
        <div className="plain">
          <p className="note">{t("These suggestions could not be placed on a single line of the resume. Review them here.")}</p>
          {placed.loose.map((c) => (
            <div className="it" key={c.find}>
              <div>{renderChange(c)}</div>
              {renderNotes(c)}
            </div>
          ))}
        </div>
      )}
      {(accepted.length > 0 || rejected.length > 0) && (
        <div className="row">
          <Btn primary busyKey={props.busyKey} onClick={() => props.onApply(accepted.map((c) => ({ find: c.find, replace: of(c).replace })), rejected.map((c) => c.find))}>
            {t("Save decisions to the resume")} ({accepted.length} {t("accepted")}, {rejected.length} {t("rejected")})
          </Btn>
          <span className="sub">{t("Downloads include only the changes you have saved.")}</span>
        </div>
      )}
    </div>
  );
}
