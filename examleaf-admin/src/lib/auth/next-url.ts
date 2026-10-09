// The intended destination after signing in (?next=): a path on this console only, never another host (open
// redirect), never back to a page that would undo the sign-in. The public site's file with the console's own pages.
const NEVER = ["/sign-in/", "/inactive/", "/no-access/", "/set-up-two-step/"];
const ORIGIN = "https://examleaf.invalid";
// "//" anywhere (a network-path reference, also once dot segments are removed: "/..//host"), a backslash, a "."
// or ".." segment (plain or percent-encoded), "@", whitespace or a control character
const UNSAFE = /\/\/|\\|@|[\s\u0000-\u001f\u007f]|(^|\/)(\.|%2e){1,2}(\/|[?#]|$)/i;

/** A relative path that starts with one "/", with none of UNSAFE, and stays on this origin through the URL parser;
 *  anything else is `fallback`. */
export function safeNext(value: string | string[] | null | undefined, fallback = "/"): string {
  const next = Array.isArray(value) ? value[0] : value;
  if (!next || !next.startsWith("/") || UNSAFE.test(next)) return fallback;
  try {
    const url = new URL(next, ORIGIN);
    const path = url.pathname + url.search + url.hash;
    if (url.origin !== ORIGIN || path.startsWith("//") || new URL(path, ORIGIN).origin !== ORIGIN) return fallback;
    if (NEVER.some((never) => url.pathname.startsWith(never))) return fallback;
    return path;
  } catch {
    return fallback;
  }
}

/** A link to an auth page that keeps the destination: withNext("/account/login/", "/s/PHY-E02/"). */
export function withNext(path: string, next: string | null | undefined): string {
  const safe = safeNext(next, "");
  return safe && safe !== "/" ? `${path}?next=${encodeURIComponent(safe)}` : path;
}
