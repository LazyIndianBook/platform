// .alert, Direction A (Components board, 05): the tint and hairline of its kind, its icon a filled circle in the
// kind's colour with the sign in white (i, ✓, !, ×: the lucide set, filled by .icon-filled in globals.css), the title
// in Public Sans 700 and the text in 15 px; no side bar. role="status" for news after an action, role="alert" only for
// a form's error summary. API unchanged.
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";
import { CircleAlert, CircleCheck, CircleX, Info } from "lucide-react";
import * as React from "react";

const alertVariants = cva(
  "grid grid-cols-[28px_minmax(0,1fr)] items-start gap-3 rounded-lg border px-4 py-3.5 text-foreground",
  {
    variants: {
      variant: {
        info: "border-info-line bg-info-bg [&>svg]:text-info-fg",
        success: "border-success-line bg-success-bg [&>svg]:text-success-fg",
        warning: "border-warning-line bg-warning-bg [&>svg]:text-warning-fg",
        error: "border-error-line bg-error-bg [&>svg]:text-error-fg",
      },
    },
    defaultVariants: { variant: "info" },
  },
);

const ICONS = { info: Info, success: CircleCheck, warning: CircleAlert, error: CircleX };

type AlertProps = Omit<React.ComponentProps<"div">, "title"> &
  VariantProps<typeof alertVariants> & { title?: React.ReactNode };

function Alert({ className, variant = "info", title, children, role = "status", ...props }: AlertProps) {
  const Icon = ICONS[variant ?? "info"];
  return (
    <div data-slot="alert" role={role} className={cn(alertVariants({ variant }), className)} {...props}>
      <Icon aria-hidden="true" className="icon-filled size-6" />
      <div className="flex min-w-0 flex-col gap-0.5 text-[15px] leading-[1.55] text-[#3e4454] [&_p]:m-0">
        {title ? <p className="text-base leading-snug font-bold text-foreground">{title}</p> : null}
        {children}
      </div>
    </div>
  );
}

export { Alert, alertVariants };
