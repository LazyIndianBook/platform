"use client";

// After a failed submit: one alert at the top of the form (role="alert"), each problem a link to its field; focus
// moves to it, so a long form scrolls back to what needs fixing.
import { useEffect, useRef } from "react";

import { Alert } from "@/components/ui/alert";
import type { ApiError } from "@/lib/api/errors";

export function ErrorSummary({ error, labels }: { error: ApiError | null; labels?: Record<string, string> }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) box.current?.focus();
  }, [error]);
  if (!error) return null;
  const fields = Object.entries(error.fields);
  const fieldMessages = new Set(fields.flatMap(([, messages]) => messages));
  return (
    <div ref={box} tabIndex={-1} className="outline-none">
      <Alert variant="error" role="alert" title="There is a problem">
        {!fieldMessages.has(error.message) ? <p>{error.message}</p> : null}
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
