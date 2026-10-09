"use client";

// A bulk action of the course as a staff job (POST jobs/, kind bulk_action), a dry run first: the dialog's fields and
// a reason make the payload; "Check them" starts the job as a dry run (each row through the action's own rules,
// nothing changed) and shows its progress, then how many can be done and each refusal with its reason (JobProgress
// lists them); Apply starts the job itself, which above the person's bulk limit waits for an approver (JobProgress says
// so and links the change request). The page is read again once it is applied.
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { JobProgress } from "@/components/data/job-progress";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import type { ApiError } from "@/lib/api/errors";
import { type CourseBulkAction, FINAL_JOB_STATES, type Job, startCourseBulk } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

const words = copy.course.bulk;

/** A finished job's outcomes in words: "3 can be done, 1 refused". */
export function outcomeLine(result: unknown): string {
  const outcomes = ((result ?? {}) as { outcomes?: Record<string, number> }).outcomes ?? {};
  const parts = Object.entries(outcomes)
    .filter(([, count]) => count > 0)
    .map(([name, count]) => `${count} ${labelOf(words.outcomes, name).toLowerCase()}`);
  return parts.length ? parts.join(", ") : words.none;
}

const validOf = (job: Job) => ((job.result ?? {}) as { outcomes?: Record<string, number> }).outcomes?.valid ?? 0;

type Run = { job: Job; dry: boolean; done: Job | null; payload: Record<string, unknown>; reason: string };

export function BulkDialog({
  action,
  targets,
  triggerLabel,
  triggerVariant = "secondary",
  title,
  lead,
  labels,
  build,
  children,
  onApplied,
}: {
  action: CourseBulkAction;
  /** The rows, or null when the form names them (the accounts to give access to). */
  targets: (number | string)[] | null;
  triggerLabel: React.ReactNode;
  triggerVariant?: "primary" | "secondary" | "destructive";
  title: string;
  lead: string;
  labels?: Record<string, string>;
  /** The payload (and the targets when the form names them) from the form; throws nothing: the API judges it. */
  build: (form: FormData) => { payload: Record<string, unknown>; targets?: (number | string)[] };
  children?: (id: string, error: ApiError | null) => React.ReactNode;
  onApplied?: () => void;
}) {
  const id = useId();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [run, setRun] = useState<(Run & { targets: (number | string)[] }) | null>(null);
  const starting = useAction();

  // a job that answers finished already (a small one) is not asked again
  const settled = (job: Job) => (FINAL_JOB_STATES.has(job.state) ? job : null);
  const applied = (done: Job | null) => {
    if (done?.state !== "done") return;
    toast.success(words.applied);
    onApplied?.();
    router.refresh();
  };
  const finish = (done: Job | null) => {
    setRun((current) => (current ? { ...current, done } : current));
    if (run && !run.dry) applied(done);
  };

  const apply = () =>
    run &&
    starting.run(async () => {
      const job = await startCourseBulk(action, run.targets, run.payload, run.reason, false);
      setRun({ ...run, job, dry: false, done: settled(job) });
      applied(settled(job));
    });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setRun(null);
          starting.setError(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" variant={triggerVariant}>
          {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>{title}</DialogHeader>
        {!run ? (
          <form
            noValidate
            className="flex flex-col gap-3.5"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              const reason = String(form.get("reason") ?? "").trim();
              const built = build(form);
              const rows = built.targets ?? targets ?? [];
              await starting.run(async () => {
                const job = await startCourseBulk(action, rows, built.payload, reason, true);
                setRun({ job, dry: true, done: settled(job), payload: built.payload, reason, targets: rows });
              });
            }}
          >
            <DialogBody>
              <DialogDescription>{lead}</DialogDescription>
            </DialogBody>
            <ErrorSummary
              error={starting.error}
              labels={{ reason: copy.common.reason, ...labels }}
              idPrefix={`${id}-`}
            />
            {open && children ? children(id, starting.error) : null}
            <Field
              id={`${id}-reason`}
              label={copy.common.reason}
              help={copy.common.reasonHelp}
              error={fieldError(starting.error, "reason")}
            >
              <Textarea name="reason" rows={2} aria-required="true" />
            </Field>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="secondary">{copy.common.cancel}</Button>
              </DialogClose>
              <Button type="submit" busy={starting.busy}>
                {words.dryRun}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <div className="flex flex-col gap-3.5">
            <JobProgress key={run.job.id} job={run.job} onDone={finish} />
            {run.done?.state === "done" ? (
              <p className="m-0 text-[15px] font-semibold" role="status">
                {run.dry ? words.checked(outcomeLine(run.done.result)) : outcomeLine(run.done.result)}
              </p>
            ) : null}
            <ErrorSummary error={starting.error} />
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="secondary">{run.dry ? copy.common.cancel : copy.common.close}</Button>
              </DialogClose>
              {run.dry && run.done?.state === "done" && validOf(run.done) > 0 ? (
                <Button busy={starting.busy} onClick={apply}>
                  {words.apply}
                </Button>
              ) : null}
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
