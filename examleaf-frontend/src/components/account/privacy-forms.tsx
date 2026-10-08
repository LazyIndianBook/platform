"use client";

// Consent and your data (Django's my_account.html #consent and #data, account_data.html, account_delete.html): the
// parent's link sent again (POST me/parent-consent/), Download my data (POST me/export/ with the password: what the
// file holds, part by part, then the file itself), Delete my account (POST me/deletion/, due in seven days) and Keep
// my account (DELETE me/deletion/).
import { Download, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

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

export function KeepAccountButton() {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <>
      {error ? <p className="font-semibold text-destructive">{error.message}</p> : null}
      <div>
        <Button
          variant="secondary"
          size="sm"
          busy={busy}
          onClick={async () => {
            if (await run(() => personal(api.DELETE("/api/v1/me/deletion/")))) {
              toast.success("Your account stays. We have cancelled the deletion.");
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

// the parts of the file in words, as Django's DATA_PARTS (accounts/views.py) shows them before the download
const PARTS: [string, string][] = [
  ["profile", "Your details: name, email address, class, board, district, date of birth, a parent's details"],
  ["email_addresses", "Email addresses"],
  ["passkeys_and_authenticators", "Passkeys and authenticator apps"],
  ["google_accounts", "Google accounts connected"],
  ["teacher_profile", "Teacher access asked for"],
  ["attempts", "Marks saved in My record"],
  ["answer_sheets", "Answer sheets uploaded"],
  ["consents", "Consents given"],
  ["deletion_requests", "Requests to delete the account"],
  ["addresses", "Saved addresses"],
  ["cart", "Cart"],
  ["orders", "Orders, with their payments, refunds and invoices"],
  ["reviews", "Reviews"],
  ["quote_requests", "School and bulk quotation requests"],
  ["stock_alerts", "Requests to be emailed when a book is back"],
  ["learning", "The revision course: settings, codes, progress, quiz answers, devices"],
  ["sms", "SMS sent to you"],
  ["email_suppressed", "Emails stopped after a bounce"],
];

/** The records in a part (Django's how_many): a list's length, the lists' total of a part made of lists, else 1 or 0. */
export function howMany(value: unknown): number {
  if (Array.isArray(value)) return value.length;
  if (!value || typeof value !== "object") return value ? 1 : 0;
  const items = Object.values(value);
  if (items.some(Array.isArray)) return items.reduce((total: number, item) => total + howMany(item), 0);
  return items.length ? 1 : 0;
}

export function DataExport({ hasPassword }: { hasPassword: boolean }) {
  const { run, busy, error } = useAction();
  const [file, setFile] = useState<{ url: string; parts: [string, number][] } | null>(null);
  useEffect(() => () => (file ? URL.revokeObjectURL(file.url) : undefined), [file]);

  if (!hasPassword) {
    return (
      <p>
        Your account has no password yet (you log in with Google or a code). The file is handed out only after your
        password: <Link href="/account/security/#change-password">choose one</Link> first.
      </p>
    );
  }
  if (file) {
    return (
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
            {file.parts.map(([label, count]) => (
              <tr key={label}>
                <TableCell>{label}</TableCell>
                <TableCell numeric>{count || "none"}</TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
        <div>
          <a
            href={file.url}
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
      <ErrorSummary error={error} labels={{ password: "Your password" }} />
      <form
        className="flex max-w-[30rem] flex-col gap-3"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const password = String(new FormData(event.currentTarget).get("password") ?? "");
          await run(async () => {
            const data = (await personal(api.POST("/api/v1/me/export/", { body: { password } }))) as Record<
              string,
              unknown
            >;
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
            setFile({
              url: URL.createObjectURL(blob),
              parts: PARTS.map(([key, label]) => [label, howMany(data[key])]),
            });
          });
        }}
      >
        <Field
          id="password"
          label="Your password"
          required
          help="For your safety the file is made only after your password."
          error={fieldError(error, "password")}
        >
          <Input name="password" type="password" autoComplete="current-password" />
        </Field>
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
  if (!hasPassword) {
    return (
      <p>
        To delete your account, <Link href="/account/security/#change-password">choose a password</Link> first: we ask
        for it before an account is deleted.
      </p>
    );
  }
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
      <form
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
          if (await run(() => personal(api.POST("/api/v1/me/deletion/", { body: { password } })))) {
            toast.success("Your account will be deleted in 7 days. Until then you can keep it.");
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
        <Field id="delete_password" label="Your password" required error={fieldError(shown, "delete_password")}>
          <Input name="password" type="password" autoComplete="current-password" />
        </Field>
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
