// What a student typed, kept in this tab while it is sent: a session that ended (401) takes them to log in and back
// (sessionMiddleware), and the form puts it back (marks-form.tsx's pattern). Storage off (private mode): nothing kept.
export function readDraft<T>(key: string): T | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

/** null forgets it (after the server took it). */
export function writeDraft(key: string, value: unknown) {
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: nothing to keep */
  }
}
