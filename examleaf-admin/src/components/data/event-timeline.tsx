// A record's timeline: its audit events, newest first (who did what, when, why, and what changed), as the kit's
// timeline draws a sequence: a 28 px column with a dot and a hairline down to the next item. Nothing animates here.
import { cn } from "cn";

import type { AuditEvent } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

export function actorLabel(event: Pick<AuditEvent, "actor">): string {
  const { actor } = event;
  return actor.name || actor.email || labelOf(copy.audit.actorTypes, actor.type);
}

export function EventTimeline({ events, label }: { events: AuditEvent[]; label: string }) {
  if (!events.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.common.none}</p>;
  return (
    <ol aria-label={label} className="m-0 list-none p-0">
      {events.map((event, index) => (
        <li
          key={event.id}
          className={cn(
            "relative grid grid-cols-[20px_minmax(0,1fr)] gap-x-2.5",
            "before:absolute before:top-[16px] before:bottom-0 before:left-[8.25px] before:w-[1.5px] before:bg-border before:content-[''] last:before:hidden",
          )}
        >
          <span
            aria-hidden="true"
            className={cn(
              "mt-1 ml-[2px] size-3.5 rounded-full border-2 border-primary bg-card",
              event.outcome !== "success" && "border-destructive",
            )}
          />
          <div className={cn("flex min-w-0 flex-col gap-0.5 text-[15px]", index < events.length - 1 && "pb-4")}>
            <span className="font-mono text-[13px] break-all">{event.action}</span>
            <span>
              {actorLabel(event)}
              {event.outcome !== "success" ? (
                <span className="font-semibold text-destructive"> · {labelOf(copy.audit.outcomes, event.outcome)}</span>
              ) : null}
            </span>
            {event.reason ? <span className="text-muted-foreground">“{event.reason}”</span> : null}
            <time dateTime={event.ts} className="text-sm text-muted-foreground">
              {formatDateTime(event.ts)}
            </time>
          </div>
        </li>
      ))}
    </ol>
  );
}
