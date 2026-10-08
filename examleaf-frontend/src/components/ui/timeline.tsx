// .timeline (an order's status): a 28 px dot and connector per item; done items are filled with a check, the
// current one is an accent ring with aria-current="step", upcoming ones dashed and muted. Items rise in 40 ms apart
// (six at most) inside the motion wrapper.
import { cn } from "cn";
import { Check } from "lucide-react";

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
            "relative grid grid-cols-[28px_1fr] gap-x-4",
            "motion-safe:animate-[el-rise_220ms_var(--ease-enter)_both]",
            "before:absolute before:top-8 before:bottom-1 before:left-[13px] before:w-0.5 before:bg-border before:content-[''] last:before:hidden",
            item.state === "done" && "before:bg-primary",
          )}
        >
          <span
            className={cn(
              "flex size-7 items-center justify-center rounded-full border-2 border-dashed border-input bg-card",
              item.state === "done" && "border-0 bg-primary text-white",
              item.state === "current" &&
                "border-[3px] border-solid border-accent bg-[radial-gradient(circle,var(--accent)_5px,var(--card)_5.5px)]",
            )}
          >
            {item.state === "done" ? <Check aria-hidden="true" className="size-4" /> : null}
          </span>
          <span className={cn("flex flex-col", index < items.length - 1 && "pb-5")}>
            <strong
              className={cn(
                "font-head text-[17px] leading-7 font-bold",
                item.state === "upcoming" && "font-semibold text-muted-foreground",
              )}
            >
              {item.label}
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
