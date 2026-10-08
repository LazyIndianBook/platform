"use client";

// One request at a time for the account forms: busy while it runs, the ApiError when it fails (its fields go beside
// their boxes, its message to the summary). A 401 is not shown: personal() and signedIn() are already taking the
// visitor to log in (or to type the password again) and back. A cancelled passkey prompt is not an error.
import { useState } from "react";

import { ApiError } from "@/lib/api/errors";

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  /** Runs the work; true when it succeeded. */
  async function run(work: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await work();
      return true;
    } catch (caught) {
      if (caught instanceof ApiError) {
        if (caught.status !== 401) setError(caught);
      } else if (caught instanceof DOMException && caught.name === "NotSupportedError") {
        setError(new ApiError(0, "unsupported", "This browser cannot make passkeys. Try your phone's browser."));
      } else if (!(caught instanceof DOMException && caught.name === "NotAllowedError")) {
        setError(new ApiError(0, "unavailable", "That did not work. Please try again."));
      }
      return false;
    } finally {
      setBusy(false);
    }
  }

  return { run, busy, error, setError };
}
