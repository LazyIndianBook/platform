"use client";

// While a member of ExamLeaf's support is signed in as this customer (the `impersonation` of allauth's session user,
// which the root layout reads on every page): a band above every page, in the site's information colours (news, not an error), that cannot be
// dismissed, saying who and until when, with End (DELETE account/impersonate/, then the log-in page); and the actions
// such a session may not take (payments, addresses, the password, email and mobile number, two-step log-in and
// passkeys, consent, the data download and deletion) drawn disabled, with the reason. The API refuses them anyway
// (403 impersonating): this only says so before anyone tries. The token from the staff console's link is accepted on
// /account/impersonate/ (AcceptImpersonation).
import { Info } from "lucide-react";
import Link from "next/link";
import { createContext, useContext, useEffect, useRef, useState } from "react";

import { AuthTitle, Lead } from "@/components/auth/auth-card";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { AuthUser } from "@/lib/auth/headless";
import { ensureCsrfCookie, readCookie } from "@/lib/api/client";
import { formatTime } from "@/lib/dates";

/** While a member of staff is signed in as this customer: when it ends and who (their address, masked). */
export type Impersonation = NonNullable<AuthUser["impersonation"]>;

const ImpersonationContext = createContext<Impersonation | null>(null);

export function ImpersonationProvider({ value, children }: { value: Impersonation | null; children: React.ReactNode }) {
  return <ImpersonationContext.Provider value={value}>{children}</ImpersonationContext.Provider>;
}

export const useImpersonation = () => useContext(ImpersonationContext);

/** account/impersonate/, the website's side of a staff member's 15-minute token: POST accepts it, DELETE ends it. */
async function impersonation(method: "POST" | "DELETE", body?: { token: string }): Promise<Response> {
  await ensureCsrfCookie();
  return fetch(`${process.env.NEXT_PUBLIC_API_BASE ?? ""}/api/v1/account/impersonate/`, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "X-CSRFToken": readCookie("csrftoken") ?? "",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}

export function ImpersonationBanner() {
  const current = useImpersonation();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  if (!current) return null;
  return (
    <section aria-label="A support colleague is viewing this account" className="border-b border-info-line bg-info-bg">
      <div className="mx-auto flex w-full max-w-[calc(var(--container)+var(--margin-col)+var(--marks-col))] flex-wrap items-center gap-x-4 gap-y-2 px-(--gutter) py-2.5 nav:px-10">
        <Info aria-hidden="true" className="icon-filled size-6 shrink-0 text-info-fg" />
        <p className="m-0 min-w-0 flex-1 text-[15px] leading-snug text-foreground">
          A support colleague is viewing this account as <strong>{current.by}</strong> until{" "}
          <time dateTime={current.until}>{formatTime(current.until)}</time>.
          {failed ? <span className="block">That did not work: try End again.</span> : null}
        </p>
        <Button
          variant="secondary"
          size="sm"
          busy={busy}
          onClick={async () => {
            setBusy(true);
            setFailed(false);
            try {
              const answer = await impersonation("DELETE");
              // gone already (expired, ended elsewhere) is ended too
              if (!answer.ok && answer.status !== 401 && answer.status !== 404) throw new Error(String(answer.status));
              // a full load: the session changed, and with it the layout (its banner, the header)
              // eslint-disable-next-line @next/next/no-location-assign-relative-destination
              window.location.assign("/account/login/");
            } catch {
              setFailed(true);
              setBusy(false);
            }
          }}
        >
          End
        </Button>
      </div>
    </section>
  );
}

/** An action such a session may not take: drawn disabled (a fieldset disables every control in it), with why. */
export function WhileImpersonated({ what, children }: { what: string; children: React.ReactNode }) {
  if (!useImpersonation()) return children;
  return (
    <div className="flex flex-col gap-3">
      <p className="m-0 flex items-start gap-2 text-[15px] text-muted-foreground">
        <Info aria-hidden="true" className="icon-filled mt-0.5 size-5 shrink-0 text-info-fg" />
        <span>{what} stays closed while a support colleague is viewing this account.</span>
      </p>
      <fieldset disabled className="m-0 min-w-0 border-0 p-0">
        {children}
      </fieldset>
    </div>
  );
}

type Outcome = { state: "working" | "refused" | "unavailable"; words: string };

/** /account/impersonate/?token=…: the token is sent once (POST account/impersonate/), then the account opens; a token
 *  that is not valid, has expired or was used already gets an honest page with the API's words, and nothing else
 *  happens. */
export function AcceptImpersonation({ token }: { token: string }) {
  const [outcome, setOutcome] = useState<Outcome>({ state: "working", words: "" });
  const sent = useRef(false); // once, also when a development render runs the effect twice
  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    impersonation("POST", { token })
      .then(async (answer) => {
        // a full load, as above: the session is the customer's now
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        if (answer.ok) return window.location.assign("/account/");
        const body = (await answer.json().catch(() => null)) as Record<string, unknown> | null;
        const words = [body?.detail, ...(Array.isArray(body?.token) ? body.token : [])].find(
          (value): value is string => typeof value === "string",
        );
        setOutcome({ state: answer.status >= 500 ? "unavailable" : "refused", words: words ?? "" });
      })
      .catch(() => setOutcome({ state: "unavailable", words: "" }));
  }, [token]);

  if (outcome.state === "working") {
    return (
      <>
        <AuthTitle>Opening the account</AuthTitle>
        <Lead aria-live="polite">One moment: the link is being checked.</Lead>
      </>
    );
  }
  return (
    <>
      <AuthTitle>
        {outcome.state === "refused" ? "This link does not open the account" : "ExamLeaf cannot be reached"}
      </AuthTitle>
      <Lead>
        {outcome.state === "refused"
          ? "It is not a valid link, it has expired (it lasts 15 minutes), or it was used already. Ask for a new one from the staff console."
          : "Nothing was opened. Try the link again in a minute."}
      </Lead>
      {outcome.words ? (
        <Alert variant="info" title="What the server said">
          <p>{outcome.words}</p>
        </Alert>
      ) : null}
      <Link href="/" className="inline-flex min-h-11 items-center font-semibold">
        Go to the home page
      </Link>
    </>
  );
}
