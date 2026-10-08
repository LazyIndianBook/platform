// Checkbox, radio and switch, Direction A (Components board, 04): native inputs (they work before any script, in any
// form) drawn as the board draws them by globals.css ("choice controls", keyed on data-slot): 22 px boxes with a
// control border, navy when checked; the switch a 44×26 track. The label is the full sentence and the whole row is
// the target (at least 44 px). SelectableCard, the choice card (product options, addresses, payment methods): a white
// sheet with a hairline, a 2 px ink border when chosen (padding adjusted, so nothing moves), what it costs in `end`
// at the right (under the words when the card is narrow); a BEST VALUE chip (Badge variant="gold") goes in the
// caller's label row. Disabled greys the row.
import { cn } from "cn";
import * as React from "react";

type ChoiceProps = Omit<React.ComponentProps<"input">, "type"> & {
  children?: React.ReactNode;
  labelClassName?: string;
};

const rowClasses =
  "flex cursor-pointer items-start gap-3 py-[9px] text-base leading-relaxed font-normal has-disabled:cursor-not-allowed has-disabled:text-input";

function Checkbox({ children, className, labelClassName, ...props }: ChoiceProps) {
  return (
    <label className={cn(rowClasses, labelClassName)}>
      <input type="checkbox" data-slot="checkbox" className={cn("mt-0.5", className)} {...props} />
      {children}
    </label>
  );
}

function Radio({ children, className, labelClassName, ...props }: ChoiceProps) {
  return (
    <label className={cn(rowClasses, labelClassName)}>
      <input type="radio" data-slot="radio" className={cn("mt-0.5", className)} {...props} />
      {children}
    </label>
  );
}

/** role="switch": the 44×26 track before its words; off is the control grey, on is navy, the knob drawn in CSS. */
function Switch({ children, className, labelClassName, ...props }: ChoiceProps) {
  return (
    <label className={cn(rowClasses, labelClassName)}>
      <input type="checkbox" role="switch" data-slot="switch" className={className} {...props} />
      <span className="min-w-0">{children}</span>
    </label>
  );
}

function SelectableCard({
  type = "radio",
  children,
  className,
  end,
  ...props
}: Omit<React.ComponentProps<"input">, "type"> & {
  type?: "radio" | "checkbox";
  /** At the right of the card: the option's price. */
  end?: React.ReactNode;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer flex-wrap items-start gap-x-3.5 gap-y-2 rounded-lg border border-border bg-card px-[18px] py-4",
        "hover:not-has-checked:not-has-disabled:border-input",
        "has-checked:border-2 has-checked:border-foreground has-checked:px-[17px] has-checked:py-[15px]",
        "has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring",
        "has-disabled:cursor-not-allowed has-disabled:border-[#c9ccd2] has-disabled:bg-paper-2 has-disabled:text-input",
        className,
      )}
    >
      <input type={type} data-slot={type} className="mt-0.5" {...props} />
      <span className="flex min-w-40 flex-1 flex-col gap-0.5">{children}</span>
      {end ? <span className="ml-auto self-center">{end}</span> : null}
    </label>
  );
}

export { Checkbox, Radio, SelectableCard, Switch };
