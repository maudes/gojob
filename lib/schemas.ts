import { z } from "zod";

/* ---------- Shared building blocks ---------- */

export const Label = z.enum(["confirmed", "inference", "needs_confirmation"]);
export type Label = z.infer<typeof Label>;

/** A verbatim quote plus where it came from. Empty quote = no evidence exists. */
export const Evidence = z.object({
  source: z.enum(["resume", "jd", "profile", "none"]),
  quote: z.string(),
});
export type Evidence = z.infer<typeof Evidence>;

/**
 * One tracked change to the resume. `find` is copied word for word from the resume
 * (one line or part of one line); `replace` is the full new text for that span.
 */
export const ResumeChange = z.object({
  section: z.string(),
  find: z.string(),
  replace: z.string(),
  reason: z.string(),
  label: Label,
});
export type ResumeChange = z.infer<typeof ResumeChange>;

/* ---------- Profile (user input, never model output) ---------- */

export const TargetJD = z.object({
  id: z.string(),
  title: z.string(),
  text: z.string(),
});

export const Profile = z.object({
  resumeText: z.string(),
  resumeFileName: z.string(),
  resumeLink: z.string(),
  resumeFormat: z.enum(["docx", "other", ""]),
  linkedinUrl: z.string(),
  websiteUrl: z.string(),
  linkedinText: z.string(),
  websiteText: z.string(),
  roles: z.array(z.string()).max(2),
  domains: z.array(z.string()).max(3),
  targetJDs: z.array(TargetJD).max(10),
  regions: z.array(z.string()),
  sponsorship: z.boolean(),
  /** Countries where the candidate can already work, so sponsorship is not needed there. */
  workAuthorized: z.array(z.string()).max(10),
  workModes: z.array(z.enum(["remote", "onsite", "hybrid"])),
  fullTimeOnly: z.literal(true),
  sheetUrl: z.string(),
  /** When the resume content last changed. Drives the six-month reminder. */
  resumeUpdatedAt: z.string().nullable(),
  savedAt: z.string().nullable(),
});
export type Profile = z.infer<typeof Profile>;

export const emptyProfile: Profile = {
  resumeText: "",
  resumeFileName: "",
  resumeLink: "",
  resumeFormat: "",
  linkedinUrl: "",
  websiteUrl: "",
  linkedinText: "",
  websiteText: "",
  roles: [],
  domains: [],
  targetJDs: [],
  regions: [],
  sponsorship: false,
  workAuthorized: [],
  workModes: [],
  fullTimeOnly: true,
  sheetUrl: "",
  resumeUpdatedAt: null,
  savedAt: null,
};

/* ---------- Review layers ---------- */

/** One of the three scoring reviewers (ATS, recruiter, hiring manager). */
export const PanelScore = z.object({
  score: z.number(),
  verdict: z.string(),
  strengths: z.array(z.object({ point: z.string(), proof: Evidence })),
  gaps: z.array(z.object({ point: z.string(), proof: Evidence })),
});
export type PanelScore = z.infer<typeof PanelScore>;

/** One of the three lightweight fidelity auditors. */
export const Audit = z.object({
  score: z.number(),
  checks: z.object({
    resumeQuotesVerbatim: z.boolean(),
    jdQuotesVerbatim: z.boolean(),
    noInventedFacts: z.boolean(),
    labelsCorrect: z.boolean(),
    alignedWithProfile: z.boolean(),
  }),
  issues: z.array(z.string()),
});
export type Audit = z.infer<typeof Audit>;

/* ---------- Profile health check ---------- */

export const HealthCheck = z.object({
  roleConflict: z.object({ conflict: z.boolean(), reason: z.string() }),
  positioning: z.object({
    statement: z.string(),
    closeToTruth: z.string(),
    closeToTarget: z.string(),
  }),
  keywords: z.array(
    z.object({
      keyword: z.string(),
      jdCount: z.number(),
      status: z.enum(["covered", "terminology_gap", "needs_confirmation"]),
      proof: Evidence,
    }),
  ),
  changes: z.array(ResumeChange),
});
export type HealthCheck = z.infer<typeof HealthCheck>;

/* ---------- Target JD analysis ---------- */

export const Verdict = z.enum(["green", "mint", "yellow", "orange", "red"]);

export const JDAnalysis = z.object({
  meta: z.object({
    company: z.string(),
    title: z.string(),
    location: z.string(),
    oneLine: z.string(),
  }),
  companyContext: z.string(),
  strategy: z.object({ verdict: Verdict, instruction: z.string() }),
  atsMatch: z.object({ score: z.number(), basis: z.string() }),
  recruiterProbability: z.object({ score: z.number(), basis: z.string() }),
  projectedAts: z.object({ score: z.number(), basis: z.string() }),
  requirements: z.array(
    z.object({
      requirement: Evidence,
      evidence: Evidence,
      label: Label,
      note: z.string(),
    }),
  ),
  missingKeywords: z.array(
    z.object({
      keyword: z.string(),
      whereToAdd: z.string(),
      reason: z.string(),
      label: Label,
    }),
  ),
  profileFit: z.array(
    z.object({
      item: z.enum(["region", "sponsorship", "work_mode", "full_time", "role", "domain"]),
      status: z.enum(["ok", "risk", "unknown"]),
      note: z.string(),
    }),
  ),
});
export type JDAnalysis = z.infer<typeof JDAnalysis>;

/* ---------- Follow-up actions ---------- */

export const FineTune = z.object({
  headlineTags: z.array(z.string()),
  changes: z.array(ResumeChange),
  bulletOrder: z.array(
    z.object({ section: z.string(), orderedBullets: z.array(z.string()), drop: z.array(z.string()), reason: z.string() }),
  ),
  additions: z.array(
    z.object({ type: z.enum(["project", "skill"]), suggestion: z.string(), basis: z.string(), label: Label }),
  ),
});
export type FineTune = z.infer<typeof FineTune>;

export const CoverLetter = z.object({
  needsStory: z.boolean(),
  storyRequest: z.string(),
  coreProblem: z.object({ text: z.string(), label: Label }),
  letter: z.string(),
  factCheck: z.array(z.object({ claim: z.string(), label: Label, proof: Evidence })),
});
export type CoverLetter = z.infer<typeof CoverLetter>;

export const Interview = z.object({
  riskMap: z.array(
    z.object({
      requirement: Evidence,
      evidence: Evidence,
      likelyQuestion: z.string(),
      risk: z.string(),
      preparation: z.string(),
    }),
  ),
  questions: z.array(
    z.object({
      category: z.enum([
        "recruiter_screen",
        "hiring_manager",
        "technical_functional",
        "behavioral",
        "motivation",
        "domain",
      ]),
      interviewer: z.string(),
      question: z.string(),
      why: z.string(),
      mustProve: z.string(),
      keyElements: z.array(z.string()),
      evidence: Evidence,
      concern: z.string(),
    }),
  ),
});
export type Interview = z.infer<typeof Interview>;

export const Networking = z.object({
  targets: z.array(
    z.object({
      type: z.enum(["hiring_manager_or_hr", "employee", "similar_background"]),
      name: z.string(),
      title: z.string(),
      profileUrl: z.string(),
      why: z.string(),
      messages: z.array(z.object({ angle: z.string(), text: z.string() })),
    }),
  ),
  note: z.string(),
});
export type Networking = z.infer<typeof Networking>;

/* ---------- Stored records ---------- */

export type Gate = {
  kind: "panel";
  scores: number[];
  average: number;
  min: number;
  needAverage: number;
  needMin: number;
  green: boolean;
};

export type QuoteCheck = {
  total: number;
  verified: number;
  failed: { source: string; quote: string }[];
};

/** The outcome of the five-auditor fidelity review of one AI output. */
export type AuditResult = { audits: Audit[]; approved: boolean; quoteCheck: QuoteCheck; demo: boolean };

export type Reviewed<T> = AuditResult & { output: T; runs: number; generatedAt: string };

export type ActionKind = "fineTune" | "coverLetter" | "interview" | "networking" | "onePager";

export type ScorePoint = { at: string; average: number; scores: number[] };

export type AnalysisRecord = {
  id: string;
  jdUrl: string;
  jdText: string;
  createdAt: string;
  /** Resume tailored to this JD. Null means the saved profile resume is used. */
  tailoredText: string | null;
  /** The resume text the current assessment was run on. */
  assessedText: string;
  history: ScorePoint[];
  networkTarget: string;
  analysis: Reviewed<JDAnalysis>;
  panel: (PanelScore & { reviewer: string })[];
  panelAudit?: AuditResult;
  gate: Gate;
  actions: {
    fineTune?: Reviewed<FineTune>;
    coverLetter?: Reviewed<CoverLetter>;
    interview?: Reviewed<Interview>;
    networking?: Reviewed<Networking>;
    onePager?: { html: string; runs: number; demo: boolean; generatedAt: string; audit?: AuditResult };
  };
};

export type HealthRecord = {
  check: Reviewed<HealthCheck>;
  panel: (PanelScore & { reviewer: string })[];
  panelAudit?: AuditResult;
  gate: Gate;
  profileSavedAt: string | null;
};

export const TrackerStatus = z.enum(["Apply", "HR", "Interview", "Reject"]);
export type TrackerRow = {
  id: string;
  company: string;
  position: string;
  location: string;
  jobLink: string;
  oneLine: string;
  matchingScore: string;
  applyDate: string;
  networkTarget: string;
  status: z.infer<typeof TrackerStatus>;
  notes: string;
};

/* ---------- Interview coach ---------- */

export const CoachCategory = z.enum(["self_intro", "behavioral", "general", "story", "jd", "product"]);
export type CoachCategory = z.infer<typeof CoachCategory>;

export const Weakness = z.enum([
  "too_long", "too_short", "unclear_situation", "no_challenge", "no_decision", "no_impact", "weak_relevance", "grammar", "vague_wording",
]);
export type Weakness = z.infer<typeof Weakness>;

export const CoachQuestion = z.object({ question: z.string(), storyHint: z.string(), why: z.string() });

export const CoachFeedback = z.object({
  score: z.number(),
  headline: z.string(),
  content: z.array(
    z.object({ element: z.enum(["situation", "challenge", "decision", "impact", "relevance"]), present: z.boolean(), note: z.string() }),
  ),
  english: z.array(z.object({ original: z.string(), better: z.string(), why: z.string() })),
  delivery: z.string(),
  tighter: z.string(),
  weaknesses: z.array(Weakness),
  confirm: z.array(z.string()),
});
export type CoachFeedback = z.infer<typeof CoachFeedback>;

export const CoachReport = z.object({
  strengths: z.array(z.string()),
  weakAreas: z.array(z.string()),
  prepare: z.array(z.string()),
  delivery30: z.string(),
  delivery2min: z.string(),
});

export type CoachMode = "30s" | "2min";
export type CoachPrompt = { category: CoachCategory; source: string; question: string; storyHint: string; why: string; demo: boolean; audit?: AuditResult };
export type CoachItem = CoachPrompt & { id: string; at: string; mode: CoachMode; answer: string; seconds: number; feedback: CoachFeedback; feedbackAudit?: AuditResult };
export type CoachData = {
  storyBank: { text: string; name: string; updatedAt: string | null };
  items: CoachItem[];
  report: { at: string; counts: Record<string, number>; total: number; output: z.infer<typeof CoachReport>; demo: boolean; audit?: AuditResult } | null;
};
export const emptyCoach: CoachData = { storyBank: { text: "", name: "", updatedAt: null }, items: [], report: null };

/* ---------- Job scout (step 2): headhunter scan, wish list, target companies ---------- */

const text = z.string().catch("");
const proof = Evidence.catch({ source: "none", quote: "" });
const label = Label.catch("needs_confirmation");

export const ScoutJob = z.object({
  tier: z.enum(["A", "B", "C"]).catch("C"),
  company: z.string(),
  title: z.string(),
  location: text,
  visa: z.enum(["offered", "not_mentioned", "needs_confirmation"]).catch("needs_confirmation"),
  visaNote: text,
  posted: text,
  url: z.string(),
  fit: text,
  proof,
  label,
});
export type ScoutJob = z.infer<typeof ScoutJob>;

export const ScoutCompany = z.object({
  company: z.string(),
  url: text,
  signal: text,
  signalUrl: text,
  why: text,
  roleType: text,
  approach: text,
  proof,
  label,
});
export type ScoutCompany = z.infer<typeof ScoutCompany>;

export const ScoutReport = z.object({
  headline: text,
  regions: z
    .array(z.object({ region: z.string(), heat: z.enum(["warming", "steady", "cooling", "unknown"]).catch("unknown"), summary: text, label, sourceUrl: text }))
    .catch([]),
  jobs: z.array(ScoutJob).catch([]),
  companies: z.array(ScoutCompany).catch([]),
  weekly: text,
  priorities: z.array(z.string()).catch([]),
  unreachable: z.array(z.string()).catch([]),
});
export type ScoutReport = z.infer<typeof ScoutReport>;

export const CompanyOpenings = z.object({
  openings: z.array(z.object({ title: z.string(), location: text, url: z.string(), fit: text, proof, label })).catch([]),
  note: text,
});
export type CompanyOpenings = z.infer<typeof CompanyOpenings>;

/** verified = the app opened the link itself and it read like an open job posting. */
export type LinkStatus = "verified" | "unverified" | "sample";
export type ScoutSettings = { regions: string[]; languages: string[]; notes: string };

export const WISH_DECISIONS = ["Deciding", "Will apply", "Applied", "Pass"] as const;
export type WishJob = {
  id: string;
  company: string;
  title: string;
  location: string;
  url: string;
  tier: string;
  visa: string;
  posted: string;
  fit: string;
  decision: (typeof WISH_DECISIONS)[number];
  notes: string;
  savedAt: string;
  lastChecked: string | null;
  open: "open" | "unconfirmed" | null;
};

export const COMPANY_STATUSES = ["Watching", "Reached out", "In conversation", "Paused"] as const;
export type WatchOpening = { title: string; location: string; url: string; fit: string; firstSeen: string; isNew: boolean; link: LinkStatus };
export type WatchCompany = {
  id: string;
  company: string;
  careersUrl: string;
  why: string;
  roleType: string;
  contact: string;
  status: (typeof COMPANY_STATUSES)[number];
  notes: string;
  addedAt: string;
  lastChecked: string | null;
  openings: WatchOpening[];
  openingsNote: string;
  openingsAudit?: AuditResult;
  people?: Reviewed<Networking>;
};

export type ScoutRun = AuditResult & { output: ScoutReport; links: Record<string, LinkStatus>; dropped: number; at: string; runs: number };
export type ScoutData = {
  settings: ScoutSettings | null;
  report: ScoutRun | null;
  history: { at: string; headline: string; regions: { region: string; heat: string }[] }[];
  wishlist: WishJob[];
  companies: WatchCompany[];
};
export const emptyScout: ScoutData = { settings: null, report: null, history: [], wishlist: [], companies: [] };
