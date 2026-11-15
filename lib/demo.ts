/**
 * Sample output shown when no API key is configured, so the whole flow can be clicked
 * through. Scores, the job and the people are invented. The sample resume changes are
 * built from the user's own resume lines so accepting and exporting them really works.
 */
import type {
  Audit,
  CoverLetter,
  FineTune,
  HealthCheck,
  Interview,
  JDAnalysis,
  Networking,
  PanelScore,
  ResumeChange,
} from "./schemas";

const j = (quote: string) => ({ source: "jd" as const, quote });
const none = { source: "none" as const, quote: "" };

export const audits: Audit[] = [97, 96, 98, 96, 99].map((score) => ({
  score,
  checks: {
    resumeQuotesVerbatim: true,
    jdQuotesVerbatim: true,
    noInventedFacts: true,
    labelsCorrect: true,
    alignedWithProfile: true,
  },
  issues: [],
}));

export const panel = (scores: number[]): (PanelScore & { reviewer: string })[] =>
  ["ATS", "Recruiter", "Hiring manager"].map((reviewer, i) => ({
    reviewer,
    score: scores[i],
    verdict: "Sample verdict. Add an API key to get a real one.",
    strengths: [],
    gaps: [],
  }));

/** Two sample tracked changes on real lines of the resume. */
function sampleChanges(resume: string): ResumeChange[] {
  const lines = resume.split("\n").map((l) => l.trim()).filter((l) => l.split(/\s+/).length >= 6 && l.length < 220);
  const out: ResumeChange[] = [];
  if (lines[0]) {
    const words = lines[0].split(" ");
    out.push({
      section: "Sample",
      find: lines[0],
      replace: `${words.slice(0, 3).join(" ")} (sample rewording) ${words.slice(3).join(" ")}`,
      reason: "Sample change. A real run explains which JD requirement this serves.",
      label: "inference",
    });
  }
  if (lines[1])
    out.push({
      section: "Sample",
      find: lines[1],
      replace: `${lines[1].replace(/[.;]$/, "")}, resulting in [X%] improvement`,
      reason: "Sample change. Outcome missing; replace [X%] with your real number or reject.",
      label: "needs_confirmation",
    });
  return out;
}

export const health = (resume: string): HealthCheck => ({
  roleConflict: { conflict: false, reason: "Sample result. A real run checks whether your roles share a job family." },
  positioning: {
    statement: "Sample: the resume positions you by technology rather than by product outcome.",
    closeToTruth: "Sample: close to the experience shown.",
    closeToTarget: "Sample: target JDs ask for terms the resume does not yet use.",
  },
  keywords: [
    { keyword: "Roadmap", jdCount: 3, status: "covered", proof: none },
    { keyword: "Stakeholder management", jdCount: 3, status: "terminology_gap", proof: none },
    { keyword: "A/B testing", jdCount: 2, status: "needs_confirmation", proof: none },
  ],
  changes: sampleChanges(resume),
});

export const jdAnalysis: JDAnalysis = {
  meta: {
    company: "Sample Home Co",
    title: "Senior Product Manager, Connected Devices",
    location: "Dublin, Ireland (Hybrid)",
    oneLine: "Own the roadmap for a smart home device line and its partner integrations.",
  },
  companyContext: "Sample result. A real run summarises the company and product from the JD you supplied.",
  strategy: { verdict: "yellow", instruction: "Sample: fine-tune the summary and two bullets, then re-assess." },
  atsMatch: { score: 68, basis: "Sample basis." },
  recruiterProbability: { score: 62, basis: "Sample basis. Rough diagnostic only." },
  projectedAts: { score: 81, basis: "Sample basis." },
  requirements: [
    {
      requirement: j("(sample) 5+ years of product management experience with connected hardware"),
      evidence: none,
      label: "inference",
      note: "Sample row. A real run quotes your resume here.",
    },
    {
      requirement: j("(sample) Experience running experiments to inform prioritisation"),
      evidence: none,
      label: "needs_confirmation",
      note: "Sample row.",
    },
  ],
  missingKeywords: [
    { keyword: "Go-to-market", whereToAdd: "Summary", reason: "Sample reason.", label: "inference" },
    { keyword: "Experimentation", whereToAdd: "Do not add yet", reason: "Sample: no resume evidence.", label: "needs_confirmation" },
  ],
  profileFit: [
    { item: "region", status: "ok", note: "Sample." },
    { item: "sponsorship", status: "unknown", note: "Sample: the JD does not mention sponsorship." },
    { item: "work_mode", status: "ok", note: "Sample." },
    { item: "full_time", status: "ok", note: "Sample." },
  ],
};

export const fineTune = (resume: string): FineTune => ({
  headlineTags: ["Connected Devices", "Partner Integrations", "Roadmap"],
  changes: sampleChanges(resume),
  bulletOrder: [],
  additions: [
    {
      type: "project",
      suggestion: "Sample: have you run a pricing or packaging experiment you could describe?",
      basis: "Sample basis.",
      label: "needs_confirmation",
    },
  ],
});

export const coverLetter = (story: string): CoverLetter =>
  story.trim().length < 40
    ? {
        needsStory: true,
        storyRequest: "Say in your own words why this company and why this role. The letter opens with it.",
        coreProblem: { text: "Sample core problem.", label: "inference" },
        letter: "",
        factCheck: [],
      }
    : {
        needsStory: false,
        storyRequest: "",
        coreProblem: { text: "Sample core problem.", label: "inference" },
        letter: `Dear Hiring Team,\n\n${story.trim()}\n\n(Sample letter. A real run writes 250 to 400 words from your story and resume, then lists every claim for you to check.)\n\nKind regards,`,
        factCheck: [{ claim: "Opening story", label: "confirmed", proof: { source: "profile", quote: "Provided by you" } }],
      };

const interview: Interview = {
  riskMap: [
    {
      requirement: j("(sample) Experience running experiments to inform prioritisation"),
      evidence: none,
      likelyQuestion: "Tell me about a decision you changed because of data.",
      risk: "High, because it is a listed requirement and the resume shows no experiment.",
      preparation: "Prepare one real decision with the data you used.",
    },
  ],
  questions: [
    ["Product lead", "Walk me through a product decision where a firmware constraint forced you to change the roadmap. What did you give up?"],
    ["Product lead", "How did factory realities such as yield, test time or lead times change a requirement you wrote?"],
    ["Product lead", "Look at our flow from unboxing to the first automation. What would you change first, and how would you prove it worked?"],
    ["Product lead", "From the outside, where does our product process most need adjusting?"],
    ["Product lead", "A partner changes its certification requirement three weeks before launch. Talk me through your first 48 hours."],
    ["Product lead", "How do you choose between a feature a partner demands and one our data says users need?"],
    ["Product lead", "Which part of our roadmap would you stop investing in, and why?"],
    ["Engineering lead", "How do you write requirements for firmware differently from cloud or app?"],
    ["Designer", "Tell me about a time feasibility and the ideal experience conflicted. Who decided?"],
    ["Peer PM", "Which metric would you add to the device team's dashboard, and which would you remove?"],
    ["QA", "A field issue shows on 2% of devices only. How do you handle it?"],
    ["Product lead", "Why this move now, and what would make you leave after a year?"],
  ].map(([interviewer, question]) => ({
    category: "hiring_manager" as const,
    interviewer,
    question,
    why: "Sample reason.",
    mustProve: "Sample competency.",
    keyElements: ["The constraint", "Options you weighed", "The call you made", "Result"],
    evidence: none,
    concern: "Sample concern.",
  })),
};

const networking: Networking = {
  targets: [
    {
      type: "hiring_manager_or_hr",
      name: "Sample Person",
      title: "Head of Product, Connected Devices · Sample Home Co",
      profileUrl: "https://www.linkedin.com/search/results/people/?keywords=Head%20of%20Product%20Connected%20Devices",
      why: "Sample: one level above the role and likely the hiring manager.",
      messages: [
        {
          angle: "Content follower",
          text: "Hi [Name], your post on [topic of their recent post] made me rethink how partner certification shapes a device roadmap. You have led connected devices through several ecosystem shifts. I would value your view on where device teams lose the most time today. Would you be open to a 20-minute call in the next two weeks?",
        },
        {
          angle: "Quick question",
          text: "Hi [Name], I am reaching out cold because your path from [previous role] to leading connected devices stood out. One question I think you can answer in a minute: which partner ecosystem shapes your roadmap the most right now?",
        },
      ],
    },
  ],
  note: "Sample list. A real run searches the web for people at the company and returns their names, titles and LinkedIn links.",
};

export const actions = { interview, networking };

export const onePagerHtml = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{font-family:system-ui;margin:40px;color:#374151}h1{color:#DC2626}</style></head><body><h1>Sample one-pager</h1><p>This is placeholder output. Add an API key to generate the researched company one-pager with cited sources.</p></body></html>`;
