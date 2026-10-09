// The browser's side of the API boundary, as on the public site (examleaf-frontend/src/lib/api/client.ts): same origin
// (Caddy sends /api/ and /_allauth/ to Django), the session cookie, and the CSRF token from the csrftoken cookie on every
// unsafe method. What the staff API's answers make the browser do lives here too: a 401 sends the person to sign in
// and back (the draft stays in sessionStorage), a refusal by role or scope asks the shell to read the manifest again,
// and "confirm it's you" opens the dialog that the transport waits for (reauthentication, then the call once more).
import type { Flow } from "@/lib/auth/headless";
import { withNext } from "@/lib/auth/next-url";

export function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie
    .split("; ")
    .find((pair) => pair.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

/** Before a first change: Django's CSRF cookie, which allauth's config answer (public, 200) sets. */
export async function ensureCsrfCookie() {
  if (typeof document === "undefined" || readCookie("csrftoken")) return;
  await fetch(`${process.env.NEXT_PUBLIC_API_BASE ?? ""}/_allauth/browser/v1/config`, {
    credentials: "same-origin",
    cache: "no-store",
  }).catch(() => undefined);
}

export type SignInReason = "expired" | "idle" | "signed-out";

/** The sign-in page with a destination and why the person is there. */
export function signInHref(next?: string | null, reason?: SignInReason): string {
  const href = withNext("/sign-in/", next ?? null);
  return reason ? `${href}${href.includes("?") ? "&" : "?"}reason=${reason}` : href;
}

/** Why a 401 ended the session, in the sign-in page's words: the backend's own idle limit (`session_idle`), or not. */
export const endedBy = (code: string): SignInReason => (code === "session_idle" ? "idle" : "expired");

/** The page the person is on, for `next`. */
export function here(): string {
  return typeof window === "undefined" ? "/" : window.location.pathname + window.location.search;
}

/** The session ended: off to sign in, then back here. Drafts stay in sessionStorage (useDraftForm). */
export function sessionEnded(reason: SignInReason = "expired") {
  if (typeof window === "undefined") return;
  window.location.assign(signInHref(here(), reason));
}

export const MANIFEST_STALE = "examleaf-admin:manifest-stale";

/** A refusal by role or scope: the shell reads the manifest again (router.refresh in ManifestProvider). */
export function manifestStale() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(MANIFEST_STALE));
}

type Waiting = { flows: Flow[]; done: Promise<boolean>; resolve: (confirmed: boolean) => void };
let waiting: Waiting | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());

/** "Confirm it's you": the transport asks, the dialog (components/shell/reauth-dialog.tsx) answers. Calls that ask
 *  while the dialog is open share its answer; with no dialog on the page the answer is no at once. */
export const reauth = {
  request(flows: Flow[] = []): Promise<boolean> {
    if (waiting) return waiting.done;
    if (!listeners.size) return Promise.resolve(false);
    let resolve: (confirmed: boolean) => void = () => undefined;
    const done = new Promise<boolean>((settle) => (resolve = settle));
    waiting = { flows, done, resolve };
    notify();
    return done;
  },
  current(): Flow[] | null {
    return waiting?.flows ?? null;
  },
  settle(confirmed: boolean) {
    const current = waiting;
    waiting = null;
    current?.resolve(confirmed);
    notify();
  },
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
};
