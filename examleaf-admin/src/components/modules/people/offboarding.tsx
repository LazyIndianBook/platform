"use client";

// An offboarding's checklist (GET people/<id>/offboarding/): each step in order, what the console did at once with its
// counts, and what an owner does by hand (the ERPNext user, Workspace, Razorpay, MSG91, AWS, Cloudflare, the error
// tracker, GitHub, the registrar, SSH keys, shared passwords, security keys, the last 90 days), each ticked with a
// note by whoever may (staff.assign_role: POST people/<id>/offboarding/tick/, audited). The API says which steps are
// the console's own: those are never ticked by hand.
import { StatusChip, type Tone } from "@/components/data/status-chip";
import { fieldError } from "@/components/forms/use-action";
import { useCan, useManifest } from "@/components/shell/manifest";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { type Offboarding, type OffboardingStep, tickOffboarding } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

import { FormDialog, formValue } from "../settings/form-dialog";

const words = copy.management.offboarding;
const TONE: Record<string, Tone> = { done: "done", todo: "waiting", not_needed: "stopped" };

function TickDialog({ person, step }: { person: number; step: OffboardingStep }) {
  return (
    <FormDialog
      triggerLabel={
        <>
          {words.tick} <span className="sr-only">{step.label}</span>
        </>
      }
      title={step.label}
      submitLabel={words.tick}
      success={words.ticked}
      labels={{ state: words.state, note: words.note }}
      onSubmit={(form) =>
        tickOffboarding(person, {
          step: step.key,
          state: formValue(form, "state") as OffboardingStep["state"] & string,
          note: formValue(form, "note"),
        })
      }
    >
      {(error, id) => (
        <>
          <Field id={`${id}-state`} label={words.state} error={fieldError(error, "state")}>
            <Select name="state" defaultValue={step.state === "todo" ? "done" : step.state}>
              {Object.entries(words.states).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field id={`${id}-note`} label={words.note} optional help={words.noteHelp} error={fieldError(error, "note")}>
            <Input name="note" autoComplete="off" maxLength={300} />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

export function OffboardingChecklist({ offboarding }: { offboarding: Offboarding }) {
  const can = useCan();
  const manifest = useManifest();
  const ticking = can(P.peopleAssign);
  const left = offboarding.steps.filter((step) => step.state === "todo").length;
  return (
    <div className="flex flex-col gap-4">
      <p className="m-0 text-[15px]">
        {words.started(staffLabel(offboarding.started_by, manifest.user.id), formatDateTime(offboarding.started_at))} ·{" "}
        “{offboarding.reason}”
      </p>
      <p className="m-0 text-[15px] font-semibold">
        {offboarding.finished_at ? words.finished(formatDateTime(offboarding.finished_at)) : words.open(left)}
      </p>
      <ol className="m-0 flex list-none flex-col p-0">
        {offboarding.steps.map((step) => (
          <li
            key={step.key}
            className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border py-3 text-[15px]"
          >
            <span className="flex min-w-0 flex-col gap-0.5">
              <span>{step.label}</span>
              <span className="text-sm text-muted-foreground">
                {[
                  labelOf(words.kinds, step.kind),
                  step.detail ?? "",
                  step.done_at
                    ? words.doneBy(staffLabel(step.done_by, manifest.user.id), formatDateTime(step.done_at))
                    : "",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </span>
            <span className="flex flex-wrap items-center gap-2">
              <StatusChip tone={TONE[step.state ?? "todo"] ?? "stopped"}>
                {labelOf(words.states, step.state ?? "todo")}
              </StatusChip>
              {ticking && step.kind === "manual" ? <TickDialog person={offboarding.user} step={step} /> : null}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
