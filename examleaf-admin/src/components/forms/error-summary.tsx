"use client";

// After a failed submit: one box at the top of the form, which takes the focus (so a long form scrolls back to it),
// as the public site's components/auth/error-summary.tsx, with the staff API's answers worded:
//   approval_required  the change request that was made, and the way to it (not an error: the outcome)
//   429                when to try again (Retry-After, from this device's clock)
//   409                someone else changed it: Reload (the draft stays)
//   reauth_required    the "confirm it's you" dialog was closed: nothing changed
//   403 without JSON   Django's own CSRF page: the form timed out
//   anything else      the API's words, each field's problem a link to its field
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { ApprovalNotice } from "@/components/data/approval-notice";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { type ApiError, errorText } from "@/lib/api/errors";
import { copy } from "@/lib/copy";

export function ErrorSummary({
  error,
  labels,
  idPrefix = "",
}: {
  error: ApiError | null;
  labels?: Record<string, string>;
  /** The form's field ids are `${idPrefix}${name}`. */
  idPrefix?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const router = useRouter();
  useEffect(() => {
    if (error) box.current?.focus();
  }, [error]);
  if (!error) return null;

  const frame = (children: React.ReactNode) => (
    <div ref={box} tabIndex={-1} className="outline-none">
      {children}
    </div>
  );

  if (error.code === "approval_required") return frame(<ApprovalNotice changeRequestId={error.changeRequestId} />);

  if (error.status === 429) {
    return frame(
      <Alert variant="error" role="alert" title={copy.problem.throttledTitle}>
        <p>{errorText(error)}</p>
      </Alert>,
    );
  }

  if (error.status === 409) {
    return frame(
      <Alert variant="warning" role="alert" title={copy.errors.problem}>
        <p>{error.message || copy.errors.conflict}</p>
        <p>{copy.errors.conflictHint}</p>
        <p>
          <Button variant="secondary" size="sm" onClick={() => router.refresh()}>
            {copy.common.reload}
          </Button>
        </p>
      </Alert>,
    );
  }

  if (error.code === "reauth_required") {
    return frame(
      <Alert variant="warning" role="alert" title={copy.auth.confirmTitle}>
        <p>{copy.errors.reauthCancelled}</p>
      </Alert>,
    );
  }

  if (error.status === 403 && error.body === null) {
    return frame(
      <Alert variant="error" role="alert" title={copy.errors.problem}>
        <p>{copy.errors.timedOut}</p>
      </Alert>,
    );
  }

  const fields = Object.entries(error.fields);
  const fieldMessages = new Set(fields.flatMap(([, messages]) => messages));
  return frame(
    <Alert variant="error" role="alert" title={copy.errors.problem}>
      {!fieldMessages.has(error.message) ? <p>{error.message}</p> : null}
      {fields.length ? (
        <ul className="m-0 pl-5">
          {fields.map(([name, messages]) => (
            <li key={name}>
              <a href={`#${idPrefix}${name}`} className="font-semibold text-destructive">
                {labels?.[name] ? `${labels[name]}: ` : ""}
                {messages.join(" ")}
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </Alert>,
  );
}
