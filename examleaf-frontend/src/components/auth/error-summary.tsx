"use client";

// After a failed submit: one alert at the top of the form (role="alert"), each problem a link to its field; focus
// moves to it, so a long form scrolls back to what needs fixing. A save refused while a parent's consent is awaited
// (code consent_pending) also offers the way on: the link to the parent again.
// Two answers get the words of the "429 and 403" board:
// - too many tries (`retryIn`, the minutes the form's limit lasts, switches it on: allauth.headless answers a 429
//   with no Retry-After, and a code asked for too often as a 400 with code too_many_login_attempts, in library words):
//   it says when to try again, from the clock of the visitor's device. Nothing is sent again by itself;
// - a 403 with no JSON body is Django's own "form could not be sent" page (the CSRF check): the form timed out.
import Link from "next/link";
import { useEffect, useRef } from "react";

import { Alert } from "@/components/ui/alert";
import type { ApiError } from "@/lib/api/errors";

const TOO_MANY = "too_many_login_attempts";

/** The clock time `minutes` from now, 24-hour: "18:24". */
export function timeAfter(minutes: number): string {
  return new Date(Date.now() + minutes * 60_000).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}

export function ErrorSummary({
  error,
  labels,
  retryIn,
  limited = "codes can be asked for and typed",
}: {
  error: ApiError | null;
  labels?: Record<string, string>;
  /** Minutes the form's limit lasts; given, a 429 is worded as the board does ("limited": what the limit is on). */
  retryIn?: number;
  limited?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) box.current?.focus();
  }, [error]);
  if (!error) return null;

  const throttled = retryIn !== undefined && (error.status === 429 || error.code === TOO_MANY);
  const timedOut = error.status === 403 && error.body === null;
  if (throttled || timedOut) {
    return (
      <div ref={box} tabIndex={-1} className="outline-none">
        <Alert variant="error" role="alert" title={throttled ? "Too many tries" : "The form timed out"}>
          <p>
            {throttled
              ? `To keep accounts safe, we limit how often ${limited}. You can try again after ${timeAfter(retryIn)}.`
              : "For your safety, forms expire. Go back, reload the page and send it again."}
          </p>
        </Alert>
      </div>
    );
  }

  const fields = Object.entries(error.fields);
  const fieldMessages = new Set(fields.flatMap(([, messages]) => messages));
  return (
    <div ref={box} tabIndex={-1} className="outline-none">
      <Alert variant="error" role="alert" title="There is a problem">
        {!fieldMessages.has(error.message) ? <p>{error.message}</p> : null}
        {error.code === "consent_pending" ? (
          <p>
            Until they confirm, your account can read but not save.{" "}
            <Link href="/account/privacy/">Send them the link again</Link>.
          </p>
        ) : null}
        {fields.length ? (
          <ul className="m-0 pl-5">
            {fields.map(([name, messages]) => (
              <li key={name}>
                <a href={`#${name}`} className="font-semibold text-destructive">
                  {labels?.[name] ? `${labels[name]}: ` : ""}
                  {messages.join(" ")}
                </a>
              </li>
            ))}
          </ul>
        ) : null}
      </Alert>
    </div>
  );
}
