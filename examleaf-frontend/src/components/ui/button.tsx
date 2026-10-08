// .btn, Direction A: 44 px tall (52 large), radius 4, Public Sans 700. Primary is navy (the one action colour);
// secondary is an ink outline; press moves 1 px; focus ring 2 + 2 px. Busy draws a spinner, sets aria-busy and
// aria-disabled (not disabled, so focus is not thrown to the top of the page: accessibility review F1) and
// swallows presses, so a form can't be sent twice. API unchanged.
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";
import { Slot } from "radix-ui";
import * as React from "react";

const buttonCva = cva(
  [
    "inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-btn px-5",
    "cursor-pointer text-center font-body text-base leading-tight font-bold no-underline select-none hover:no-underline",
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
          "border-2 border-primary bg-primary text-primary-foreground hover:border-primary-hover hover:bg-primary-hover hover:text-primary-foreground",
        secondary:
          "border-[1.5px] border-foreground bg-transparent text-foreground hover:bg-secondary-hover hover:text-foreground [.band-night_&]:border-input",
        ghost:
          "border-2 border-transparent bg-transparent text-primary underline underline-offset-[3px] hover:text-red-ink",
        destructive:
          "border-2 border-destructive bg-destructive text-destructive-foreground hover:border-destructive-hover hover:bg-destructive-hover hover:text-destructive-foreground",
        accent:
          "border-2 border-accent bg-accent text-accent-foreground hover:border-accent-hover hover:bg-accent-hover hover:text-accent-foreground",
      },
      size: {
        default: "min-h-12",
        sm: "px-4 text-[15px]",
        lg: "min-h-[52px] px-6 text-[17px]",
        icon: "w-11 px-0 [&_svg]:size-[22px]",
      },
      block: { true: "w-full", false: "" },
    },
    defaultVariants: { variant: "primary", size: "default", block: false },
  },
);

function buttonVariants({ className, ...variants }: VariantProps<typeof buttonCva> & { className?: string } = {}) {
  return cn(buttonCva(variants), className);
}

type ButtonProps = React.ComponentProps<"button"> &
  VariantProps<typeof buttonCva> & {
    asChild?: boolean;
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
