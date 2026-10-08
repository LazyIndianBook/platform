// .stepper (checkout: Address → Delivery → Payment → Done): a 4 px bar on top of each step, done steps link back with
// a check, the current one says aria-current="step" and its bar draws in (motion wrapper). On phones only the
// current step keeps its words; the others show their number, the label kept for screen readers.
import { cn } from "cn";
import { Check } from "lucide-react";
import Link from "next/link";

type Step = { label: string; href?: string };

function Stepper({ steps, current, label }: { steps: Step[]; current: number; label: string }) {
  return (
    <ol aria-label={label} className="m-0 mb-6 flex list-none gap-2 p-0">
      {steps.map((step, index) => {
        const done = index < current;
        const isCurrent = index === current;
        const text = `${index + 1}. ${step.label}`;
        const words = isCurrent ? (
          text
        ) : (
          <>
            <span className="max-nav:sr-only">{text}</span>
            <span aria-hidden="true" className="nav:hidden">
              {index + 1}
            </span>
          </>
        );
        return (
          <li
            key={step.label}
            className={cn(
              "relative flex min-h-11 flex-1 items-center border-t-4 border-border pt-1 font-head text-[15px] leading-tight font-semibold text-muted-foreground",
              (done || isCurrent) &&
                "after:absolute after:inset-x-0 after:-top-1 after:h-1 after:bg-primary after:content-['']",
              done && "text-foreground",
              isCurrent &&
                "font-bold text-primary motion-safe:after:origin-left motion-safe:after:animate-[el-draw_220ms_var(--ease-enter)_both]",
            )}
          >
            {done && step.href ? (
              <Link href={step.href} className="inline-flex min-h-11 items-center gap-1.5 text-inherit">
                <Check aria-hidden="true" className="size-[18px] text-accent" />
                {words}
              </Link>
            ) : (
              <span className="inline-flex min-h-11 items-center gap-1.5" aria-current={isCurrent ? "step" : undefined}>
                {words}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export { Stepper, type Step };
