"use client";

import { useState } from "react";
import type { AnalysisRecord, CoachData, ScoutData, TrackerRow } from "@/lib/schemas";
import { api, useApp } from "./ui";

type Usage = { bytes: number; counts: Record<string, number> };
const KINDS: [string, string][] = [
  ["scans", "Job scans and market history"],
  ["wishlist", "Wish list jobs"],
  ["companies", "Target companies"],
  ["analyses", "Analysed jobs and their tailored resumes"],
  ["tracker", "Tracker rows"],
  ["coach", "Interview practice history"],
  ["storyBank", "Story bank"],
  ["feedback", "Feedback notes"],
];

/** Manual clean-up so the local data file does not keep growing. Nothing is removed automatically. */
export function DataPanel() {
  const { t, patch, toast, run } = useApp();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);

  const load = () => api<Usage>("/api/data").then(setUsage, () => undefined);
  const clear = (what: string) =>
    run("data", async () => {
      const r = await api<Usage & { analyses: AnalysisRecord[]; tracker: TrackerRow[]; coach: CoachData; scout: ScoutData }>(`/api/data?what=${what}`, { method: "DELETE" });
      setUsage({ bytes: r.bytes, counts: r.counts });
      patch({ analyses: r.analyses, tracker: r.tracker, coach: r.coach, scout: r.scout });
      setConfirm(null);
      toast(t("Deleted."));
    });

  return (
    <details className="foot" onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) load(); }}>
      <summary style={{ cursor: "pointer" }}>{t("Manage saved data")}</summary>
      <div className="card" style={{ marginTop: 8 }}>
        <p className="sub">
          {t("Everything is stored on this computer and only removed when you delete it. Single items can be deleted where they are shown: a saved job or company in step 2, a job in step 3, a row in the tracker, a practice answer in the coach.")}
          {usage && <> · {t("Size on disk")}: {(usage.bytes / 1024).toFixed(0)} KB</>}
        </p>
        {usage && KINDS.map(([id, label]) => (
          <div className="row" key={id}>
            <span className="grow">{t(label)} <b>{usage.counts[id]}</b></span>
            {confirm === id ? (
              <>
                <button type="button" className="btn s" style={{ borderColor: "var(--bad)", color: "var(--bad)" }} onClick={() => clear(id)}>{t("Yes, delete all. This cannot be undone.")}</button>
                <button type="button" className="btn s" onClick={() => setConfirm(null)}>{t("Cancel")}</button>
              </>
            ) : (
              <button type="button" className="btn s" disabled={!usage.counts[id]} onClick={() => setConfirm(id)}>{t("Delete all")}</button>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}
