"use client";

// Consent and your data (Django's my_account.html #consent and #data, account_data.html, account_delete.html): the
// parent's link sent again (POST me/parent-consent/), Download my data (what the file holds, from me/export/summary/,
// then POST me/export/ for the file), Delete my account (POST me/deletion/, due in seven days) and Keep my account
// (DELETE me/deletion/). The export and the deletion ask for the password; an account without one (Google) needs a
// log-in in this browser in the last 5 minutes instead (the API's 403 reauthentication_required says when it is older).
import { Download, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "@/components/ui/toaster";

import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { Alert } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/choice";
import { Field, FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { api, personal } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { dateInIndia } from "@/lib/dates";

import { useAction } from "./use-action";

export function ParentResendForm({ contact, sms }: { contact: string; sms: boolean }) {
  const { run, busy, error } = useAction();
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
const focusFirstField = (form: HTMLFormElement) => form.querySelector("input")?.focus();

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

export function DataExport({ hasPassword, summary }: { hasPassword: boolean; summary: ExportPart[] | null }) {
  const { run, busy, error } = useAction();
  const [file, setFile] = useState<string | null>(null);
  useEffect(() => () => (file ? URL.revokeObjectURL(file) : undefined), [file]);

  if (file) {
    return (
      <>
        <p>Your file is ready: everything ExamLeaf keeps about you.</p>
        <div>
          <a
            href={file}
            download={`examleaf-my-data-${dateInIndia()}.json`}
            className={buttonVariants({ variant: "primary" })}
          >
            <Download aria-hidden="true" />
            <span>Download the file</span>
          </a>
        </div>
        <p className="text-[15px] text-muted-foreground">
          The file is JSON: plain text that any text editor opens. What each part is for, and how long we keep it, is in
          the <Link href="/privacy/">privacy notice</Link>.
        </p>
      </>
    );
  }
  return (
    <>
      {summary ? (
        <>
          <p>Everything ExamLeaf keeps about you is in one file. This is what it holds today.</p>
          <Table caption="What the file holds">
            <thead>
              <tr>
                <TableHead>Part</TableHead>
                <TableHead numeric>Records</TableHead>
              </tr>
            </thead>
            <tbody>
              {summary.map((part) => (
                <tr key={part.key}>
                  <TableCell>{part.label}</TableCell>
                  <TableCell numeric>{part.count || "none"}</TableCell>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
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
            <Download aria-hidden="true" />
            <span>Download my data</span>
          </Button>
        </div>
      </form>
    </>
  );
}

const CONFIRM =
  "I understand that my account, my record and my details will be deleted 7 days from now, unless I cancel before then.";

export function DeleteAccountForm({ hasPassword }: { hasPassword: boolean }) {
  const router = useRouter();
  const { run, busy, error, setError } = useAction();
  const swappedIn = useFocusOnSwap(focusFirstField);
  // the API's "password" is this form's delete_password box (Download my data has the other password box)
  const shown =
    error &&
    new ApiError(error.status, error.code, error.message, {
      ...(error.fields.password ? { delete_password: error.fields.password } : {}),
      ...(error.fields.confirm ? { confirm: error.fields.confirm } : {}),
    });
  const unticked = fieldError(shown, "confirm");
  return (
    <>
      <ErrorSummary error={shown} labels={{ delete_password: "Your password", confirm: "Confirmation" }} />
      <LogInAgain error={error} />
      <form
        ref={swappedIn}
        className="flex max-w-[34rem] flex-col gap-3"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          if (!form.get("confirm")) {
            const message = "Tick the box to confirm.";
            setError(new ApiError(400, "invalid", message, { confirm: [message] }));
            return;
          }
          const password = String(form.get("password") ?? "");
          const body = hasPassword ? { password } : {};
          if (await run(() => personal(api.POST("/api/v1/me/deletion/", { body })))) {
            toast.success("Your account will be deleted in 7 days. Until then you can keep it.");
            swapped = true;
            router.refresh();
          }
        }}
      >
        <div className="flex flex-col gap-1.5">
          <Checkbox
            id="confirm"
            name="confirm"
            value="yes"
            aria-invalid={unticked ? true : undefined}
            aria-describedby={unticked ? "confirm-error" : undefined}
          >
            {CONFIRM}
          </Checkbox>
          {unticked ? <FieldError id="confirm-error">{unticked.join(" ")}</FieldError> : null}
        </div>
        {hasPassword ? (
          <Field id="delete_password" label="Your password" required error={fieldError(shown, "delete_password")}>
            <Input name="password" type="password" autoComplete="current-password" />
          </Field>
        ) : null}
        <div>
          <Button type="submit" variant="destructive" busy={busy}>
            <Trash2 aria-hidden="true" />
            <span>Delete my account</span>
          </Button>
        </div>
      </form>
    </>
  );
}
