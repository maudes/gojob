/** Turn an uploaded resume or a fetched job page into plain text. Server only. */

export async function fileToText(name: string, bytes: Uint8Array): Promise<string> {
  const lower = name.toLowerCase();
  if (lower.endsWith(".pdf")) {
    const { extractText, getDocumentProxy } = await import("unpdf");
    const pdf = await getDocumentProxy(bytes);
    const { text } = await extractText(pdf, { mergePages: true });
    return tidy(text);
  }
  if (lower.endsWith(".docx")) {
    const mammoth = await import("mammoth");
    const { value } = await mammoth.extractRawText({ buffer: Buffer.from(bytes) });
    return tidy(value);
  }
  if (/\.(txt|md|markdown)$/.test(lower)) return tidy(new TextDecoder().decode(bytes));
  throw new Error("Unsupported file type. Use PDF, DOCX, TXT or MD.");
}

const tidy = (s: string) => s.replace(/\r/g, "").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", "#39": "'" };

export function htmlToText(html: string): string {
  // Many job boards embed the posting as JSON-LD; prefer it when present.
  for (const m of html.matchAll(/<script[^>]*application\/ld\+json[^>]*>([\s\S]*?)<\/script>/gi)) {
    try {
      const data = JSON.parse(m[1]);
      const items = Array.isArray(data) ? data : [data, ...(data["@graph"] ?? [])];
      const job = items.find((x) => x && x["@type"] === "JobPosting");
      if (job?.description) {
        const where = job.jobLocation?.address?.addressLocality ?? job.jobLocation?.[0]?.address?.addressLocality ?? "";
        const header = [job.title, job.hiringOrganization?.name, where].filter(Boolean).join("\n");
        return tidy(`${header}\n\n${strip(String(job.description))}`);
      }
    } catch {
      /* fall through to plain stripping */
    }
  }
  return tidy(strip(html));
}

function strip(html: string): string {
  return html
    .replace(/<(script|style|noscript|svg|nav|footer|header)[\s\S]*?<\/\1>/gi, " ")
    .replace(/<\/(p|div|li|h[1-6]|tr|section|ul|ol)>|<br\s*\/?>/gi, "\n")
    .replace(/<li[^>]*>/gi, "- ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&(#39|[a-z]+);/gi, (m, e) => ENTITIES[e.toLowerCase()] ?? m)
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n[ \t]+/g, "\n");
}

/** Only public http(s) pages; never the local network. */
export function isSafeUrl(raw: string): URL | null {
  try {
    const url = new URL(raw);
    if (!/^https?:$/.test(url.protocol)) return null;
    const h = url.hostname;
    if (h === "localhost" || h.endsWith(".local") || /^(127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|\[)/.test(h))
      return null;
    return url;
  } catch {
    return null;
  }
}

/**
 * Turn a Google Docs / Sheets / Drive share link into a direct download address.
 * Works only when the file is shared as "Anyone with the link".
 */
export function driveDownloadUrl(raw: string): string | null {
  const url = isSafeUrl(raw);
  if (!url) return null;
  const id = /\/d\/([\w-]{20,})/.exec(url.pathname)?.[1] ?? url.searchParams.get("id");
  if (url.hostname === "docs.google.com" && id) {
    if (url.pathname.startsWith("/document/")) return `https://docs.google.com/document/d/${id}/export?format=txt`;
    if (url.pathname.startsWith("/spreadsheets/")) {
      const gid = /gid=(\d+)/.exec(url.hash + url.search)?.[1];
      return `https://docs.google.com/spreadsheets/d/${id}/export?format=csv${gid ? `&gid=${gid}` : ""}`;
    }
  }
  if (url.hostname === "drive.google.com" && id) return `https://drive.google.com/uc?export=download&id=${id}`;
  return url.toString();
}
