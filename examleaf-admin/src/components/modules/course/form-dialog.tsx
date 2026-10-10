"use client";

// A dialog holding a short form (a move, a comment, a time, a number of days): the kit's native dialog, its fields
// given the API's error, one send (busy), the error summary, then a short toast and a fresh render of the page (or
// onDone instead). ConfirmDialog asks a question; this one asks for values.
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
  DialogTrigger,
} from "@/components/ui/dialog";
import { toast } from "@/components/ui/toaster";
import type { ApiError } from "@/lib/api/errors";
import { copy } from "@/lib/copy";

type FormDialogProps = {
  triggerLabel: React.ReactNode;
  triggerVariant?: "primary" | "secondary" | "destructive" | "ghost";
  title: string;
  text?: React.ReactNode;
  submitLabel: string;
  submitVariant?: "primary" | "destructive";
  /** The fields' names in the error summary. */
  labels?: Record<string, string>;
  success?: string;
  onSubmit: (form: FormData) => Promise<unknown>;
  onDone?: (result: unknown) => void;
  /** When it opens: what the form needs loaded (a card's text). */
  onOpen?: () => void;
  disabled?: boolean;
  /** The fields; their ids are `${id}-${name}`. */
  children: (id: string, error: ApiError | null) => React.ReactNode;
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
  onOpen,
  disabled,
  children,
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
        if (next) onOpen?.();
        else setError(null);
      }}
    >
      <DialogTrigger asChild>
        <Button variant={triggerVariant} size="sm" disabled={disabled}>
          {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent>
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
          <ErrorSummary error={error} labels={labels} idPrefix={`${id}-`} />
          {open ? children(id, error) : null}
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
