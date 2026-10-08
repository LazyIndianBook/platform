"use client";

// dialog.dialog: for confirmations only (remove a cart line, cancel an order). Radix gives the focus trap, Escape and
// the backdrop; the box is min(32rem, 100% - 32px), radius 12, the dialog shadow; footer buttons right-aligned.
// Open it on its safe button (autoFocus on "Keep it").
import { cn } from "cn";
import { X } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import * as React from "react";

const Dialog = DialogPrimitive.Root;
const DialogTrigger = DialogPrimitive.Trigger;
const DialogClose = DialogPrimitive.Close;

function DialogContent({ className, children, ...props }: React.ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-(--backdrop) motion-safe:data-[state=open]:animate-in motion-safe:data-[state=open]:fade-in-0" />
      <DialogPrimitive.Content
        className={cn(
          "fixed top-1/2 left-1/2 z-50 flex w-[min(32rem,calc(100%-32px))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg bg-card text-card-foreground shadow-dialog",
          "motion-safe:data-[state=open]:animate-in motion-safe:data-[state=open]:duration-200 motion-safe:data-[state=open]:fade-in-0",
          className,
        )}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

function DialogHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 pt-5 pr-3 pl-6">
      <DialogPrimitive.Title className="m-0 font-head text-[22px] leading-tight font-extrabold text-heading">
        {children}
      </DialogPrimitive.Title>
      <DialogPrimitive.Close
        aria-label="Close"
        className="inline-flex size-11 items-center justify-center rounded-btn text-primary hover:bg-secondary-hover"
      >
        <X aria-hidden="true" className="size-[22px]" />
      </DialogPrimitive.Close>
    </div>
  );
}

function DialogBody({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-3 px-6 pt-2 [&>*]:m-0", className)} {...props} />;
}

function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-wrap justify-end gap-3 p-6", className)} {...props} />;
}

const DialogDescription = DialogPrimitive.Description;

export { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTrigger };
