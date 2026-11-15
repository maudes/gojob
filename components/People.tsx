"use client";

import type { ReactNode } from "react";
import type { Networking } from "@/lib/schemas";
import { copy, useApp } from "./ui";

type Person = Networking["targets"][number];
const TYPE = { hiring_manager_or_hr: "Hiring manager / HR", employee: "Team member", similar_background: "Similar background" } as const;
const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;

/** People found by web search, each with two first-contact messages and the rule counters. */
export function PeopleList({ targets, action }: { targets: Person[]; action?: (p: Person) => ReactNode }) {
  const { t, toast } = useApp();
  return (
    <div>
      {targets.map((p, i) => (
        <div className="it" key={i}>
          <div className="row">
            <div className="grow"><h3>{p.name}</h3><p className="sub">{p.title}</p></div>
            <span className="badge">{t(TYPE[p.type])}</span>
            {/^https?:\/\//.test(p.profileUrl) && <a href={p.profileUrl} target="_blank" rel="noopener noreferrer">{t("Open LinkedIn profile")}</a>}
          </div>
          <p className="sub">{p.why}</p>
          {p.messages.map((m, k) => {
            const marks = (m.text.match(/\?/g) ?? []).length;
            const count = words(m.text);
            return (
              <div className="plain" key={k}>
                <p className="sub"><b>{t("Message")} {k + 1} · {m.angle}</b></p>
                <p className="rw msg">{m.text}</p>
                <div className="row sub">
                  <span className={count > 75 || marks !== 1 ? "badge bad" : ""}>{count} / 75 {t("words")} · {marks} {t("question")}</span>
                  <button type="button" className="btn s" onClick={async () => toast(t((await copy(m.text)) ? "Copied" : "Copying was blocked by the browser."))}>{t("Copy")}</button>
                </div>
              </div>
            );
          })}
          {action && <div>{action(p)}</div>}
        </div>
      ))}
    </div>
  );
}
