import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { removeSource } from "@/lib/files";
import { emptyCoach, emptyScout } from "@/lib/schemas";
import { DB_FILE, readDB, updateDB } from "@/lib/store";

async function usage() {
  const db = await readDB();
  const dir = path.join(process.cwd(), "data", "files");
  const files = await fs.readdir(dir).catch(() => [] as string[]);
  let bytes = (await fs.stat(DB_FILE).catch(() => null))?.size ?? 0;
  for (const f of files) bytes += (await fs.stat(path.join(dir, f)).catch(() => null))?.size ?? 0;
  return {
    bytes,
    counts: { analyses: db.analyses.length, tracker: db.tracker.length, coach: db.coach.items.length, storyBank: db.coach.storyBank.text ? 1 : 0, feedback: db.feedback.length, wishlist: db.scout.wishlist.length, companies: db.scout.companies.length, scans: db.scout.history.length + (db.scout.report ? 1 : 0) },
  };
}

export const dynamic = "force-dynamic";
export const GET = async () => NextResponse.json(await usage());

/** Manual clean-up of one kind of saved data. Nothing is removed automatically. */
export async function DELETE(req: Request) {
  const what = new URL(req.url).searchParams.get("what");
  const ids = await updateDB((db) => {
    const removed = what === "analyses" ? db.analyses.map((a) => a.id) : [];
    if (what === "analyses") db.analyses = [];
    else if (what === "tracker") db.tracker = [];
    else if (what === "coach") db.coach = { ...db.coach, items: [], report: null };
    else if (what === "storyBank") db.coach.storyBank = structuredClone(emptyCoach.storyBank);
    else if (what === "feedback") db.feedback = [];
    else if (what === "wishlist") db.scout.wishlist = [];
    else if (what === "companies") db.scout.companies = [];
    else if (what === "scans") db.scout = { ...db.scout, report: null, history: structuredClone(emptyScout.history) };
    return removed;
  });
  await Promise.all(ids.map((id) => removeSource(`jd-${id}`)));
  const db = await readDB();
  return NextResponse.json({ ...(await usage()), analyses: db.analyses, tracker: db.tracker, coach: db.coach, scout: db.scout });
}
