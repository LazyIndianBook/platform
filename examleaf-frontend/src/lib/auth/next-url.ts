// The intended destination after a log-in (?next=): a path on this site only, never another host (open redirect),
// never back to a page that would undo the log-in.
const NEVER = ["/account/logout/", "/account/login/", "/account/signup/"];

export function safeNext(value: string | string[] | null | undefined, fallback = "/"): string {
  const next = Array.isArray(value) ? value[0] : value;
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return fallback;
  try {
    // a path that parses to another origin (e.g. "/\t/evil.example") is refused too
    const url = new URL(next, "https://examleaf.invalid");
    if (url.origin !== "https://examleaf.invalid") return fallback;
    if (NEVER.some((path) => url.pathname.startsWith(path))) return fallback;
    return url.pathname + url.search + url.hash;
  } catch {
    return fallback;
  }
}

/** A link to an auth page that keeps the destination: withNext("/account/login/", "/s/PHY-E02/"). */
export function withNext(path: string, next: string | null | undefined): string {
  const safe = safeNext(next, "");
  return safe && safe !== "/" ? `${path}?next=${encodeURIComponent(safe)}` : path;
}
