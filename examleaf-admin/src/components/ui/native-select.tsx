// .select, Direction A: the native <select> (the phone's own picker, no script) in the input's box and states, with a
// 20 px chevron that greys with it when disabled ("Disabled: set by your book").
import { cn } from "cn";
import { ChevronDown } from "lucide-react";
import * as React from "react";

import { controlClasses } from "./input";

function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <div className="relative w-full" data-slot="select-wrapper">
      <select
        data-slot="select"
        className={cn(controlClasses, "peer cursor-pointer appearance-none pr-11", className)}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute top-3.5 right-3.5 size-5 text-muted-foreground peer-disabled:text-input"
      />
    </div>
  );
}

export { Select };
