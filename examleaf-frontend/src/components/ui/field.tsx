// .field, Direction A (Components board, 04): the label in Public Sans 600 15 (a star for required, "(optional)" in
// muted), the control, help under it in 14, the error under that: 600 14 in the error red after a filled "!" (never
// red ink). Field gives the control its id, aria-describedby (help and error) and aria-invalid, so callers write the
// control only. A disabled control greys its label and help, and the help says why ("Disabled: set by your book").
// FieldSet/FieldLegend: a group on a white sheet, its number in the margin's red mono ("1 About you").
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
    <div data-slot="field" className={cn("group/field flex min-w-0 flex-col gap-1.5", className)}>
      <label
        htmlFor={id}
        className="text-[15px] leading-snug font-semibold text-foreground group-has-disabled/field:text-input"
      >
        {label}
        {required ? (
          <span aria-hidden="true" className="text-destructive">
            {" "}
            *
          </span>
        ) : null}
        {optional ? (
          <span className="font-normal text-muted-foreground group-has-disabled/field:text-input"> (optional)</span>
        ) : null}
      </label>
      {control}
      {help ? (
        <p
          id={`${id}-help`}
          className="m-0 text-sm leading-normal text-muted-foreground group-has-disabled/field:text-input"
        >
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
      className={cn("m-0 flex items-start gap-1.5 text-sm leading-snug font-semibold text-destructive", className)}
      {...props}
    >
      <CircleAlert aria-hidden="true" className="icon-filled mt-px size-[18px] shrink-0" />
      <span>{children}</span>
    </p>
  );
}

function FieldSet({ className, ...props }: React.ComponentProps<"fieldset">) {
  return <fieldset className={cn("m-0 min-w-0 rounded-lg border border-border bg-card p-5", className)} {...props} />;
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
        "flex items-baseline gap-2.5 px-1.5 font-head text-lg leading-snug font-semibold text-heading",
        className,
      )}
    >
      {number ? (
        <span aria-hidden="true" className="font-mono text-[15px] font-semibold text-red-ink">
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
