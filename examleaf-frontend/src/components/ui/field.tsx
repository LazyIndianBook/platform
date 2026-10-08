// .field: label (600 16/1.4, a red star for required), the control, help under it, the error with an icon. Field
// gives the control its id, aria-describedby (help and error) and aria-invalid, so callers write the control only.
// FieldSet/FieldLegend: the numbered fieldsets of the Register page ("1 About you").
import { cn } from "cn";
import { CircleAlert } from "lucide-react";
import * as React from "react";

type FieldProps = {
  id: string;
  label: React.ReactNode;
  required?: boolean;
  optional?: boolean;
  help?: React.ReactNode;
  error?: string | string[] | null;
  className?: string;
  /** One control: it receives id, aria-describedby and aria-invalid. */
  children: React.ReactElement<Record<string, unknown>>;
};

function Field({ id, label, required, optional, help, error, className, children }: FieldProps) {
  const errors = (Array.isArray(error) ? error : error ? [error] : []).filter(Boolean);
  const describedBy = [help ? `${id}-help` : "", errors.length ? `${id}-error` : ""].filter(Boolean).join(" ");
  const control = React.cloneElement(children, {
    id,
    required: required || undefined,
    "aria-invalid": errors.length ? true : undefined,
    "aria-describedby": describedBy || undefined,
  });
  return (
    <div data-slot="field" className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-base leading-snug font-semibold text-foreground">
        {label}
        {required ? (
          <span aria-hidden="true" className="text-destructive">
            {" "}
            *
          </span>
        ) : null}
        {optional ? <span className="font-normal text-muted-foreground"> (optional)</span> : null}
      </label>
      {control}
      {help ? (
        <p id={`${id}-help`} className="m-0 text-sm leading-relaxed text-muted-foreground">
          {help}
        </p>
      ) : null}
      {errors.length ? <FieldError id={`${id}-error`}>{errors.join(" ")}</FieldError> : null}
    </div>
  );
}

function FieldError({ className, children, ...props }: React.ComponentProps<"p">) {
  return (
    <p
      data-slot="field-error"
      className={cn(
        "m-0 flex items-start gap-1.5 text-[15px] leading-normal font-semibold text-destructive",
        className,
      )}
      {...props}
    >
      <CircleAlert aria-hidden="true" className="mt-0.5 size-[18px] shrink-0" />
      <span>{children}</span>
    </p>
  );
}

function FieldSet({ className, ...props }: React.ComponentProps<"fieldset">) {
  return <fieldset className={cn("m-0 min-w-0 rounded-lg border border-border p-4", className)} {...props} />;
}

function FieldLegend({
  number,
  children,
  className,
}: {
  number?: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <legend
      className={cn(
        "flex items-center gap-2 px-1.5 font-head text-[17px] leading-snug font-bold text-heading",
        className,
      )}
    >
      {number ? (
        <span
          aria-hidden="true"
          className="inline-flex size-7 items-center justify-center rounded-full bg-primary text-sm text-primary-foreground"
        >
          {number}
        </span>
      ) : null}
      {children}
    </legend>
  );
}

/** The form grid: rows 16 px apart, columns 20 px, at least 220 px wide (one column on a phone). */
function FormGrid({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "grid grid-cols-[repeat(auto-fit,minmax(min(var(--min,220px),100%),1fr))] gap-x-5 gap-y-4",
        className,
      )}
      {...props}
    />
  );
}

export { Field, FieldError, FieldLegend, FieldSet, FormGrid };
