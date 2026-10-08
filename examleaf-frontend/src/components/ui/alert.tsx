// .alert: tint, hairline and icon of its kind, title and text; no side bar. role="status" for news after an action,
// role="alert" only for a form's error summary.
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";
import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import * as React from "react";

const alertVariants = cva(
  "flex items-start gap-3 rounded-lg border p-4 text-foreground [&>svg]:mt-0.5 [&>svg]:size-[22px] [&>svg]:shrink-0",
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

const ICONS = { info: Info, success: CircleCheck, warning: TriangleAlert, error: CircleAlert };

type AlertProps = Omit<React.ComponentProps<"div">, "title"> &
  VariantProps<typeof alertVariants> & { title?: React.ReactNode };

function Alert({ className, variant = "info", title, children, role = "status", ...props }: AlertProps) {
  const Icon = ICONS[variant ?? "info"];
  return (
    <div data-slot="alert" role={role} className={cn(alertVariants({ variant }), className)} {...props}>
      <Icon aria-hidden="true" />
      <div className="flex min-w-0 flex-col gap-1.5 [&_p]:m-0">
        {title ? <p className="font-head text-base leading-snug font-bold">{title}</p> : null}
        {children}
      </div>
    </div>
  );
}

export { Alert, alertVariants };
