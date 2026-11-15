import { NextResponse } from "next/server";
import { readJobPage } from "@/lib/jobpage";

export const maxDuration = 60;

/** Try to read a job page from its link. When nothing works the UI asks the user to paste the text. */
export async function POST(req: Request) {
  const { url } = (await req.json()) as { url?: string };
  const page = await readJobPage(url ?? "");
  return NextResponse.json(page ? { ok: true, ...page } : { ok: false });
}
