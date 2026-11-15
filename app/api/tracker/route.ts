import { NextResponse } from "next/server";
import { TrackerStatus, type TrackerRow } from "@/lib/schemas";
import { newId, updateDB } from "@/lib/store";

const FIELDS = ["company", "position", "location", "jobLink", "oneLine", "matchingScore", "applyDate", "networkTarget", "notes"] as const;

function clean(input: Record<string, unknown>): Partial<TrackerRow> {
  const out: Partial<TrackerRow> = {};
  for (const f of FIELDS) if (typeof input[f] === "string") out[f] = input[f] as string;
  const status = TrackerStatus.safeParse(input.status);
  if (status.success) out.status = status.data;
  return out;
}

export async function POST(req: Request) {
  const row: TrackerRow = {
    id: newId(),
    company: "", position: "", location: "", jobLink: "", oneLine: "", matchingScore: "",
    applyDate: "", networkTarget: "", status: "Apply", notes: "",
    ...clean(await req.json()),
  };
  const tracker = await updateDB((d) => {
    d.tracker.unshift(row);
    return d.tracker;
  });
  return NextResponse.json({ tracker, row });
}

export async function PATCH(req: Request) {
  const body = await req.json();
  const tracker = await updateDB((d) => {
    const row = d.tracker.find((r) => r.id === body.id);
    if (row) Object.assign(row, clean(body));
    return d.tracker;
  });
  return NextResponse.json({ tracker });
}

export async function DELETE(req: Request) {
  const id = new URL(req.url).searchParams.get("id");
  const tracker = await updateDB((d) => {
    d.tracker = d.tracker.filter((r) => r.id !== id);
    return d.tracker;
  });
  return NextResponse.json({ tracker });
}
