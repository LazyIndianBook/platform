// .input: 48 px, 1.5 px --input border (3.7:1), radius 12, 16 px text (no zoom on iOS). Invalid: a red border and the
// error linked by aria-describedby (Field does it). InputPrefix: "+91" in a muted cell before a borderless input.
import { cn } from "cn";
import * as React from "react";

export const controlClasses = [
  "w-full min-w-0 min-h-12 rounded-lg border-[1.5px] border-input bg-card px-3.5 font-body text-base leading-normal text-foreground",
  "hover:not-disabled:not-focus:border-foreground",
  "aria-invalid:border-destructive aria-invalid:shadow-[inset_0_0_0_0.5px_var(--destructive)] user-invalid:border-destructive",
  "disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground",
];

function Input({ className, type = "text", ...props }: React.ComponentProps<"input">) {
  return <input type={type} data-slot="input" className={cn(controlClasses, className)} {...props} />;
}

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(controlClasses, "min-h-24 resize-y py-3 leading-[1.7]", className)}
      {...props}
    />
  );
}

function InputPrefix({ prefix, className, ...props }: React.ComponentProps<"input"> & { prefix: string }) {
  return (
    <div
      className={cn(
        "flex min-h-12 overflow-hidden rounded-lg border-[1.5px] border-input bg-card",
        "focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring has-aria-invalid:border-destructive",
      )}
    >
      <span aria-hidden="true" className="flex items-center border-r border-border bg-muted px-3 font-semibold">
        {prefix}
      </span>
      <input
        data-slot="input"
        className={cn(
          "min-w-0 flex-1 border-0 bg-transparent px-3.5 font-body text-base text-foreground focus-visible:outline-none",
          className,
        )}
        {...props}
      />
    </div>
  );
}

export { Input, InputPrefix, Textarea };
