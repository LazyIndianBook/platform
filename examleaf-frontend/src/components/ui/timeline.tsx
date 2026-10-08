// .timeline, Direction A (an order's status): a 14 px dot and a hairline per item; done items are navy, the current
// one a red-ink ring with aria-current="step", upcoming ones a pale ring and muted words. Items rise in 40 ms apart
// (six at most) inside the motion wrapper; with reduced motion they are simply there.
import { cn } from "cn";

type TimelineItem = {
  label: string;
  state: "done" | "current" | "upcoming";
  time?: string;
  datetime?: string;
  note?: string;
};

function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <ol className="m-0 list-none p-0">
      {items.map((item, index) => (
        <li
          key={item.label}
          aria-current={item.state === "current" ? "step" : undefined}
          style={{ animationDelay: `${Math.min(index, 5) * 40}ms` }}
          className={cn(
            "relative grid grid-cols-[24px_1fr] gap-x-3.5",
            "motion-safe:animate-[el-rise_220ms_var(--ease-enter)_both]",
            "before:absolute before:top-6 before:bottom-0 before:left-[11px] before:w-[1.5px] before:bg-border before:content-[''] last:before:hidden",
          )}
        >
          <span
            aria-hidden="true"
            className={cn(
              "mt-[7px] ml-[5px] size-3.5 rounded-full border-2 border-border bg-card",
              item.state === "done" && "border-primary bg-primary",
              item.state === "current" && "border-red-ink bg-card",
            )}
          />
          <span className={cn("flex flex-col", index < items.length - 1 && "pb-5")}>
            <strong
              className={cn(
                "text-[17px] leading-7 font-bold",
                item.state === "upcoming" && "font-semibold text-muted-foreground",
              )}
            >
              {item.label}
              <span className="sr-only">
                {item.state === "done" ? ", done" : item.state === "current" ? ", now" : ", next"}
              </span>
            </strong>
            {item.time ? (
              <time dateTime={item.datetime} className="text-[15px] text-muted-foreground">
                {item.time}
              </time>
            ) : null}
            {item.note ? <small className="text-[15px] text-muted-foreground">{item.note}</small> : null}
          </span>
        </li>
      ))}
    </ol>
  );
}

export { Timeline, type TimelineItem };
