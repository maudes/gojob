import { NextResponse } from "next/server";
import { hasCredentials, MAIN_MODEL, REVIEWER_MODEL } from "@/lib/claude";
import { selfTest } from "@/lib/selftest";
import { readDB } from "@/lib/store";

export const dynamic = "force-dynamic";

export async function GET() {
  const [db, tests] = await Promise.all([readDB(), selfTest()]);
  return NextResponse.json({
    profile: db.profile,
    health: db.health,
    analyses: db.analyses,
    tracker: db.tracker,
    coach: db.coach,
    scout: db.scout,
    config: { live: hasCredentials(), mainModel: MAIN_MODEL, reviewerModel: REVIEWER_MODEL, tests },
  });
}
