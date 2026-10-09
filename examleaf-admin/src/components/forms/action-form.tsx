"use client";

// A small form that does one thing through the staff API (grant a role, change a setting, log a request): its fields,
// one submit that sends once (busy), the error summary (the API's field errors beside their fields, an approval
// that was asked for instead), a draft kept while typing, and after success a short toast and a fresh render of the
// page from the server. The fields are the children, given the current error; their ids are `${id}-${name}`.
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import type { ApiError } from "@/lib/api/errors";

import { ErrorSummary } from "./error-summary";
import { useAction } from "./use-action";
import { useDraftForm } from "./use-draft";

type ActionFormProps = {
  /** The draft's key and the fields' id prefix: unique on the page. */
  id: string;
  submitLabel: string;
  /** Sends the form; what it returns goes to onDone. */
  onSubmit: (form: FormData) => Promise<unknown>;
  /** The toast after it worked (three words or fewer). */
  success?: string;
  onDone?: (result: unknown) => void;
  labels?: Record<string, string>;
  variant?: "primary" | "secondary" | "destructive";
  className?: string;
  children: (error: ApiError | null) => React.ReactNode;
};

export function ActionForm({
  id,
  submitLabel,
  onSubmit,
  success,
  onDone,
  labels,
  variant = "primary",
  className,
  children,
}: ActionFormProps) {
  const router = useRouter();
  const { ref, save, clear } = useDraftForm(id);
  const { run, busy, error } = useAction();

  return (
    <form
      ref={ref}
      onInput={save}
      noValidate
      className={className ?? "flex max-w-[40rem] flex-col gap-4"}
      onSubmit={async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        let result: unknown;
        const ok = await run(async () => {
          result = await onSubmit(new FormData(form));
        });
        if (!ok) return;
        clear();
        // the form's own reset: a field named "reset" (a setting's "back to the environment's") hides form.reset
        HTMLFormElement.prototype.reset.call(form);
        if (success) toast.success(success);
        onDone?.(result);
        router.refresh();
      }}
    >
      <ErrorSummary error={error} labels={labels} idPrefix={`${id}-`} />
      {children(error)}
      <div>
        <Button type="submit" variant={variant} busy={busy}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

/** A text field of a FormData, trimmed. */
export const formText = (form: FormData, name: string) => String(form.get(name) ?? "").trim();
