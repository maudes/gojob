"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CoachTab } from "@/components/CoachTab";
import { DataPanel } from "@/components/DataPanel";
import { JDTab } from "@/components/JDTab";
import { ProfileTab } from "@/components/ProfileTab";
import { ScoutTab } from "@/components/ScoutTab";
import { TrackerTab } from "@/components/TrackerTab";
import { api, AppCtx, translate, type App, type AppState, type Lang } from "@/components/ui";

type Tab = "profile" | "scout" | "jd" | "tracker" | "coach";
const HALF_YEAR = 183 * 86400000;

export default function Page() {
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("profile");
  const [lang, setLang] = useState<Lang>("en");
  const [busy, setBusy] = useState<string | null>(null);
  const [jdLink, setJdLink] = useState("");
  const [toastMsg, setToastMsg] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api<AppState>("/api/state").then(setState, (e) => setError(String(e.message ?? e)));
    try {
      const saved = localStorage.getItem("gojob-lang");
      if (saved === "zh" || saved === "en") setLang(saved);
    } catch {
      /* storage unavailable */
    }
  }, []);

  const toast = useCallback((msg: string) => {
    setToastMsg(msg);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToastMsg(""), 4500);
  }, []);

  const app = useMemo<App | null>(() => {
    if (!state) return null;
    const t = (en: string) => translate(lang, en);
    return {
      state,
      lang,
      t,
      toast,
      busy,
      go: setTab,
      jdLink,
      openJD: (url) => {
        setJdLink(url);
        setTab("jd");
      },
      patch: (p) => setState((s) => (s ? { ...s, ...p } : s)),
      putRecord: (r) =>
        setState((s) => (s ? { ...s, analyses: s.analyses.some((a) => a.id === r.id) ? s.analyses.map((a) => (a.id === r.id ? r : a)) : [r, ...s.analyses] } : s)),
      run: async (key, fn) => {
        setBusy(key);
        try {
          return await fn();
        } catch (e) {
          toast(t(e instanceof Error ? e.message : "Something went wrong."));
          return undefined;
        } finally {
          setBusy(null);
        }
      },
    };
  }, [state, lang, busy, toast, jdLink]);

  if (error) return <div className="shell"><p className="note bad">{error}</p></div>;
  if (!app || !state) return <div className="shell"><p className="sub">Loading…</p></div>;
  const { t } = app;
  const failed = state.config.tests.filter((x) => !x.pass);
  const resumeDate = state.profile.savedAt ? state.profile.resumeUpdatedAt ?? state.profile.savedAt : null;
  const resumeOld = resumeDate != null && Date.now() - Date.parse(resumeDate) > HALF_YEAR;
  const pickLang = (l: Lang) => {
    setLang(l);
    try {
      localStorage.setItem("gojob-lang", l);
    } catch {
      /* storage unavailable */
    }
  };

  return (
    <AppCtx.Provider value={app}>
      <div className="shell">
        <div className="top">
          <h1>Go<em>Job</em></h1>
          <div className="pills" role="tablist">
            {([["profile", "1 Profile"], ["scout", "2 Find jobs"], ["jd", "3 Target JD"], ["tracker", "4 Tracker"], ["coach", "5 Interview coach"]] as const).map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{t(label)}</button>
            ))}
          </div>
          <div className="pills sm">
            <button aria-selected={lang === "en"} onClick={() => pickLang("en")}>EN</button>
            <button aria-selected={lang === "zh"} onClick={() => pickLang("zh")}>繁中</button>
          </div>
        </div>

        {!state.config.live && (
          <p className="note">
            {t("No API key found, so every result is sample output. Add ANTHROPIC_API_KEY to .env.local and restart to run the real agents.")}
          </p>
        )}
        {failed.length > 0 && (
          <p className="note bad">
            {t("Self-test failed. Results may be unreliable until this is fixed:")} {failed.map((x) => x.name).join("; ")}
          </p>
        )}

        {resumeOld && (
          <p className="note">
            {t("Your resume was last updated more than six months ago:")} {resumeDate!.slice(0, 10)}. {t("Add your recent work before the next application.")}{" "}
            <button type="button" className="btn s" onClick={() => setTab("profile")}>{t("Update resume")}</button>
          </p>
        )}

        <div hidden={tab !== "profile"}><ProfileTab /></div>
        <div hidden={tab !== "scout"}><ScoutTab /></div>
        <div hidden={tab !== "jd"}><JDTab /></div>
        <div hidden={tab !== "tracker"}><TrackerTab /></div>
        <div hidden={tab !== "coach"}><CoachTab /></div>

        <p className="foot">
          {t("Self-test")}: {state.config.tests.length - failed.length}/{state.config.tests.length} {t("checks passed at start")} · {t("Writer")}: {state.config.mainModel} · {t("Auditors")}: {state.config.reviewerModel} · {t("Your data stays in this folder on your computer.")}
        </p>
        <DataPanel />
      </div>
      {toastMsg && <div className="toast" role="status">{toastMsg}</div>}
    </AppCtx.Provider>
  );
}
