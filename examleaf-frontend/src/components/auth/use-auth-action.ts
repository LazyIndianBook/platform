"use client";

// One submit at a time for the auth forms: busy while it runs (and while a signed-in visitor's next page loads, so a
// press meanwhile sends nothing), the ApiError when it fails (fields and message), then whatever comes next for the
// answer (nextRoute: the destination, or the pending step's page).
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { ApiError } from "@/lib/api/errors";
import { type AuthResult, nextRoute } from "@/lib/auth/headless";

export function useAuthAction(next: string | null) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const running = useRef(false); // set at once, before React re-renders the button as busy

  /** Runs the call; returns its answer when the page should handle it itself (no route to go to). */
  async function run(call: () => Promise<AuthResult>): Promise<AuthResult | null> {
    if (running.current) return null;
    running.current = true;
    let leaving = false;
    setBusy(true);
    setError(null);
    try {
      const result = await call();
      const route = nextRoute(result, next);
      if (route) {
        // a full load once signed in: the header, the cart and every server component read the new session
        leaving = result.authenticated;
        if (result.authenticated) window.location.assign(route);
        else router.push(route);
        return null;
      }
      return result;
    } catch (caught) {
      if (caught instanceof ApiError) setError(caught);
      else if (caught instanceof DOMException && caught.name === "NotAllowedError")
        setError(null); // prompt cancelled
      else setError(new ApiError(0, "unavailable", "That did not work. Please try again."));
      return null;
    } finally {
      running.current = false;
      if (!leaving) setBusy(false);
    }
  }

  return { run, busy, error, setError };
}

export const fieldError = (error: ApiError | null, name: string) => error?.fields[name] ?? null;
