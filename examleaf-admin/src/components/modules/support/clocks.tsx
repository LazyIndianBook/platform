// A ticket's legal deadlines as the API computes them (its `clocks`, earliest first): each with the rule it comes from,
// counting down while it runs (gold in its last quarter, red once late), or met or missed once it stopped (an
// acknowledgement's at the acknowledgement, the others at the resolution). Drawn by the server; the countdowns move
// in the browser.
import { Clock } from "@/components/data/clock";
import type { TicketRecord } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

const RUNNING = new Set(["new", "open", "waiting_customer", "waiting_third_party"]);

export function TicketClocks({ ticket, now }: { ticket: TicketRecord; now: number }) {
  const running = RUNNING.has(ticket.status);
  return (
    <ul className="m-0 flex list-none flex-col gap-3 p-0">
      {ticket.clocks.map((clock) => (
        <li key={clock.name} className="flex flex-col gap-1 border-l-2 border-border pl-3">
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-[15px] font-semibold">{labelOf(copy.support.clockNames, clock.name)}</span>
            {clock.stopped_at ? (
              <span className={clock.breached ? "text-[15px] font-semibold text-destructive" : "text-[15px]"}>
                {clock.breached
                  ? copy.support.clockMissed(formatDateTime(clock.stopped_at))
                  : copy.support.clockMet(formatDateTime(clock.stopped_at))}
              </span>
            ) : running ? (
              <Clock
                label={labelOf(copy.support.clockNames, clock.name)}
                start={ticket.received_at}
                due={clock.due}
                now={now}
                compact
              />
            ) : null}
            <span className="font-mono text-xs text-muted-foreground">{formatDateTime(clock.due)}</span>
          </span>
          <span className="text-sm text-muted-foreground">{clock.rule}</span>
        </li>
      ))}
    </ul>
  );
}
