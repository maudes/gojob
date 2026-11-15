"use client";

import { useState } from "react";
import type { Profile, TrackerRow } from "@/lib/schemas";
import { TRACKER_COLUMNS, trackerTSV } from "@/lib/text";
import { api, Btn, copy, send, useApp } from "./ui";

const HEAD: Record<(typeof TRACKER_COLUMNS)[number], string> = {
  company: "Company",
  position: "Job position",
  location: "Location",
  jobLink: "Job link",
  oneLine: "One line description",
  matchingScore: "Matching score",
  applyDate: "Apply date",
  networkTarget: "Network Target",
  status: "Status",
  notes: "Notes",
};
const STATUS: TrackerRow["status"][] = ["Apply", "HR", "Interview", "Reject"];

export function TrackerTab() {
  const { state, patch, t, toast, run } = useApp();
  const [sheet, setSheet] = useState(state.profile.sheetUrl);

  const saveSheet = () =>
    run("sheet", async () => {
      const r = await send<{ profile: Profile }>("PUT", "/api/profile", { ...state.profile, sheetUrl: sheet.trim() });
      patch({ profile: r.profile });
      toast(t("Sheet link saved."));
    });

  // Edit locally on every keystroke, write to disk when the field loses focus.
  const edit = (id: string, change: Partial<TrackerRow>) => patch({ tracker: state.tracker.map((r) => (r.id === id ? { ...r, ...change } : r)) });
  const commit = (id: string, change: Partial<TrackerRow>) => {
    edit(id, change);
    send("PATCH", "/api/tracker", { id, ...change }).catch(() => toast(t("Could not save the change.")));
  };
  const add = () => run("row", async () => patch({ tracker: (await send<{ tracker: TrackerRow[] }>("POST", "/api/tracker", {})).tracker }));
  const remove = (id: string) => run("row", async () => patch({ tracker: (await api<{ tracker: TrackerRow[] }>(`/api/tracker?id=${id}`, { method: "DELETE" })).tracker }));

  const copyRow = async (row: TrackerRow) => {
    const ok = await copy(trackerTSV(row));
    if (ok && state.profile.sheetUrl) window.open(state.profile.sheetUrl, "_blank", "noopener");
    toast(t(ok ? "Row copied. Paste it into the first empty row of your sheet." : "Copying was blocked by the browser."));
  };

  return (
    <div className="card tracker">
      <h2>{t("Application tracker")}</h2>
      <div className="row">
        <div className="f grow">
          <label htmlFor="sheet">{t("Your Google Sheet")}</label>
          <input type="url" id="sheet" placeholder="https://docs.google.com/spreadsheets/d/…" value={sheet} onChange={(e) => setSheet(e.target.value)} />
        </div>
        <Btn busyKey="sheet" disabled={sheet.trim() === state.profile.sheetUrl} onClick={saveSheet}>{t("Save link")}</Btn>
      </div>
      <p className="sub">{t("Logging an application adds the row here, copies it in your sheet's column order and opens the sheet in a new tab to paste.")}</p>
      <div className="row">
        <Btn small busyKey="row" onClick={add}>{t("+ Add row")}</Btn>
        <button type="button" className="btn s" onClick={async () => toast(t((await copy(TRACKER_COLUMNS.map((c) => HEAD[c]).join("\t"))) ? "Header row copied. Paste it into row 1 of a new sheet." : "Copying was blocked by the browser."))}>{t("Copy header row")}</button>
      </div>
      {state.tracker.length === 0 ? (
        <p className="sub">{t("No applications yet. Use Log application on a JD, or add a row.")}</p>
      ) : (
        <div className="tw">
          <table>
            <thead><tr>{TRACKER_COLUMNS.map((c) => <th key={c}>{t(HEAD[c])}</th>)}<th /></tr></thead>
            <tbody>
              {state.tracker.map((row) => (
                <tr key={row.id}>
                  {TRACKER_COLUMNS.map((c) => (
                    <td key={c}>
                      {c === "status" ? (
                        <select id={`${c}-${row.id}`} aria-label={t(HEAD[c])} value={row.status} onChange={(e) => commit(row.id, { status: e.target.value as TrackerRow["status"] })}>
                          {STATUS.map((s) => <option key={s}>{s}</option>)}
                        </select>
                      ) : (
                        <input type="text" id={`${c}-${row.id}`} aria-label={t(HEAD[c])} value={row[c]} onChange={(e) => edit(row.id, { [c]: e.target.value })} onBlur={(e) => commit(row.id, { [c]: e.target.value })} />
                      )}
                    </td>
                  ))}
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button type="button" className="btn s" onClick={() => copyRow(row)}>{t("Copy row")}</button>{" "}
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
