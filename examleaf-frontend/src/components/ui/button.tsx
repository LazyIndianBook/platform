// .btn (components.md): 44 px tall (52 large), radius 10, Poppins 700; hover darkens 6 %, a 1 px press, the focus
// ring; busy draws a spinner before the label and ignores presses, but is aria-disabled, not disabled: a disabled
// button loses the keyboard focus, which then starts again at the top of the page (accessibility review F1).
// asChild renders the styles on a <Link>.
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";
import { Slot } from "radix-ui";
import * as React from "react";

const buttonCva = cva(
  [
    "inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-btn px-4",
    "cursor-pointer text-center font-head text-[15px] leading-tight font-bold no-underline select-none hover:no-underline",
    "[&_svg]:size-5 [&_svg]:shrink-0",
    "active:not-disabled:not-aria-busy:translate-y-px motion-safe:transition-[translate] motion-safe:duration-150 motion-safe:ease-enter",
    "disabled:cursor-not-allowed disabled:not-aria-busy:opacity-55 aria-disabled:cursor-not-allowed aria-disabled:opacity-55",
    "aria-busy:cursor-progress aria-busy:before:size-4 aria-busy:before:shrink-0 aria-busy:before:rounded-full aria-busy:before:border-2",
    "aria-busy:before:border-current aria-busy:before:border-r-transparent aria-busy:before:content-['']",
    "motion-safe:aria-busy:before:animate-[el-spin_0.8s_linear_infinite]",
  ],
  {
    variants: {
      variant: {
        primary:
          "border-2 border-primary bg-primary text-primary-foreground hover:border-primary-hover hover:bg-primary-hover",
        secondary:
          "border-[1.5px] border-input bg-card text-primary hover:bg-secondary-hover [.band-night_&]:bg-transparent [.band-night_&]:hover:bg-white/8",
        ghost:
          "border-2 border-transparent bg-transparent text-primary hover:bg-secondary-hover [.band-night_&]:hover:bg-white/8",
        destructive:
          "border-2 border-destructive bg-destructive text-destructive-foreground hover:border-destructive-hover hover:bg-destructive-hover",
        accent:
          "border-2 border-accent bg-accent text-accent-foreground hover:border-accent-hover hover:bg-accent-hover",
      },
      size: {
        default: "",
        sm: "px-3 text-sm",
        lg: "min-h-[52px] px-6 text-[17px]",
        icon: "w-11 px-0 [&_svg]:size-[22px]",
      },
      block: { true: "w-full", false: "" },
    },
    defaultVariants: { variant: "primary", size: "default", block: false },
  },
);

/** The classes of a button, merged (a caller's className wins over the variant's): for links styled as buttons. */
function buttonVariants({ className, ...variants }: VariantProps<typeof buttonCva> & { className?: string } = {}) {
  return cn(buttonCva(variants), className);
}

type ButtonProps = React.ComponentProps<"button"> &
  VariantProps<typeof buttonCva> & {
    asChild?: boolean;
    /** A real wait (a request in flight): spinner, aria-busy, aria-disabled; presses (a form's submit too) do nothing. */
    busy?: boolean;
  };

function Button({
  className,
  variant,
  size,
  block,
  asChild = false,
  busy = false,
  disabled,
  onClick,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      data-slot="button"
      className={buttonVariants({ variant, size, block, className })}
      aria-busy={busy || undefined}
      aria-disabled={(busy && !disabled) || undefined}
      disabled={asChild ? undefined : disabled}
      onClick={busy ? (event: React.MouseEvent<HTMLButtonElement>) => event.preventDefault() : onClick}
      {...props}
    />
  );
}

export { Button, buttonVariants };
