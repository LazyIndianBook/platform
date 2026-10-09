// What /system/ opens on: one line per subsystem (GET system/'s `status`: health checks, queues, webhooks, email, SMS,
// backups, the audit chain, the ERPNext sync, dependencies, hardening, the checkout's scripts, logs and time), each in
// words with its state (Good, Look at it, Act now, Not set up) and since when, linking to its own page where it has
// one; then the system's pages.
import Link from "next/link";

import { StatusChip, type Tone } from "@/components/data/status-chip";
import type { SystemLine } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatAgo } from "@/lib/format";

const words = copy.management.system;
const TONE: Record<string, Tone> = { ok: "good", warn: "waiting", bad: "bad", off: "stopped" };
/** The lines that have a page of their own, and the permission-free path to it (the page asks the API itself). */
export const SYSTEM_PAGES = ["sync", "backups", "logs", "dependencies", "hardening", "scripts"] as const;

export function SystemStateChip({ state }: { state: string }) {
  return <StatusChip tone={TONE[state] ?? "stopped"}>{labelOf(words.states, state)}</StatusChip>;
}

export function StatusLines({ lines, now }: { lines: SystemLine[]; now: number }) {
  return (
    <ul className="m-0 flex list-none flex-col border-t-[1.5px] border-foreground p-0">
      {lines.map((line) => {
        const page = (SYSTEM_PAGES as readonly string[]).includes(line.key) ? `/system/${line.key}/` : null;
        const name = labelOf(words.keys, line.key);
        return (
          <li
            key={line.key}
            className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-border py-2.5 text-[15px]"
          >
            <span className="flex min-w-0 flex-col">
              {page ? (
                <Link href={page} className="font-semibold">
                  {name}
                </Link>
              ) : (
                <span className="font-semibold">{name}</span>
              )}
              <span
                className={
                  line.state === "bad" ? "text-sm font-semibold text-destructive" : "text-sm text-muted-foreground"
                }
              >
                {line.summary}
                {line.since ? ` · ${words.since(formatAgo(line.since, now))}` : ""}
              </span>
            </span>
            <SystemStateChip state={line.state} />
          </li>
        );
      })}
    </ul>
  );
}

export function SystemPagesNav() {
  return (
    <nav aria-label={words.pages} className="flex flex-wrap gap-x-5">
      {SYSTEM_PAGES.map((page) => (
        <Link key={page} href={`/system/${page}/`} className="inline-flex min-h-11 items-center font-semibold">
          {labelOf(words.pageTitles, page)}
        </Link>
      ))}
    </nav>
  );
}
