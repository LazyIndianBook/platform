"use client";

// An import from the books repository (staff.import_content): the subject and the commit (empty: the folder as it is;
// on a test site, the test papers), a dry run first (POST jobs/ kind content_import, dry_run: the API compares and
// writes nothing), its counts and labels when it is done, then Apply with the same subject and commit, naming the dry
// run (the API refuses an apply without one, or once the repository has moved). Each run is a job followed with
// JobProgress; what it found is the job's result, read as the API gives it.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { JobProgress } from "@/components/data/job-progress";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useManifest } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import { FINAL_JOB_STATES, type ImportParams, type Job, startImport } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

const words = copy.content.imports;
type Found = { counts?: Record<string, number>; rows?: Record<string, string[]>; commit?: string | null };

/** What an import found: its counts, and the labels behind each (not "the same": those are only counted). */
export function ImportResult({ job }: { job: Job }) {
  const result = (job.result ?? {}) as Found;
  const counts = result.counts ?? {};
  return (
    <div className="flex flex-col gap-3">
      <p className="m-0 text-sm text-muted-foreground">
        {labelOf(copy.content.subjectNames, String((job.params as { subject?: string })?.subject ?? ""))}
        {" · "}
        {(job.params as { fixtures?: boolean })?.fixtures ? words.testPapers : result.commit ? words.commitLine(result.commit.slice(0, 12)) : words.noCommit}
      </p>
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-3">
        {Object.keys(words.counts).map((outcome) => (
          <div key={outcome} className="flex flex-col gap-0.5 rounded-lg border border-border bg-card px-3 py-2">
            <dt className="text-sm text-muted-foreground">{words.counts[outcome]}</dt>
            <dd className="m-0 font-mono text-xl">{(counts[outcome] ?? 0).toLocaleString("en-IN")}</dd>
          </div>
        ))}
      </dl>
      {Object.entries(result.rows ?? {}).filter(([, labels]) => labels.length).map(([outcome, labels]) => (
        <details key={outcome}>
          <summary className="min-h-11 cursor-pointer text-[15px] font-semibold text-primary">
            {labelOf(words.counts, outcome)} · {labels.length.toLocaleString("en-IN")}
          </summary>
          <ul className="m-0 mt-1 flex max-h-72 list-none flex-col gap-0.5 overflow-y-auto p-0 font-mono text-sm">
            {labels.map((label) => (
              <li key={label}>{label}</li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}

export function ImportForm() {
  const router = useRouter();
  const manifest = useManifest();
  const testSite = Boolean(manifest.flags.test_mode);
  const { run, busy, error } = useAction();
  const [params, setParams] = useState<ImportParams>({ subject: "physics", commit: "", fixtures: false });
  const [dry, setDry] = useState<Job | null>(null);
  const [dryDone, setDryDone] = useState<Job | null>(null);
  const [apply, setApply] = useState<Job | null>(null);
  const set = (change: Partial<ImportParams>) => {
    setParams({ ...params, ...change });
    setDry(null);
    setDryDone(null);
    setApply(null);
  };
  return (
    <div className="flex max-w-[48rem] flex-col gap-5">
      <ErrorSummary error={error} labels={{ "params.subject": words.subject, "params.commit": words.commit, "params.dry_run_job": words.apply }} idPrefix="import-" />
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          run(async () => {
            setDryDone(null);
            setApply(null);
            const job = await startImport(
              { subject: params.subject, commit: params.commit.trim(), ...(params.fixtures ? { fixtures: true } : {}) },
              true,
            );
            setDry(job);
            if (FINAL_JOB_STATES.has(job.state)) setDryDone(job); // (a job already over: nothing to follow)
          });
        }}
      >
        <div className="grid gap-4 min-[640px]:grid-cols-2">
          <Field id="import-params.subject" label={words.subject} error={fieldError(error, "params.subject")}>
            <Select name="subject" value={params.subject} onChange={(event) => set({ subject: event.target.value })}>
              {Object.entries(copy.content.subjectNames).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="import-params.commit" label={words.commit} optional help={words.commitHelp} error={fieldError(error, "params.commit")}>
            <Input
              name="commit"
              value={params.commit}
              onChange={(event) => set({ commit: event.target.value })}
              autoComplete="off"
              spellCheck={false}
              disabled={params.fixtures}
              className="font-mono"
            />
          </Field>
        </div>
        {testSite ? (
          <label className="flex min-h-11 cursor-pointer items-center gap-3 text-[15px]">
            <input
              type="checkbox"
              data-slot="checkbox"
              checked={Boolean(params.fixtures)}
              onChange={(event) => set({ fixtures: event.target.checked, commit: "" })}
            />
            {words.fixtures}
          </label>
        ) : null}
        <div>
          <Button type="submit" busy={busy && !dryDone}>
            {words.dryRun}
          </Button>
        </div>
      </form>
      {dry ? (
        <section aria-labelledby="import-dry-title" className="flex flex-col gap-3">
          <h3 id="import-dry-title" className="m-0 text-[15px] font-semibold">
            {words.dryRunning}
          </h3>
          <JobProgress job={dry} onDone={(job) => setDryDone(job)} />
          {dryDone?.state === "done" ? (
            <>
              <ImportResult job={dryDone} />
              <p className="m-0 text-[15px] text-muted-foreground">{words.applyLead}</p>
              <div>
                <Button
                  busy={busy && Boolean(dryDone) && !apply}
                  disabled={Boolean(apply)}
                  onClick={() =>
                    run(async () => {
                      setApply(
                        await startImport(
                          {
                            subject: params.subject,
                            commit: params.commit.trim(),
                            ...(params.fixtures ? { fixtures: true } : {}),
                            dry_run_job: dryDone.id,
                          },
                          false,
                        ),
                      );
                    })
                  }
                >
                  {words.apply}
                </Button>
              </div>
            </>
          ) : null}
        </section>
      ) : null}
      {apply ? (
        <section aria-labelledby="import-apply-title" className="flex flex-col gap-3">
          <h3 id="import-apply-title" className="m-0 text-[15px] font-semibold">
            {words.applying}
          </h3>
          <JobProgress
            job={apply}
            onDone={(job) => {
              if (job?.state === "done") {
                toast.success(words.applied);
                router.refresh();
              }
            }}
          />
        </section>
      ) : null}
    </div>
  );
}
