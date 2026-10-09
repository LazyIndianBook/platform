"use client";

// The list's bulk bar for the chosen accounts: suspend, lift a suspension, sign out everywhere, send the parents'
// links again (never a deletion). Each is a background job (POST jobs/, kind bulk_action) and is asked in two steps:
// "Check first" is a dry run that changes nothing and says how many accounts it would change, how many it would leave
// alone and why, how many belong to students under 18 and whether a second person must approve it (always, with a
// child's account among them, and above your row limit); only then "Run it". What the person may not do is not drawn;
// the API decides the rest, row by row, and records one event for each account and one for the batch.
import { useId, useState } from "react";

import { JobProgress } from "@/components/data/job-progress";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan, useManifest } from "@/components/shell/manifest";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import {
  bulkResult,
  type Customer,
  type CustomersBulkAction,
  type Job,
  limitsOf,
  startCustomersJob,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";

/** The actions, and the permission whose holders may start each (the job's own permission is the action's). */
const ACTIONS: { name: CustomersBulkAction; permission: string }[] = [
  { name: "user.suspend", permission: P.usersSuspend },
  { name: "user.unsuspend", permission: P.usersSuspend },
  { name: "user.end_sessions", permission: P.usersEndSessions },
  { name: "user.resend_consent", permission: P.usersResendVerification },
];

type BulkProps = {
  rows: Customer[];
  clear: () => void;
  onJob: (job: Job, title: string) => void;
};

/** What a check found, in sentences: the accounts it would change, those it would leave alone, the children among
 *  them and whether the real run waits for an approver. */
export function CheckSummary({ job }: { job: Job }) {
  const words = copy.customers.bulk;
  const { outcomes, minors, approval } = bulkResult(job);
  const valid = outcomes.valid ?? 0;
  const refused = outcomes.refused ?? 0;
  return (
    <div className="flex flex-col gap-2">
      <p className="m-0 text-[15px] font-semibold" role="status">
        {valid ? words.can(valid) : words.nothing}
      </p>
      {refused ? <p className="m-0 text-[15px]">{words.left(refused)}</p> : null}
      {minors ? <p className="m-0 text-[15px]">{words.minors(minors)}</p> : null}
      {approval ? (
        <Alert variant="warning" title={words.waits(approval)} />
      ) : (
        <p className="m-0 text-[15px] text-muted-foreground">{words.runsAtOnce}</p>
      )}
    </div>
  );
}

function BulkDialog({
  action,
  ids,
  clear,
  onJob,
}: {
  action: CustomersBulkAction;
  ids: number[];
  clear: () => void;
  onJob: BulkProps["onJob"];
}) {
  const id = useId();
  const manifest = useManifest();
  const words = copy.customers.bulk;
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  // the check: its job, then the job as it ended (null: the answer could not be read)
  const [check, setCheck] = useState<{ job: Job; ended: Job | null | undefined } | null>(null);
  const asking = useAction();
  const starting = useAction();
  const error = starting.error ?? asking.error;
  const ended = check?.ended && check.ended.state === "done" ? check.ended : null;
  const canRun = ended !== null && (bulkResult(ended).outcomes.valid ?? 0) > 0;

  const reset = () => {
    setReason("");
    setCheck(null);
    asking.setError(null);
    starting.setError(null);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        {words.actions[action]}
      </Button>
      <DialogContent>
        <DialogHeader>{words.titles[action](ids.length)}</DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-3.5"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!canRun) return;
            await starting.run(async () => {
              const job = await startCustomersJob(action, ids, reason.trim(), false);
              setOpen(false);
              reset();
              clear();
              toast.success(words.started);
              onJob(job, words.actions[action]);
            });
          }}
        >
          <DialogBody>
            <DialogDescription>{words.texts[action]}</DialogDescription>
            <p className="m-0 text-sm text-muted-foreground">{words.limits(limitsOf(manifest).bulk_rows)}</p>
          </DialogBody>
          <ErrorSummary error={error} idPrefix={`${id}-`} labels={{ "params.reason": words.reason }} />
          <Field
            id={`${id}-params.reason`}
            label={words.reason}
            help={words.reasonHelp}
            error={fieldError(error, "params.reason")}
          >
            <Textarea
              name="reason"
              rows={2}
              aria-required="true"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </Field>
          {check ? (
            <section aria-label={words.checked} className="flex flex-col gap-3">
              <JobProgress
                key={check.job.id}
                job={check.job}
                onDone={(finished) =>
                  setCheck((current) =>
                    current?.job.id === check.job.id ? { job: current.job, ended: finished } : current,
                  )
                }
              />
              {ended ? <CheckSummary job={ended} /> : null}
            </section>
          ) : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary">{copy.common.cancel}</Button>
            </DialogClose>
            <Button
              variant="secondary"
              busy={asking.busy || (check !== null && check.ended === undefined)}
              onClick={() =>
                asking.run(async () => {
                  setCheck(null);
                  setCheck({ job: await startCustomersJob(action, ids, reason.trim(), true), ended: undefined });
                })
              }
            >
              {check ? words.again : words.check}
            </Button>
            <Button type="submit" busy={starting.busy} disabled={!canRun}>
              {words.run(ids.length)}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function UsersBulk({ rows, clear, onJob }: BulkProps) {
  const can = useCan();
  const words = copy.customers.bulk;
  const ids = rows.map((row) => row.id);
  const shown = ACTIONS.filter((action) => can(action.permission));
  return (
    <>
      <p className="m-0 text-[15px] font-semibold" role="status">
        {words.selected(ids.length)}
      </p>
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label={words.group}>
        {shown.map((action) => (
          <BulkDialog key={action.name} action={action.name} ids={ids} clear={clear} onJob={onJob} />
        ))}
        <Button size="sm" variant="ghost" onClick={clear}>
          {words.clear}
        </Button>
      </div>
    </>
  );
}
