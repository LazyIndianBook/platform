"use client";

// The GSTR-1 export (POST tax/gstr1/ {month, months, dry_run}): a month, or the quarter ending with it, run as a
// background job; the page's list of the person's exports then shows its progress and its file (JobProgress). One
// above the person's export limit waits for an approver first; a dry run only counts the documents.
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Checkbox } from "@/components/ui/choice";
import { Field, FormGrid } from "@/components/ui/field";
import { Select } from "@/components/ui/native-select";
import { startGstr1 } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { monthLabel } from "./periods";

/** `months`: the months to choose from, newest first; the one before this is chosen (its GSTR-1 is due on the 11th). */
export function Gstr1Form({ months }: { months: string[] }) {
  return (
    <ActionForm
      id="gstr1"
      submitLabel={copy.tax.gstr1Run}
      success={copy.tax.gstr1Started}
      labels={{ month: copy.tax.month, months: copy.tax.gstr1Period, dry_run: copy.tax.gstr1DryRun }}
      onSubmit={(form) =>
        startGstr1({
          month: formText(form, "month"),
          months: formText(form, "months") === "3" ? 3 : 1,
          dry_run: form.get("dry_run") === "on",
        })
      }
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="gstr1-month" label={copy.tax.month} error={fieldError(error, "month")}>
              <Select name="month" defaultValue={months[1] ?? months[0]}>
                {months.map((month) => (
                  <option key={month} value={month}>
                    {monthLabel(month)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              id="gstr1-months"
              label={copy.tax.gstr1Period}
              help={copy.tax.gstr1QuarterHelp}
              error={fieldError(error, "months")}
            >
              <Select name="months" defaultValue="1">
                <option value="1">{copy.tax.gstr1Month}</option>
                <option value="3">{copy.tax.gstr1Quarter}</option>
              </Select>
            </Field>
          </FormGrid>
          <Checkbox name="dry_run">{copy.tax.gstr1DryRun}</Checkbox>
        </>
      )}
    </ActionForm>
  );
}
