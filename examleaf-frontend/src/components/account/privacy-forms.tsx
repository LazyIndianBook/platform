"use client";

// Consent and your data (Privacy artboard; Gaps "Data summary and deletion"): the parent's link sent again (POST
// me/parent-consent/: to the contact on record, or a corrected one), Download my data (what the file holds, from
// me/export/summary/, BEFORE the download; then POST me/export/ for the file), Delete my account (POST me/deletion/,
// due in seven days, confirmed by typing the account's email address) and Keep my account (DELETE me/deletion/). The
// export and the deletion ask for the password; an account without one (Google) needs a log-in in this browser in the
// last 5 minutes instead (the API's 403 reauthentication_required says when it is older).
import { CircleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "@/components/ui/toaster";

import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { Alert } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api, personal } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { dateInIndia } from "@/lib/dates";

import { useAction } from "./use-action";

/** A 429 in words: the API's sentence without DRF's "Expected available in N seconds." (the sentence says when
 *  already), or with the minutes to wait when it does not. Never retried by itself. */
export function throttled(error: ApiError | null): ApiError | null {
  if (error?.status !== 429) return error;
  const seconds = Number(/Expected available in (\d+) seconds?/.exec(error.message)?.[1]);
  const said = error.message.replace(/\s*Expected available in \d+ seconds?\.?/, "").trim();
  const wait = seconds ? `Try again in about ${Math.max(1, Math.ceil(seconds / 60))} minutes.` : "Try again later.";
  return new ApiError(429, error.code, /wait|try again/i.test(said) ? said : `${said} ${wait}`, error.fields);
}

export function ParentResendForm({ contact, sms }: { contact: string; sms: boolean }) {
  const { run, busy, error: raw } = useAction();
  const error = throttled(raw);
  const [sent, setSent] = useState<string | null>(null);
  const label = `Parent's or guardian's email${sms ? " or mobile number" : ""}`;
  return (
    <div className="flex max-w-[30rem] flex-col gap-3">
      {sent ? (
        <Alert variant="success">
          <p>{sent}</p>
        </Alert>
      ) : null}
      <ErrorSummary error={error} labels={{ parent_contact: label }} />
      <form
        className="flex flex-col gap-3"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const value = String(new FormData(event.currentTarget).get("parent_contact") ?? "").trim();
          await run(async () => {
            const answer = await personal(api.POST("/api/v1/me/parent-consent/", { body: { parent_contact: value } }));
            setSent(answer.detail);
          });
        }}
      >
        <Field id="parent_contact" label={label} required error={fieldError(error, "parent_contact")}>
          <Input name="parent_contact" autoComplete="off" maxLength={120} defaultValue={contact} />
        </Field>
        <div>
          <Button type="submit" variant="secondary" busy={busy}>
            Send the link again
          </Button>
        </div>
      </form>
    </div>
  );
}

/** "Send the link again" in a notice: to the contact on record at once; the answer (or why not, such as a link sent
 *  minutes ago) beside it. A corrected contact goes through ParentResendForm. */
export function SendParentLinkButton({ contact }: { contact: string }) {
  const { run, busy, error: raw } = useAction();
  const error = throttled(raw);
  const [sent, setSent] = useState<string | null>(null);
  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        busy={busy}
        className="-mx-4 font-bold"
        onClick={() =>
          run(async () => {
            setSent(null);
            const answer = await personal(
              api.POST("/api/v1/me/parent-consent/", { body: { parent_contact: contact } }),
            );
            setSent(answer.detail);
          })
        }
      >
        Send the link again
      </Button>
      <span role="status" className={`order-last basis-full ${error ? "text-destructive" : "font-normal"}`}>
        {error ? <CircleAlert aria-hidden="true" className="mr-1.5 inline size-[18px] align-[-3px]" /> : null}
        {sent ?? error?.message ?? ""}
      </span>
    </>
  );
}

// Asking for the deletion swaps its form for Keep my account, and keeping the account swaps them back, once the page
// comes back from the server: the one that arrives takes the keyboard focus (accessibility review F1).
let swapped = false;
function useFocusOnSwap<T extends HTMLElement>(focus: (element: T) => void) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!swapped || !ref.current) return;
    swapped = false;
    focus(ref.current);
  }, [focus]);
  return ref;
}
const focusButton = (button: HTMLButtonElement) => button.focus();

export function KeepAccountButton() {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const button = useFocusOnSwap(focusButton);
  return (
    <>
      {error ? <p className="font-semibold text-destructive">{error.message}</p> : null}
      <div>
        <Button
          ref={button}
          variant="secondary"
          size="sm"
          busy={busy}
          onClick={async () => {
            if (await run(() => personal(api.DELETE("/api/v1/me/deletion/")))) {
              toast.success("Your account stays. We have cancelled the deletion.");
              swapped = true;
              router.refresh();
            }
          }}
        >
          Keep my account
        </Button>
      </div>
    </>
  );
}

type ExportPart = components["schemas"]["ExportPart"];

/** What to do when the API wants a recent log-in (an account without a password, after 5 minutes). */
function LogInAgain({ error }: { error: ApiError | null }) {
  if (error?.code !== "reauthentication_required") return null;
  return (
    <Alert variant="warning" title="Log in again first">
      <p>
        For your safety this needs a log-in in the last 5 minutes. <Link href="/account/logout/">Log out</Link>, log in
        again with Google or a code by email, then come back to Consent and your data.
      </p>
    </Alert>
  );
}

/** What the file holds, part by part (me/export/summary/), then the download: the password, the file, its link. */
export function DataExport({ hasPassword, summary }: { hasPassword: boolean; summary: ExportPart[] | null }) {
  const { run, busy, error } = useAction();
  const [file, setFile] = useState<string | null>(null);
  useEffect(() => () => (file ? URL.revokeObjectURL(file) : undefined), [file]);

  if (file) {
    return (
      <>
        <p className="m-0">Your file is ready: everything ExamLeaf keeps about you.</p>
        <div>
          <a
            href={file}
            download={`examleaf-my-data-${dateInIndia()}.json`}
            className={buttonVariants({ variant: "primary" })}
          >
            Download the file
          </a>
        </div>
        <p className="m-0 text-[15px] text-muted-foreground">
          The file is JSON: plain text that any text editor opens. What each part is for, and how long we keep it, is in
          the <Link href="/privacy/">privacy notice</Link>.
        </p>
      </>
    );
  }
  return (
    <>
      {summary ? (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse border-t-[1.5px] border-foreground text-[15px]">
            <caption className="sr-only">What the file holds</caption>
            <thead className="sr-only">
              <tr>
                <th scope="col">Part</th>
                <th scope="col">Records</th>
              </tr>
            </thead>
            <tbody>
              {summary.map((part) => (
                <tr key={part.key} className="border-b border-border">
                  <td className="py-2.5 pr-4">{part.label}</td>
                  <td className="py-2.5 text-right font-mono tabular-nums">{part.count || "none"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <ErrorSummary error={error} labels={{ password: "Your password" }} />
      <LogInAgain error={error} />
      <form
        className="flex max-w-[30rem] flex-col gap-3"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const password = String(new FormData(event.currentTarget).get("password") ?? "");
          await run(async () => {
            const data = await personal(api.POST("/api/v1/me/export/", { body: hasPassword ? { password } : {} }));
            setFile(URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })));
          });
        }}
      >
        {hasPassword ? (
          <Field
            id="password"
            label="Your password"
            required
            help="For your safety the file is made only after your password."
            error={fieldError(error, "password")}
          >
            <Input name="password" type="password" autoComplete="current-password" />
          </Field>
        ) : null}
        <div>
          <Button type="submit" variant="secondary" busy={busy}>
            Download all of it (JSON)
          </Button>
        </div>
      </form>
    </>
  );
}

/** Delete my account: "Delete…" opens the confirmation, which asks for the account's email address typed out (its
 *  button stays disabled until it matches) and the password when the account has one (the API asks for it). */
export function DeleteAccountForm({ hasPassword, email }: { hasPassword: boolean; email: string }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [open, setOpen] = useState(false);
  const [closed, setClosed] = useState(false); // closed by the student: the focus goes back to Delete…
  const [typed, setTyped] = useState("");
  const opener = useFocusOnSwap(focusButton);
  const matches = typed.trim().toLowerCase() === email.trim().toLowerCase();
  // the API's "password" is this form's delete_password box (Download my data has the other password box)
  const shown =
    error &&
    new ApiError(
      error.status,
      error.code,
      error.message,
      error.fields.password ? { delete_password: error.fields.password } : {},
    );

  if (!open) {
    return (
      <div>
        <Button
          ref={opener}
          variant="destructive"
          autoFocus={closed}
          className="max-nav:w-full"
          onClick={() => {
            setOpen(true);
            setClosed(false);
          }}
        >
          Delete my account…
        </Button>
      </div>
    );
  }
  return (
    <form
      aria-labelledby="delete-title"
      className="flex max-w-[36rem] flex-col gap-3 border-2 border-destructive bg-card p-4 [&_p]:m-0"
      noValidate
      onSubmit={async (event) => {
        event.preventDefault();
        if (!matches) return;
        const password = String(new FormData(event.currentTarget).get("password") ?? "");
        const body = hasPassword ? { password } : {};
        if (await run(() => personal(api.POST("/api/v1/me/deletion/", { body })))) {
          toast.success("Your account will be deleted in 7 days. Until then you can keep it.");
          swapped = true;
          router.refresh();
        }
      }}
    >
      <h3 id="delete-title" className="m-0 text-xl leading-tight">
        Delete your account?
      </h3>
      <p className="text-sm leading-relaxed text-ink/85">
        Your account, your record, your course progress and your details are deleted seven days after you ask; until
        then you can log in and keep it. Orders and their invoices stay, as tax law requires. Type your email address to
        confirm.
      </p>
      <ErrorSummary error={shown} labels={{ delete_password: "Your password" }} />
      <LogInAgain error={error} />
      <Field id="confirm_email" label="Your email address">
        <Input
          name="confirm_email"
          type="email"
          inputMode="email"
          autoComplete="off"
          spellCheck={false}
          autoFocus
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
      </Field>
      {hasPassword ? (
        <Field id="delete_password" label="Your password" required error={fieldError(shown, "delete_password")}>
          <Input name="password" type="password" autoComplete="current-password" />
        </Field>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2.5">
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            setOpen(false);
            setClosed(true);
            setTyped("");
          }}
        >
          Keep my account
        </Button>
        <Button type="submit" variant="destructive" busy={busy} disabled={!matches}>
          Delete it
        </Button>
      </div>
    </form>
  );
}
