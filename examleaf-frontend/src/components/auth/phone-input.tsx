// The mobile number box of the Login boards: "+91" in IBM Plex Mono in a cell of its own with a hairline after it, then
// the number, 52 px high. Field gives the control its id and aria-*, which land on the input.
import { cn } from "cn";

export function PhoneInput({ className, ...props }: Omit<React.ComponentProps<"input">, "type">) {
  return (
    <div
      className={cn(
        "flex min-h-13 overflow-hidden rounded-lg border-[1.5px] border-input bg-card",
        "focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring has-aria-invalid:border-destructive",
      )}
    >
      <span aria-hidden="true" className="flex items-center border-r border-border px-3 font-mono">
        +91
      </span>
      <input
        data-slot="input"
        type="tel"
        inputMode="tel"
        autoComplete="tel-national"
        placeholder="98765 43210"
        className={cn(
          "min-w-0 flex-1 border-0 bg-transparent px-3 font-mono text-base text-foreground focus-visible:outline-none",
          className,
        )}
        {...props}
      />
    </div>
  );
}
