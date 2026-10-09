"use client";

// The yearly dark-pattern self-audit (privacy/dark-pattern-audits/): started for the year due, then each of the 13
// patterns answered (what was found, what was fixed or ruled out) with the certificate's text and the day the website
// shows it from (PATCH), then completed once with the year typed (POST complete/: the API refuses until every pattern
// and the text are there, and keeps it as signed from then on). The signed copy is kept in the private storage
// (POST file/) and downloaded through the API (GET file/, recorded).
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmTyped } from "@/components/data/confirm-typed";
import { ActionForm, formText } from "@/components/forms/action-form";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import {
  completeDarkPatternAudit,
  createDarkPatternAudit,
  type DarkPatternAudit,
  updateDarkPatternAudit,
  uploadCertificate,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";

export function StartAudit({ year }: { year: number }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <div className="flex flex-col gap-3">
      <ErrorSummary error={error} />
      <div>
        <Button
          busy={busy}
          onClick={() =>
            run(async () => {
              await createDarkPatternAudit(year);
              toast.success(copy.legal.darkStarted);
              router.push(`/privacy/dark-pattern-audit/?year=${year}`);
              router.refresh();
            })
          }
        >
          {copy.legal.darkStart(year)}
        </Button>
      </div>
    </div>
  );
}

/** The 13 rows, the certificate's text and its day, saved together. */
export function AuditForm({ audit }: { audit: DarkPatternAudit }) {
  const rows = audit.rows ?? [];
  const id = `audit-${audit.year}`;
  return (
    <ActionForm
      id={id}
      submitLabel={copy.legal.saveAudit}
      success={copy.legal.auditSaved}
      variant="secondary"
      className="flex max-w-[52rem] flex-col gap-6"
      labels={{
        rows: copy.legal.darkPattern,
        certificate_text: copy.legal.certificateText,
        effective_from: copy.legal.effectiveFrom,
      }}
      onSubmit={(form) =>
        updateDarkPatternAudit(audit.id, {
          rows: rows.map((row) => ({
            pattern: row.pattern,
            finding: formText(form, `finding-${row.pattern}`),
            fix: formText(form, `fix-${row.pattern}`),
          })),
          certificate_text: formText(form, "certificate_text"),
          effective_from: formText(form, "effective_from") || null,
        })
      }
    >
      {(error) => (
        <>
          <ol className="m-0 flex list-none flex-col gap-6 p-0">
            {rows.map((row, index) => (
              <li key={row.pattern} className="flex flex-col gap-3 border-t border-border pt-4">
                <h3 className="m-0 font-head text-lg">
                  <span className="font-mono text-sm text-muted-foreground">{index + 1}. </span>
                  {row.label}
                </h3>
                <FormGrid style={{ "--min": "280px" } as React.CSSProperties}>
                  <Field id={`${id}-finding-${row.pattern}`} label={copy.legal.finding} help={copy.legal.findingHelp}>
                    <Textarea name={`finding-${row.pattern}`} rows={3} maxLength={2000} defaultValue={row.finding} />
                  </Field>
                  <Field id={`${id}-fix-${row.pattern}`} label={copy.legal.fix}>
                    <Textarea name={`fix-${row.pattern}`} rows={3} maxLength={2000} defaultValue={row.fix} />
                  </Field>
                </FormGrid>
              </li>
            ))}
          </ol>
          <Field
            id={`${id}-certificate_text`}
            label={copy.legal.certificateText}
            help={copy.legal.certificateHelp}
            error={fieldError(error, "certificate_text")}
          >
            <Textarea name="certificate_text" rows={5} defaultValue={audit.certificate_text ?? ""} />
          </Field>
          <Field
            id={`${id}-effective_from`}
            label={copy.legal.effectiveFrom}
            optional
            help={copy.legal.effectiveHelp}
            error={fieldError(error, "effective_from")}
          >
            <Input name="effective_from" type="date" defaultValue={audit.effective_from ?? ""} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

export function CompleteAudit({ audit }: { audit: DarkPatternAudit }) {
  return (
    <ConfirmTyped
      label={String(audit.year)}
      triggerLabel={copy.legal.complete}
      triggerVariant="primary"
      title={copy.legal.completeTitle(audit.year)}
      text={copy.legal.completeText}
      confirmLabel={copy.legal.complete}
      confirmVariant="primary"
      success={copy.legal.completed}
      onConfirm={() => completeDarkPatternAudit(audit.id, "")}
    />
  );
}

export function CertificateUpload({ audit }: { audit: DarkPatternAudit }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [file, setFile] = useState<File | null>(null);
  const id = `certificate-${audit.year}`;
  return (
    <form
      noValidate
      className="flex max-w-[40rem] flex-col gap-3"
      onSubmit={async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        if (!file) return;
        const ok = await run(() => uploadCertificate(audit.id, file));
        if (!ok) return;
        form.reset();
        setFile(null);
        toast.success(copy.legal.uploaded);
        router.refresh();
      }}
    >
      <ErrorSummary error={error} labels={{ file: copy.legal.uploadLabel }} idPrefix={`${id}-`} />
      <Field id={`${id}-file`} label={copy.legal.uploadLabel} error={fieldError(error, "file")}>
        <Input
          name="file"
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </Field>
      <div>
        <Button type="submit" variant="secondary" busy={busy} disabled={!file}>
          {copy.legal.upload}
        </Button>
      </div>
    </form>
  );
}
