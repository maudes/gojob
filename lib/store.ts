import { promises as fs } from "node:fs";
import path from "node:path";
import {
  emptyCoach,
  emptyScout,
  emptyProfile,
  type CoachData,
  type AnalysisRecord,
  type HealthRecord,
  type Profile,
  type ScoutData,
  type TrackerRow,
} from "./schemas";

/** Everything lives in one local JSON file. Nothing leaves this machine except model calls. */
export type DB = {
  profile: Profile;
  health: HealthRecord | null;
  healthRuns: number;
  analyses: AnalysisRecord[];
  tracker: TrackerRow[];
  feedback: { at: string; feature: string; message: string }[];
  coach: CoachData;
  scout: ScoutData;
};

const FILE = path.join(process.cwd(), "data", "db.json");

const empty: DB = {
  profile: emptyProfile,
  health: null,
  healthRuns: 0,
  analyses: [],
  tracker: [],
  feedback: [],
  coach: emptyCoach,
  scout: emptyScout,
};

export async function readDB(): Promise<DB> {
  try {
    const raw = await fs.readFile(FILE, "utf8");
    const db = { ...structuredClone(empty), ...JSON.parse(raw) } as DB;
    db.profile = { ...emptyProfile, ...db.profile };
    db.coach = { ...structuredClone(emptyCoach), ...db.coach };
    db.scout = { ...structuredClone(emptyScout), ...db.scout };
    return db;
  } catch {
    return structuredClone(empty);
  }
}

let queue: Promise<unknown> = Promise.resolve();

/** Serialised read-modify-write so parallel requests cannot clobber each other. */
export function updateDB<T>(fn: (db: DB) => T | Promise<T>): Promise<T> {
  const next = queue.then(async () => {
    const db = await readDB();
    const result = await fn(db);
    await fs.mkdir(path.dirname(FILE), { recursive: true });
    await fs.writeFile(FILE, JSON.stringify(db, null, 2), "utf8");
    return result;
  });
  queue = next.catch(() => undefined);
  return next;
}

export const DB_FILE = FILE;
export const newId = () => Math.random().toString(36).slice(2, 10);
