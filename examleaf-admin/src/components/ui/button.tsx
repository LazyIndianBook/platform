// .btn, Direction A (Components board, 03): Public Sans 700, radius 4; md 48 px tall, lg 52, sm 44 (never smaller).
// Primary navy, ink on hover and press; secondary an ink outline, paper 2 on hover; destructive the error red; ghost
// the link style. Press moves 1 px; focus ring 2 + 2 px (globals.css). Busy keeps the button's colour, draws a 14 px
// ring before the label, sets aria-busy and aria-disabled (not disabled, so focus is not thrown to the top of the
// page: accessibility review F1) and swallows presses, so a form can't be sent twice. Disabled (or aria-disabled while
// not busy) is the board's flat grey of each variant: the `live` and `off` variants of globals.css. Only a
// type="submit" button sends its form: the type is "button" unless said (HTML's default, submit, made every Cancel in a
// dialog's form send it).
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";
import { Slot } from "radix-ui";
import * as React from "react";

const buttonCva = cva(
  [
    "inline-flex min-h-11 shrink-0 items-center justify-center gap-2.5 rounded-btn px-5",
    "cursor-pointer text-center font-body text-base leading-tight font-bold no-underline select-none hover:no-underline",
    "[&_svg]:size-5 [&_svg]:shrink-0",
    "motion-safe:transition-[translate] motion-safe:duration-150 motion-safe:ease-enter active:live:translate-y-px",
    "off:cursor-not-allowed",
    "aria-busy:cursor-progress aria-busy:before:size-3.5 aria-busy:before:shrink-0 aria-busy:before:rounded-full aria-busy:before:border-2",
    "aria-busy:before:border-current/35 aria-busy:before:border-t-current aria-busy:before:content-['']",
    "motion-safe:aria-busy:before:animate-[el-spin_0.8s_linear_infinite]",
  ],
  {
    variants: {
      variant: {
        primary: [
          "border-2 border-primary bg-primary text-primary-foreground hover:text-primary-foreground",
          "hover:live:border-primary-hover hover:live:bg-primary-hover active:live:border-primary-hover active:live:bg-primary-hover",
          "off:border-[#c9ccd2] off:bg-[#c9ccd2] off:text-[#4a5060]",
        ],
        secondary: [
          "border-[1.5px] border-foreground bg-transparent text-foreground hover:text-foreground [.band-night_&]:border-input",
          "hover:live:bg-secondary active:live:bg-secondary-hover",
          "aria-busy:before:border-border aria-busy:before:border-t-foreground",
          "off:border-[#b9bcc3] off:bg-transparent off:text-input",
        ],
        ghost: [
          "border-2 border-transparent bg-transparent text-primary underline underline-offset-[3px] hover:text-red-ink",
          "active:live:text-foreground active:live:no-underline off:text-input off:no-underline",
        ],
        destructive: [
          "border-2 border-destructive bg-destructive text-destructive-foreground hover:text-destructive-foreground",
          "hover:live:border-destructive-hover hover:live:bg-destructive-hover active:live:border-destructive-hover active:live:bg-destructive-hover",
          "off:border-[#e9c9c5] off:bg-[#e9c9c5] off:text-[#7a3a33]",
        ],
        accent: [
          "border-2 border-accent bg-accent text-accent-foreground hover:text-accent-foreground",
          "hover:live:border-accent-hover hover:live:bg-accent-hover active:live:border-accent-hover active:live:bg-accent-hover",
          "off:border-[#c9ccd2] off:bg-[#c9ccd2] off:text-[#4a5060]",
        ],
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
  type = "button",
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
      type={asChild ? undefined : type}
      onClick={busy ? (event: React.MouseEvent<HTMLButtonElement>) => event.preventDefault() : onClick}
      {...props}
    />
  );
}

export { Button, buttonVariants };
