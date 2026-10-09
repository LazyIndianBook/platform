"use client";

// A reported mistake's triage (staff.triage_report): the steps its state allows, as the API has them (reported →
// confirmed or rejected → fixed online → fixed in printing; a rejection reopened), a rejection with its reason, a
// fix in printing with the printing's label, the reporter told once it is fixed (if they left an address), and the
// staff note and the errata switch (PATCH). The API refuses any other step; its words are shown.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { ActionForm, formText } from "@/components/forms/action-form";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { type ContentReportDetail, reportStep, tellReporter, updateReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const words = copy.content.reports;

export function ReportSteps({ report }: { report: ContentReportDetail }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [pressed, setPressed] = useState("");
  const state = report.state ?? "reported";
  const step = (verb: "confirm" | "fix-online", success: string) => {
    setPressed(verb);
    run(async () => {
      await reportStep(report.id, verb);
      toast.success(success);
      router.refresh();
    });
  };
  return (
    <div className="flex flex-col gap-3">
      <ErrorSummary error={error} />
      <div className="flex flex-wrap gap-2.5">
        {state === "reported" ? (
          <Button size="sm" busy={busy && pressed === "confirm"} onClick={() => step("confirm", words.confirmed)}>
            {words.confirm}
          </Button>
        ) : null}
        {state === "reported" || state === "confirmed" ? (
          <Button
            size="sm"
            variant="secondary"
            busy={busy && pressed === "fix-online"}
            onClick={() => step("fix-online", words.fixedOnline)}
          >
            {words.fixOnline}
          </Button>
        ) : null}
        {state === "confirmed" || state === "fixed_online" ? (
          <ConfirmDialog
            triggerLabel={words.fixInPrinting}
            title={words.fixInPrintingTitle}
            text={words.fixInPrintingText}
            fields={[{ name: "fixed_in", label: words.printing }]}
            confirmLabel={words.fixInPrinting}
            confirmVariant="primary"
            success={words.fixedInPrinting}
            onConfirm={({ values }) => reportStep(report.id, "fix-in-printing", { fixed_in: values.fixed_in })}
          />
        ) : null}
        {state === "reported" || state === "confirmed" ? (
          <ConfirmDialog
            triggerLabel={words.reject}
            title={words.rejectTitle}
            text={words.rejectText}
            fields={[{ name: "staff_note", label: words.reason }]}
            confirmLabel={words.reject}
            success={words.rejected}
            onConfirm={({ values }) => reportStep(report.id, "reject", { staff_note: values.staff_note })}
          />
        ) : null}
        {state === "rejected" ? (
          <Button size="sm" variant="secondary" busy={busy && pressed === "reopen"} onClick={() => {
            setPressed("reopen");
            run(async () => {
              await reportStep(report.id, "reopen");
              toast.success(words.reopened);
              router.refresh();
            });
          }}>
            {words.reopen}
          </Button>
        ) : null}
        {report.can_tell ? (
          <ConfirmDialog
            triggerLabel={words.tell}
            triggerVariant="primary"
            title={words.tellTitle}
            text={words.tellText}
            confirmLabel={words.tell}
            confirmVariant="primary"
            success={words.toldToast}
            onConfirm={() => tellReporter(report.id)}
          />
        ) : null}
      </div>
    </div>
  );
}

export function ReportNotes({ report }: { report: ContentReportDetail }) {
  return (
    <ActionForm
      id={`report-${report.id}`}
      submitLabel={words.saveNotes}
      success={words.notesSaved}
      labels={{ staff_note: words.staffNote, public: words.public }}
      variant="secondary"
      onSubmit={(form) =>
        updateReport(report.id, { staff_note: formText(form, "staff_note"), public: form.get("public") === "on" })
      }
    >
      {(error) => (
        <>
          <Field id={`report-${report.id}-staff_note`} label={words.staffNote} help={words.staffNoteHelp} error={fieldError(error, "staff_note")}>
            <Textarea name="staff_note" rows={3} defaultValue={report.staff_note ?? ""} />
          </Field>
          <label className="flex min-h-11 cursor-pointer items-center gap-3 text-[15px]">
            <input type="checkbox" name="public" data-slot="checkbox" defaultChecked={Boolean(report.public)} />
            {words.public}
          </label>
        </>
      )}
    </ActionForm>
  );
}
