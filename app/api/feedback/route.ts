import { NextResponse } from "next/server";
import { updateDB } from "@/lib/store";

export async function POST(req: Request) {
  const { feature, message } = (await req.json()) as { feature?: string; message?: string };
  if (!message?.trim()) return NextResponse.json({ error: "Empty feedback." }, { status: 400 });
  await updateDB((d) => {
    d.feedback.push({ at: new Date().toISOString(), feature: String(feature ?? ""), message: message.trim().slice(0, 4000) });
  });
  return NextResponse.json({ ok: true });
}
