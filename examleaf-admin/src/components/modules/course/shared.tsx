// The course module's chips and small words, for its server pages and its client parts alike: a revision's state, a
// clip's processing, a print run's state, an access's state (always the words, the colour only beside them), the
// option lists of its filters and forms, a clip's length.
import { StatusChip, type Tone } from "@/components/data/status-chip";
import type { CourseItemStats } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

const words = copy.course;

/** A table of words as a select's options. */
export const options = (table: Record<string, string>) =>
  Object.entries(table).map(([value, label]) => ({ value, label }));
export const subjectOptions = options(copy.content.subjects);

/** Tags as typed, separated by commas: each trimmed, the empty ones dropped. */
export const tagsOf = (typed: string) =>
  typed
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);

/** A clip's length, 3:07. */
export const clock = (seconds: number) => words.seconds(Math.max(0, Math.round(seconds)));

const REVISION: Record<string, Tone> = { draft: "waiting", review: "moving", approved: "good", published: "done" };

export function RevisionChip({ status, publishAt }: { status: string; publishAt?: string | null }) {
  return (
    <>
      <StatusChip tone={REVISION[status] ?? "stopped"}>{labelOf(words.revisionStates, status)}</StatusChip>
      {publishAt && status !== "published" ? (
        <StatusChip tone="moving">{words.outline.scheduled(formatDateTime(publishAt))}</StatusChip>
      ) : null}
    </>
  );
}

const PROCESSING: Record<string, Tone> = { uploaded: "waiting", processing: "moving", ready: "done", failed: "bad" };

export function ProcessingChip({ processing }: { processing: string }) {
  return <StatusChip tone={PROCESSING[processing] ?? "stopped"}>{labelOf(words.processing, processing)}</StatusChip>;
}

const BATCH: Record<string, Tone> = {
  generating: "moving",
  failed: "bad",
  ready: "good",
  dispatched: "done",
  void: "stopped",
};

export function BatchChip({ state }: { state: string }) {
  return <StatusChip tone={BATCH[state] ?? "stopped"}>{labelOf(words.codes.batchStates, state)}</StatusChip>;
}

const ACCESS: Record<string, Tone> = { active: "good", ended: "stopped", revoked: "bad" };

export function AccessChip({ state }: { state: string }) {
  return <StatusChip tone={ACCESS[state] ?? "stopped"}>{labelOf(words.access.states, state)}</StatusChip>;
}

const CODE: Record<string, Tone> = { unused: "good", redeemed: "done", void: "stopped", unknown: "bad" };

export function CodeChip({ state }: { state: string }) {
  return <StatusChip tone={CODE[state] ?? "stopped"}>{labelOf(words.codes.states, state)}</StatusChip>;
}

/** A share of 1 as a percentage with one decimal, or N/A. */
export const percent = (rate: number | null | undefined) =>
  rate === null || rate === undefined ? words.bank.na : `${(rate * 100).toFixed(1)}%`;

/** An item analysis flag in words (a distractor's names its option). */
export function flagLabel(flag: string): string {
  const option = /^distractor_(.+)$/.exec(flag);
  return option ? words.bank.distractor(option[1]) : labelOf(words.bank.flags, flag);
}

/** What the bank shows of a statistic: the number, or N/A under 30 learners (or before the first nightly run). */
export function statOf(stats: CourseItemStats, name: "n" | "p" | "discrimination"): string {
  if (stats.n_too_small || stats[name] === null) return words.bank.na;
  if (name === "n") return String(stats.n);
  if (name === "p") return percent(stats.p);
  return (stats.discrimination ?? 0).toFixed(2);
}
