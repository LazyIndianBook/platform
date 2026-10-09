"use client";

// A form in a dialog for one action of the connections, the templates and the system's pages (replace a provider's
// keys, switch its mode, hold its circuit, rotate a webhook token, record a restore drill): its fields as children,
// one submit that sends once, the API's field errors beside their fields, then a toast and a fresh render of the page
// from the server (or `onDone`, which gets what the call answered: a new token shown once). The fields' ids are
// `${id}-${name}`; nothing typed is kept as a draft (a key or a password must never land in storage).
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
  success?: string;
  labels?: Record<string, string>;
  onSubmit: (form: FormData) => Promise<unknown>;
  onDone?: (result: unknown) => void;
  disabled?: boolean;
  children: (error: ApiError | null, id: string) => React.ReactNode;
};

export function FormDialog({
  triggerLabel,
  triggerVariant = "secondary",
  title,
  text,
  submitLabel,
  submitVariant = "primary",
  success,
  labels,
  onSubmit,
  onDone,
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
        if (!next) setError(null);
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
            router.refresh();
          }}
        >
          {text ? (
            <DialogBody>
              <DialogDescription>{text}</DialogDescription>
            </DialogBody>
          ) : null}
          <ErrorSummary error={error} idPrefix={`${id}-`} labels={{ reason: copy.common.reason, ...labels }} />
          {children(error, id)}
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
export const formValue = (form: FormData, name: string) => String(form.get(name) ?? "").trim();
