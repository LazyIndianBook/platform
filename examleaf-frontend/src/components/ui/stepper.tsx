// .stepper, Direction A (Components board, 06; "Checkout", "Phone checkout"): Address → Delivery → Payment → Done, a
// 4 px bar per step and its word 8 px under it. Done steps are navy with ink words (a link back while the order can
// still change); the current one is red ink with bold words and aria-current="step", and its bar draws in once (motion
// wrapper); the rest keep the hairline colour and muted words. 14 px words, 12 px on a phone. The word shown is the
// step's name; screen readers hear its number with it ("2. Delivery").
import { cn } from "cn";
import Link from "next/link";

type Step = { label: string; href?: string };

function Stepper({ steps, current, label }: { steps: Step[]; current: number; label: string }) {
  return (
    <ol aria-label={label} className="m-0 mb-6 flex list-none gap-1 p-0 nav:gap-1.5">
      {steps.map((step, index) => {
        const done = index < current;
        const isCurrent = index === current;
        const words = (
          <>
            <span className="sr-only">{`${index + 1}. ${step.label}`}</span>
            <span aria-hidden="true">{step.label}</span>
          </>
        );
        return (
          <li
            key={step.label}
            className={cn(
              "relative min-w-0 flex-1 border-t-4 border-border pt-1.5 font-body text-xs leading-tight font-medium text-muted-foreground nav:pt-2 nav:text-sm",
              (done || isCurrent) && "after:absolute after:inset-x-0 after:-top-1 after:h-1 after:content-['']",
              done && "text-foreground after:bg-primary",
              isCurrent &&
                "font-bold text-foreground after:bg-red-ink motion-safe:after:origin-left motion-safe:after:animate-[el-draw_220ms_var(--ease-enter)_both]",
            )}
          >
            {done && step.href ? (
              <Link
                href={step.href}
                className="inline-flex min-h-11 items-start text-inherit no-underline hover:text-red-ink hover:underline"
              >
                {words}
              </Link>
            ) : (
              <span className="inline-block" aria-current={isCurrent ? "step" : undefined}>
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
