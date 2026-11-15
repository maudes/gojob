/** Free, deterministic checks run on every start. No model calls. */
import { applyChangesToDocx, docxToText, textToDocx } from "./docx";
import { checkQuotes, gate, isApproved } from "./pipeline";
import type { Audit } from "./schemas";
import { keepLinked } from "./scout";
import { applyToText, diffOps, isVerbatim, redact, tier, trackerTSV } from "./text";

export type SelfTest = { name: string; pass: boolean }[];

const audit = (score: number, ok = true): Audit => ({
  score,
  checks: { resumeQuotesVerbatim: ok, jdQuotesVerbatim: true, noInventedFacts: true, labelsCorrect: true, alignedWithProfile: true },
  issues: [],
});
const clean = { total: 1, verified: 1, failed: [] };

async function run(): Promise<SelfTest> {
  const t = (name: string, pass: boolean) => ({ name, pass });
  const out: SelfTest = [];
  const red = redact("Jane Doe · jane.doe@mail.com · +353 87 123 4567 · 2019 - 2023");
  out.push(t("Contact details are removed", !red.includes("@") && !red.includes("123 4567") && red.includes("2019 - 2023")));
  out.push(t("Quote check accepts word-for-word text", isVerbatim("•  Led   Matter integration", "- Led Matter integration across teams")));
  out.push(t("Quote check rejects altered text", !isVerbatim("Led Matter integrations", "Led Matter integration across teams")));
  const qc = checkQuotes({ a: { source: "resume", quote: "not there" }, c: [{ find: "Owned roadmap", replace: "x" }] }, { resume: "Owned roadmap", jd: "" });
  out.push(t("Unverified quotes are counted", qc.total === 2 && qc.failed.length === 1));
  out.push(t("Health gate: average 80, minimum 70", gate([80, 80, 80], 80, 70).green && !gate([95, 95, 69], 80, 70).green && !gate([79, 80, 80], 80, 70).green));
  out.push(t("JD tiers: 80 apply, 60 tune, below risky", tier(80, 60) === "apply" && tier(79.9, 70) === "tune" && tier(85, 59) === "tune" && tier(59.9, 50) === "risky"));
  out.push(t("Approval needs five auditors above 95", isApproved([96, 96, 96, 96, 96].map((s) => audit(s)), clean) && !isApproved([96, 96, 96, 96, 95].map((s) => audit(s)), clean) && !isApproved([99, 99, 99, 99].map((s) => audit(s)), clean)));
  out.push(t("Approval needs every box and every quote", !isApproved([99, 99, 99, 99, 99].map((s, i) => audit(s, i !== 2)), clean) && !isApproved([99, 99, 99, 99, 99].map((s) => audit(s)), { total: 1, verified: 0, failed: [{ source: "resume", quote: "x" }] })));
  const ops = diffOps("Aligned firmware teams", "Managed stakeholders across firmware teams");
  out.push(t("Tracked changes show removed and added text", ops.some((o) => o.type === "del" && o.text.includes("Aligned")) && ops.some((o) => o.type === "ins" && o.text.includes("Managed"))));
  out.push(t("Accepted changes apply to text", applyToText("A\nOwned roadmap\nB", [{ find: "Owned roadmap", replace: "Owned the roadmap" }]).text === "A\nOwned the roadmap\nB"));
  try {
    const docx = await textToDocx("Jane Doe\nEXPERIENCE\n- Owned the connectivity roadmap\n- Built middleware");
    const edited = await applyChangesToDocx(docx, [{ find: "Owned the connectivity roadmap", replace: "Owned the connectivity roadmap for [X] products" }]);
    const text = await docxToText(edited.bytes);
    out.push(t("Word file is edited in place", edited.missed.length === 0 && text.includes("for [X] products") && text.includes("Built middleware")));
  } catch {
    out.push(t("Word file is edited in place", false));
  }
  const tsv = trackerTSV({ company: "A", position: "B", location: "C", jobLink: "D", oneLine: "E\tx", matchingScore: "71", applyDate: "2026-01-01", networkTarget: "F", status: "Apply", notes: "" });
  out.push(t("Tracker row follows the sheet column order", tsv === "A\tB\tC\tD\tE x\t71\t2026-01-01\tF\tApply\t"));
  const linked = keepLinked([{ url: "https://jobs.example.com/1" }, { url: "" }, { url: "see careers page" }, { url: "http://localhost/x" }]);
  out.push(t("Scan drops jobs without a real link", linked.kept.length === 1 && linked.dropped === 3));
  return out;
}

let cached: Promise<SelfTest> | null = null;
export const selfTest = () => (cached ??= run());
