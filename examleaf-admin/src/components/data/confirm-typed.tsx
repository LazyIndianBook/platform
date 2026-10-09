"use client";

// Guards chosen by the damage an action can do (research, admin UX 6.4): ConfirmDialog asks once ("Revoke the role?"),
// optionally with a reason for the audit trail; ConfirmTyped makes the person type the record's label first (GitHub's
// danger zone) for what is wide or cannot be undone: offboarding, revoking a key, signing in as a customer. The
// dialog is the kit's native <dialog>: it opens on its safe button, Escape and the backdrop close it.
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
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
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { copy } from "@/lib/copy";

type ConfirmProps = {
  triggerLabel: React.ReactNode;
  triggerVariant?: "primary" | "secondary" | "destructive" | "ghost";
  title: string;
  text: React.ReactNode;
  confirmLabel: string;
  confirmVariant?: "primary" | "destructive";
  /** Ask for a reason (saved in the audit trail with the action). */
  reason?: boolean;
  reasonHelp?: string;
  /** More short fields the action needs (a ticket number), before the reason. */
  fields?: { name: string; label: string; help?: string }[];
  /** The words the person types to confirm (the record's label). */
  typed?: string;
  success?: string;
  onConfirm: (input: { reason: string; values: Record<string, string> }) => Promise<unknown>;
  /** After it worked, instead of a fresh render of the page. */
  onDone?: (result: unknown) => void;
  disabled?: boolean;
};

export function ConfirmDialog({
  triggerLabel,
  triggerVariant = "secondary",
  title,
  text,
  confirmLabel,
  confirmVariant = "destructive",
  reason = false,
  reasonHelp,
  fields = [],
  typed,
  success,
  onConfirm,
  onDone,
  disabled,
}: ConfirmProps) {
  const id = useId();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const { run, busy, error, setError } = useAction();
  const matches = !typed || value.trim() === typed;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setValue("");
          setError(null);
        }
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
            if (!matches) return;
            const form = new FormData(event.currentTarget);
            const given = String(form.get("reason") ?? "").trim();
            const values = Object.fromEntries(
              fields.map((field) => [field.name, String(form.get(field.name) ?? "").trim()]),
            );
            let result: unknown;
            const ok = await run(async () => {
              result = await onConfirm({ reason: given, values });
            });
            if (!ok) return;
            setOpen(false);
            setValue("");
            if (success) toast.success(success);
            if (onDone) onDone(result);
            else router.refresh();
          }}
        >
          <DialogBody>
            <DialogDescription>{text}</DialogDescription>
          </DialogBody>
          <ErrorSummary
            error={error}
            idPrefix={`${id}-`}
            labels={{
              reason: copy.common.reason,
              ...Object.fromEntries(fields.map((field) => [field.name, field.label])),
            }}
          />
          {fields.map((field) => (
            <Field
              key={field.name}
              id={`${id}-${field.name}`}
              label={field.label}
              help={field.help}
              error={fieldError(error, field.name)}
            >
              <Input name={field.name} autoComplete="off" aria-required="true" />
            </Field>
          ))}
          {reason ? (
            <Field
              id={`${id}-reason`}
              label={copy.common.reason}
              help={reasonHelp ?? copy.common.reasonHelp}
              error={fieldError(error, "reason")}
            >
              <Textarea name="reason" rows={3} aria-required="true" />
            </Field>
          ) : null}
          {typed ? (
            <Field
              id={`${id}-typed`}
              label={copy.confirmTyped.instruction(typed)}
              error={value && !matches ? copy.confirmTyped.mismatch : null}
            >
              <Input
                name="typed"
                value={value}
                onChange={(event) => setValue(event.target.value)}
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
                data-no-draft=""
                className="font-mono"
              />
            </Field>
          ) : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary">{copy.common.cancel}</Button>
            </DialogClose>
            <Button type="submit" variant={confirmVariant} busy={busy} disabled={!matches}>
              {confirmLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** The typed confirmation: the person types `label` before the action runs. */
export function ConfirmTyped(props: Omit<ConfirmProps, "typed"> & { label: string }) {
  const { label, ...rest } = props;
  return <ConfirmDialog {...rest} typed={label} />;
}
