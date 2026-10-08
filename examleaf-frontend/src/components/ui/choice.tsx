// Checkbox, radio and switch: native inputs (they work before any script, in any form), 22 px with the primary
// accent, inside a 44 px label row whose text is the full sentence. SelectableCard: a radio or checkbox as a card
// (addresses, payment methods): 2 px primary border when checked, padding adjusted so nothing shifts.
import { cn } from "cn";
import * as React from "react";

type ChoiceProps = Omit<React.ComponentProps<"input">, "type"> & {
  children?: React.ReactNode;
  labelClassName?: string;
};

const rowClasses = "flex min-h-11 cursor-pointer items-center gap-3 text-base leading-relaxed font-normal";
const boxClasses = "size-[22px] shrink-0 cursor-pointer accent-primary";

function Checkbox({ children, className, labelClassName, ...props }: ChoiceProps) {
  return (
    <label className={cn(rowClasses, labelClassName)}>
      <input type="checkbox" data-slot="checkbox" className={cn(boxClasses, className)} {...props} />
      {children}
    </label>
  );
}

function Radio({ children, className, labelClassName, ...props }: ChoiceProps) {
  return (
    <label className={cn(rowClasses, labelClassName)}>
      <input type="radio" data-slot="radio" className={cn(boxClasses, className)} {...props} />
      {children}
    </label>
  );
}

/** role="switch": 48×28 track, --input off, --accent on, the knob drawn by a gradient (no extra element). */
function Switch({ children, className, labelClassName, ...props }: ChoiceProps) {
  return (
    <label className={cn("flex min-h-11 cursor-pointer items-center justify-between gap-4", labelClassName)}>
      <span>{children}</span>
      <input
        type="checkbox"
        role="switch"
        data-slot="switch"
        className={cn(
          "h-7 w-12 shrink-0 cursor-pointer appearance-none rounded-pill",
          "bg-input bg-[radial-gradient(circle_at_14px_14px,#fff_10px,transparent_10.5px)]",
          "checked:bg-accent checked:bg-[radial-gradient(circle_at_34px_14px,#fff_10px,transparent_10.5px)]",
          className,
        )}
        {...props}
      />
    </label>
  );
}

function SelectableCard({
  type = "radio",
  children,
  className,
  ...props
}: Omit<React.ComponentProps<"input">, "type"> & { type?: "radio" | "checkbox" }) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-card p-4",
        "hover:not-has-checked:border-input has-checked:border-2 has-checked:border-primary has-checked:p-[15px]",
        "has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring",
        className,
      )}
    >
      <input type={type} className={cn(boxClasses, "mt-0.5")} {...props} />
      <span className="flex min-w-0 flex-col gap-0.5">{children}</span>
    </label>
  );
}

export { Checkbox, Radio, SelectableCard, Switch };
