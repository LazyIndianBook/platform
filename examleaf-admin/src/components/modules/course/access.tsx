"use client";

// Access to the course (GET course/entitlements/): who may watch which subject, from a book code, a purchase or a
// grant, until when, open, ended or revoked; filtered by subject, source and state, or found by an account's whole
// email address (the API records the search by its hash). One row chosen: extended or revoked at once, with a reason;
// more: the same as a bulk job, a dry run first. Access is given to one account here, or to many (their account
// numbers) as a bulk job. Ending access never touches a student's progress: access given again picks up where it
// stopped. A learner's page opens from its own link (never prefetched: every view of it is logged).
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import {
  type CourseEntitlement,
  extendEntitlement,
  grantEntitlement,
  revokeEntitlement,
  type SavedView,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate } from "@/lib/format";
import { P } from "@/lib/modules";

import { BulkDialog } from "./bulk";
import { FormDialog } from "./form-dialog";
import { AccessChip, options, subjectOptions } from "./shared";

const words = copy.course.access;
const SUBJECTS = [...subjectOptions, { value: "ALL", label: words.subjectAll }];

/** Account numbers as typed: whole numbers, one a line or separated by commas or spaces, each once. */
export function accountsOf(typed: string): number[] {
  return [
    ...new Set(
      typed
        .split(/[\s,;]+/)
        .map((part) => part.trim().replace(/^#/, ""))
        .filter((part) => /^\d+$/.test(part))
        .map(Number),
    ),
  ];
}

function Days({ id, error }: { id: string; error: Parameters<typeof fieldError>[0] }) {
  return (
    <Field id={`${id}-days`} label={words.days} help={words.daysHelp} error={fieldError(error, "days")}>
      <Input name="days" type="number" inputMode="numeric" min={1} max={365} defaultValue={30} className="w-32" />
    </Field>
  );
}

function Reason({ id, error }: { id: string; error: Parameters<typeof fieldError>[0] }) {
  return (
    <Field
      id={`${id}-reason`}
      label={copy.common.reason}
      help={copy.common.reasonHelp}
      error={fieldError(error, "reason")}
    >
      <Textarea name="reason" rows={2} aria-required="true" />
    </Field>
  );
}

function AccessBulk({ rows, clear }: { rows: CourseEntitlement[]; clear: () => void }) {
  const can = useCan();
  const router = useRouter();
  if (!can(P.accessExtend)) return null;
  const [one] = rows;
  const days = (form: FormData) => Number(String(form.get("days") ?? "").trim());
  if (rows.length === 1)
    return (
      <>
        <FormDialog
          triggerLabel={words.extend(1)}
          title={words.extendTitle(1)}
          text={words.extendLead}
          submitLabel={words.extend(1)}
          success={words.extended}
          labels={{ days: words.days, reason: copy.common.reason }}
          disabled={!one.can_extend}
          onSubmit={(form) => extendEntitlement(one.id, days(form), String(form.get("reason") ?? "").trim())}
          onDone={() => {
            clear();
            router.refresh();
          }}
        >
          {(id, error) => (
            <>
              <Days id={id} error={error} />
              <Reason id={id} error={error} />
            </>
          )}
        </FormDialog>
        <ConfirmDialog
          triggerLabel={words.revoke(1)}
          title={words.revokeTitle(1)}
          text={words.revokeLead}
          confirmLabel={words.revoke(1)}
          reason
          success={words.revoked}
          disabled={!one.can_revoke}
          onConfirm={({ reason }) => revokeEntitlement(one.id, reason)}
          onDone={() => {
            clear();
            router.refresh();
          }}
        />
      </>
    );
  const ids = rows.map((row) => row.id);
  return (
    <>
      <BulkDialog
        action="entitlement.extend"
        targets={ids}
        triggerLabel={words.extend(rows.length)}
        title={words.extendTitle(rows.length)}
        lead={`${words.extendLead} ${words.bulkLead}`}
        labels={{ days: words.days }}
        build={(form) => ({ payload: { days: days(form) } })}
        onApplied={clear}
      >
        {(id, error) => <Days id={id} error={error} />}
      </BulkDialog>
      <BulkDialog
        action="entitlement.revoke"
        targets={ids}
        triggerLabel={words.revoke(rows.length)}
        triggerVariant="destructive"
        title={words.revokeTitle(rows.length)}
        lead={`${words.revokeLead} ${words.bulkLead}`}
        build={() => ({ payload: {} })}
        onApplied={clear}
      />
    </>
  );
}

export function AccessTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: CourseEntitlement[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const can = useCan();
  const columns: Column<CourseEntitlement>[] = [
    {
      key: "learner",
      label: words.columns.learner,
      wrap: true,
      render: (row) => (
        <span className="inline-flex flex-col gap-0.5">
          <span className="inline-flex flex-wrap items-center gap-2">
            {row.user.name || copy.course.learner.account(row.user.id)}
            {row.user.is_minor ? <StatusChip tone="waiting">{words.minor}</StatusChip> : null}
          </span>
          <span className="font-mono text-sm text-muted-foreground">{row.user.email}</span>
          <Link href={`/course/learners/${row.user.id}/`} prefetch={false} className="text-sm">
            {words.openLearner}
            <span className="sr-only">: {copy.course.learner.account(row.user.id)}</span>
          </Link>
        </span>
      ),
    },
    { key: "subject", label: words.columns.subject, render: (row) => row.subject_name || words.every },
    { key: "source", label: words.columns.source, render: (row) => labelOf(words.sources, row.source) },
    {
      key: "until",
      label: words.columns.until,
      render: (row) => (row.valid_until ? formatDate(row.valid_until) : words.noEnd),
    },
    { key: "state", label: words.columns.state, render: (row) => <AccessChip state={row.state} /> },
    {
      key: "note",
      label: words.columns.note,
      render: (row) => row.reference || row.note || copy.common.none,
      hidden: true,
    },
  ];
  return (
    <DataTable
      listKey="course-entitlements"
      caption={words.title}
      rows={rows}
      columns={columns}
      rowId={(row) => String(row.id)}
      next={next}
      previous={previous}
      views={views}
      filters={[
        { name: "q", label: words.filters.q, type: "search" },
        { name: "subject", label: words.filters.subject, type: "select", options: SUBJECTS },
        { name: "source", label: words.filters.source, type: "select", options: options(words.sources) },
        { name: "state", label: words.filters.state, type: "select", options: options(words.states) },
      ]}
      selection={
        can(P.accessExtend)
          ? {
              label: (row) => words.choose(copy.course.learner.account(row.user.id)),
              page: words.page,
              bulk: (chosen, clear) => <AccessBulk rows={chosen} clear={clear} />,
            }
          : undefined
      }
      toolbar={can(P.accessGrant) ? <GrantMany /> : undefined}
      empty={{ title: words.emptyTitle, text: words.emptyText }}
    />
  );
}

function Grant({ id, error }: { id: string; error: Parameters<typeof fieldError>[0] }) {
  return (
    <FormGrid>
      <Field id={`${id}-subject`} label={words.subject} error={fieldError(error, "subject")}>
        <Select name="subject" defaultValue="PHY">
          {SUBJECTS.map((subject) => (
            <option key={subject.value} value={subject.value}>
              {subject.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field
        id={`${id}-valid_until`}
        label={words.until}
        help={words.untilHelp}
        optional
        error={fieldError(error, "valid_until")}
      >
        <Input name="valid_until" type="date" />
      </Field>
      <Field
        id={`${id}-reference`}
        label={words.reference}
        help={words.referenceHelp}
        optional
        error={fieldError(error, "reference")}
      >
        <Input name="reference" maxLength={40} autoComplete="off" />
      </Field>
    </FormGrid>
  );
}

/** Access given to many accounts at once: their numbers, a dry run, then Apply. */
function GrantMany() {
  return (
    <BulkDialog
      action="entitlement.grant"
      targets={null}
      triggerLabel={words.bulkGrant}
      title={words.bulkGrant}
      lead={words.bulkGrantLead}
      labels={{
        accounts: words.accounts,
        subject: words.subject,
        valid_until: words.until,
        reference: words.reference,
      }}
      build={(form) => ({
        targets: accountsOf(String(form.get("accounts") ?? "")),
        payload: {
          subject: String(form.get("subject") ?? ""),
          valid_until: String(form.get("valid_until") ?? "") || null,
          reference: String(form.get("reference") ?? "").trim(),
        },
      })}
    >
      {(id, error) => (
        <>
          <Field id={`${id}-accounts`} label={words.accounts} error={fieldError(error, "targets")}>
            <Textarea name="accounts" rows={4} className="font-mono" />
          </Field>
          <Grant id={id} error={error} />
        </>
      )}
    </BulkDialog>
  );
}

/** Access given to one account (POST course/entitlements/). */
export function GrantForm() {
  const id = "course-grant";
  return (
    <ActionForm
      id={id}
      submitLabel={words.grantButton}
      success={words.granted}
      labels={{
        user: words.account,
        subject: words.subject,
        valid_until: words.until,
        reference: words.reference,
        reason: copy.common.reason,
      }}
      onSubmit={(form) =>
        grantEntitlement({
          user: Number(formText(form, "user").replace(/^#/, "")),
          subject: formText(form, "subject"),
          valid_until: formText(form, "valid_until") || null,
          reference: formText(form, "reference"),
          reason: formText(form, "reason"),
        })
      }
    >
      {(error) => (
        <>
          <Field id={`${id}-user`} label={words.account} error={fieldError(error, "user")}>
            <Input name="user" inputMode="numeric" autoComplete="off" className="w-40 font-mono" />
          </Field>
          <Grant id={id} error={error} />
          <Reason id={id} error={error} />
        </>
      )}
    </ActionForm>
  );
}
