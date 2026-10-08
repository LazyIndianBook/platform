// .input, Direction A (Components board, 04): 48 px, white on paper, a 1.5 px control border (#7B8595, 3.7:1), radius
// 4, 16 px text (no zoom on iOS); focus turns the border navy inside the green ring; invalid is a 2 px error-red border
// (the 0.5 px inset keeps the box from moving) with the message linked by aria-describedby (Field does it); disabled
// is paper 2 with a pale border. Mono where the caller asks (className="font-mono": codes, marks). InputPrefix: "+91"
// in a paper 2 cell before a borderless input, the box taking the input's states.
import { cn } from "cn";
import * as React from "react";

export const controlClasses = [
  "w-full min-w-0 min-h-12 rounded-lg border-[1.5px] border-input bg-card px-3.5 font-body text-base leading-normal text-foreground",
  "hover:not-disabled:not-focus:not-aria-invalid:border-foreground focus-visible:border-primary",
  "aria-invalid:border-destructive aria-invalid:shadow-[inset_0_0_0_0.5px_var(--destructive)] user-invalid:border-destructive",
  "disabled:cursor-not-allowed disabled:border-[#c9ccd2] disabled:bg-paper-2 disabled:text-input",
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
        "group/prefix flex min-h-12 overflow-hidden rounded-lg border-[1.5px] border-input bg-card",
        "focus-within:border-primary focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring",
        "has-aria-invalid:border-destructive has-aria-invalid:shadow-[inset_0_0_0_0.5px_var(--destructive)]",
        "has-disabled:border-[#c9ccd2] has-disabled:bg-paper-2",
      )}
    >
      <span
        aria-hidden="true"
        className="flex items-center border-r border-border bg-paper-2 px-3 font-semibold group-has-disabled/prefix:text-input"
      >
        {prefix}
      </span>
      <input
        data-slot="input"
        className={cn(
          "min-w-0 flex-1 border-0 bg-transparent px-3.5 font-body text-base text-foreground focus-visible:outline-none",
          "disabled:cursor-not-allowed disabled:text-input",
          className,
        )}
        {...props}
      />
    </div>
  );
}

export { Input, InputPrefix, Textarea };
