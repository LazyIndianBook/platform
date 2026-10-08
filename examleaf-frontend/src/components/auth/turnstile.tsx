"use client";

// Cloudflare Turnstile where a form shows it (only when the server's config gives a site key): the widget's code
// (turnstile-widget.tsx) and Cloudflare's script load with that form, never with the page (Lighthouse review L2).
// useTurnstile is the form's side: the token for the request, and `waiting` until it comes, while the form's button
// says CHECKING and sends nothing (a send before the token would be refused). A check without a token after 10 s
// (its script blocked or down) lets the button send without one, so the server's own rules answer, and offers to try
// again. A token works once: after a refused send (resetKey) a new check runs for a new one.
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

const Widget = dynamic(() => import("./turnstile-widget").then((module) => module.Turnstile), {
  ssr: false,
  loading: () => <div className="min-h-[65px]" />,
});

export const CHECKING = "Checking that you are not a robot…";
const PATIENCE = 10_000;

/** `siteKey` while the form shows the check (else null); `resetKey`, the form's error. */
export function useTurnstile(siteKey: string | null, resetKey?: unknown) {
  const [token, setToken] = useState("");
  const [round, setRound] = useState(0); // a new widget each time the check is shown, refused or tried again
  const [lapsed, setLapsed] = useState(-1); // the round that waited PATIENCE without a token
  const [seen, setSeen] = useState({ siteKey, resetKey });
  if (siteKey !== seen.siteKey || resetKey !== seen.resetKey) {
    setSeen({ siteKey, resetKey });
    if (siteKey !== seen.siteKey || resetKey) {
      setRound(round + 1);
      setToken("");
    }
  }

  useEffect(() => {
    if (!siteKey || token) return;
    const timer = setTimeout(() => setLapsed(round), PATIENCE);
    return () => clearTimeout(timer);
  }, [siteKey, token, round]);

  const late = !token && lapsed === round;
  return {
    token,
    waiting: Boolean(siteKey) && !token && !late,
    widget: siteKey ? (
      <div>
        <Widget key={round} siteKey={siteKey} onToken={setToken} round={round} />
        {late ? (
          <p className="m-0 text-[15px] text-muted-foreground">
            The check did not finish.{" "}
            <button
              type="button"
              className="inline-flex min-h-11 cursor-pointer items-center font-semibold text-primary underline underline-offset-3"
              onClick={() => setRound(round + 1)}
            >
              Try it again
            </button>
          </p>
        ) : null}
      </div>
    ) : null,
  };
}
