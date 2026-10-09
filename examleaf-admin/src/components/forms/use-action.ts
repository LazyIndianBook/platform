"use client";

// One request at a time for a form or a button (the public site's account/use-action.ts): busy while it runs (a
// second press sends nothing), the ApiError when it fails. A 401 is not shown: the transport is already taking the
// person to sign in and back. A cancelled passkey prompt is not an error.
import { useRef, useState } from "react";

import { ApiError } from "@/lib/api/errors";
import { copy } from "@/lib/copy";

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const running = useRef(false); // set at once, before React re-renders the button as busy

  /** Runs the work; true when it succeeded. */
  async function run(work: () => Promise<unknown>): Promise<boolean> {
    if (running.current) return false;
    running.current = true;
    setBusy(true);
    setError(null);
    try {
      await work();
      return true;
    } catch (caught) {
      if (caught instanceof ApiError) {
        if (caught.status !== 401) setError(caught);
      } else if (!(caught instanceof DOMException && caught.name === "NotAllowedError")) {
        setError(new ApiError(0, "unavailable", copy.errors.unavailable));
      }
      return false;
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  return { run, busy, error, setError };
}

export const fieldError = (error: ApiError | null, name: string) => error?.fields[name] ?? null;
