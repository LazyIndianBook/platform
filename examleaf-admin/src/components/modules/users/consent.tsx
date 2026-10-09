"use client";

// A student under 18's parent consent, on the record and in the list of those waiting: how it stands and how it was
// given, the link's life (what went, when it stops working, how many today of the day's limit), and what staff do
// about it: send the link again (a text only from 08:00 to 21:00), or record the consent by hand, with how it was
// checked, where the evidence is and why (POST users/{id}/consent/verify/: high risk, so it asks to confirm it's you;
// the API refuses it twice, for an adult, and while a deletion waits for the parent). The evidence is a reference, never
// the document and never a contact. Each is drawn when the manifest allows it; the API decides and records it.
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Facts } from "@/components/data/record-page";
import { StatusChip } from "@/components/data/status-chip";
import { fieldError, useAction } from "@/components/forms/use-action";
import { FormDialog, formValue } from "@/components/modules/settings/form-dialog";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import { errorText } from "@/lib/api/errors";
import {
  type ConsentMethod,
  type CustomerDetail,
  type CustomerParentLink,
  userAction,
  verifyConsent,
} from "@/lib/api/staff";
import { copy, humanize, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

const METHODS: ConsentMethod[] = ["staff_manual", "adult_account", "digilocker"];
const text = (value: unknown) => (typeof value === "string" ? value : "");

/** Whether a consent can be recorded by hand for this account: a student under 18 whose parent has not confirmed, not
 *  erased and not leaving (a deletion waits for the parent's word on the data request instead). */
export function verifiable(user: Pick<CustomerDetail, "under_18" | "consent" | "status">): boolean {
  return user.under_18 && user.consent !== "verified" && !["erased", "pending_deletion"].includes(user.status);
}

/** The link's life in one phrase: when it stops working, when it did, or that none went. */
export function linkLife(link: Pick<CustomerParentLink, "sent" | "expires_at" | "expired">): string {
  const words = copy.customers.consent;
  if (!link.sent || !link.expires_at) return words.linkNone;
  return link.expired
    ? words.linkEnded(formatDateTime(link.expires_at))
    : words.linkUntil(formatDateTime(link.expires_at));
}

/** A student's consent as facts: the state, how it was given, and the link's count, life and day's use. */
export function ConsentFacts({ user }: { user: CustomerDetail }) {
  const words = copy.customers.consent;
  const link = user.parent_link;
  return (
    <Facts
      items={[
        { label: copy.users.consent, value: labelOf(copy.users.consentStates, user.consent) },
        ...(user.consent === "verified" && user.consent_method
          ? [{ label: words.how, value: labelOf(copy.customers.methods, user.consent_method) }]
          : []),
        ...(link && user.consent !== "verified"
          ? [
              {
                label: words.linksSent,
                value: words.linksValue(link.sent, link.last_at ? formatDate(link.last_at) : ""),
              },
              { label: words.linkLife, value: linkLife(link) },
              { label: words.today, value: words.todayValue(link.today, link.daily_limit) },
            ]
          : []),
      ]}
    />
  );
}

/** The parent's link again: a plain button, the API's refusal (a text out of hours, the day's limit) beside it. */
export function ResendLink({ id, name }: { id: number; name?: string }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button
        variant="secondary"
        size="sm"
        busy={busy}
        onClick={() =>
          run(async () => {
            await userAction(id, "resend-verification");
            toast.success(copy.customers.consent.linkSent);
            router.refresh();
          })
        }
      >
        {copy.customers.consent.sendAgain}
        {name ? <span className="sr-only"> ({name})</span> : null}
      </Button>
      {error ? (
        <span role="alert" className="max-w-[40ch] text-sm font-semibold text-destructive">
          {error.status === 429 ? error.message : errorText(error)}
        </span>
      ) : null}
    </span>
  );
}

/** The dialog that records a parent's consent by hand: how it was checked, where the evidence is, why. */
export function VerifyConsent({ id, name }: { id: number; name?: string }) {
  const words = copy.customers.verify;
  return (
    <FormDialog
      triggerLabel={
        <>
          {copy.customers.consent.recordByHand}
          {name ? <span className="sr-only"> ({name})</span> : null}
        </>
      }
      title={words.title}
      text={words.text}
      submitLabel={words.submit}
      success={words.done}
      labels={{ method: words.method, evidence_ref: words.evidence, reason: copy.common.reason }}
      onSubmit={(form) =>
        verifyConsent(id, {
          method: formValue(form, "method") as ConsentMethod,
          evidence_ref: formValue(form, "evidence_ref"),
          reason: formValue(form, "reason"),
        })
      }
    >
      {(error, prefix) => (
        <>
          <Field id={`${prefix}-method`} label={words.method} error={fieldError(error, "method")}>
            <Select name="method" defaultValue="staff_manual">
              {METHODS.map((method) => (
                <option key={method} value={method}>
                  {words.methods[method]}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            id={`${prefix}-evidence_ref`}
            label={words.evidence}
            help={words.evidenceHelp}
            error={fieldError(error, "evidence_ref")}
          >
            <Input name="evidence_ref" autoComplete="off" aria-required="true" data-no-draft="" />
          </Field>
          <Field
            id={`${prefix}-reason`}
            label={copy.common.reason}
            help={words.reasonHelp}
            error={fieldError(error, "reason")}
          >
            <Textarea name="reason" rows={3} aria-required="true" />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

/** What staff do about a student's consent, for whoever may. */
export function ConsentActions({ user }: { user: CustomerDetail }) {
  const can = useCan();
  if (!user.under_18 || user.consent === "verified") return null;
  if (user.status === "pending_deletion")
    return <p className="m-0 text-[15px] text-muted-foreground">{copy.customers.consent.holds}</p>;
  const resend = can(P.usersResendVerification) && user.consent === "pending";
  const record = can(P.usersVerifyConsent) && verifiable(user);
  if (!resend && !record) return null;
  return (
    <div className="flex flex-wrap items-center gap-2.5">
      {resend ? <ResendLink id={user.id} /> : null}
      {record ? <VerifyConsent id={user.id} /> : null}
    </div>
  );
}

/** The consent records as lines: when, what, how, by whom and where the evidence is. */
export function ConsentRecords({ user }: { user: CustomerDetail }) {
  const words = copy.customers.consent;
  if (!user.consents.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.users.noConsents}</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
      {user.consents.map((consent, index) => {
        const how = [
          consent.by_parent ? words.byParent : "",
          consent.method ? labelOf(copy.customers.methods, text(consent.method)) : "",
          consent.notice_version ? words.notice(text(consent.notice_version)) : "",
          typeof consent.verified_by === "number" ? words.recordedBy(consent.verified_by) : "",
          consent.evidence_ref ? words.evidence(text(consent.evidence_ref)) : "",
        ].filter(Boolean);
        return (
          <li key={`${text(consent.created)}-${index}`}>
            <span className="font-mono text-sm text-muted-foreground">{formatDateTime(text(consent.created))} · </span>
            {words.recordLine(humanize(text(consent.event)), how.join(", "))}
          </li>
        );
      })}
    </ul>
  );
}

/** The accounts a student's parent contact points to, or the students that named this adult. */
export function LinkedAccounts({ user }: { user: CustomerDetail }) {
  const words = copy.customers.consent;
  if (!user.linked.length) return <p className="m-0 text-[15px] text-muted-foreground">{words.linkedNone}</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
      {user.linked.map((account) => (
        <li key={account.id} className="flex flex-wrap items-center gap-2">
          <StatusChip tone="stopped">{labelOf(words.relation, account.relation)}</StatusChip>
          <Link href={`/users/${account.id}/`} className="font-semibold">
            {account.full_name || `#${account.id}`}
          </Link>
        </li>
      ))}
    </ul>
  );
}
