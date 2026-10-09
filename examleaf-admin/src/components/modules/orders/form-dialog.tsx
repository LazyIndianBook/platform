"use client";

// A dialog with a small form that does one thing (send by hand, record a payment, decline a return …): its fields
// get the API's error beside them, one submit sends once, and after success a short toast and a fresh render of the
// page. A 202 (approval_required) keeps the dialog open with the change request that was made instead.
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { toast } from "@/components/ui/toaster";
import type { ApiError } from "@/lib/api/errors";
import { copy } from "@/lib/copy";

type FormDialogProps = {
  triggerLabel: string;
  triggerVariant?: "primary" | "secondary" | "destructive" | "ghost";
  title: string;
  text?: React.ReactNode;
  submitLabel: string;
  submitVariant?: "primary" | "destructive";
  /** Field labels by name, for the error summary's links. */
  labels?: Record<string, string>;
  success?: string;
  onSubmit: (form: FormData) => Promise<unknown>;
  onDone?: (result: unknown) => void;
  /** The fields, given the form's id prefix and the current error. */
  children: (prefix: string, error: ApiError | null) => React.ReactNode;
  wide?: boolean;
};

export function FormDialog({
  triggerLabel,
  triggerVariant = "secondary",
  title,
  text,
  submitLabel,
  submitVariant = "primary",
  labels,
  success,
  onSubmit,
  onDone,
  children,
  wide,
}: FormDialogProps) {
  const id = useId();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { run, busy, error, setError } = useAction();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setError(null);
      }}
    >
      <Button size="sm" variant={triggerVariant} onClick={() => setOpen(true)}>
        {triggerLabel}
      </Button>
      <DialogContent className={wide ? "w-[min(44rem,calc(100%-32px))]" : undefined}>
        <DialogHeader>{title}</DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-3.5"
          onSubmit={async (event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            let result: unknown;
            const ok = await run(async () => {
              result = await onSubmit(form);
            });
            if (!ok) return;
            setOpen(false);
            if (success) toast.success(success);
            if (onDone) onDone(result);
            else router.refresh();
          }}
        >
          {text ? (
            <DialogBody>
              <DialogDescription>{text}</DialogDescription>
            </DialogBody>
          ) : null}
          <ErrorSummary error={error} idPrefix={`${id}-`} labels={labels} />
          {children(`${id}-`, error)}
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary">{copy.common.cancel}</Button>
            </DialogClose>
            <Button type="submit" variant={submitVariant} busy={busy}>
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** A text field of a FormData, trimmed. */
export const field = (form: FormData, name: string) => String(form.get(name) ?? "").trim();
