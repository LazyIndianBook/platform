"use client";

// dialog.dialog, Direction A (Components board, 08; States, "Cancel dialog"): for confirmations only (remove a cart
// line, cancel an order, remove a passkey or an address). The browser's own modal <dialog> (showModal: the page behind
// is inert, Escape closes it, the box sits in the top layer), so no dialog library ships to the page. A paper sheet
// min(32rem, 100% - 32px) wide over rgba(29,34,48,.55), 26 px inside: the title in the serif, the body in 15 px, the
// footer right-aligned with the safe button first and then the destructive or primary one. Never taller than the
// screen, it scrolls inside (400 % zoom: accessibility review F6). No × (neither drawing has one): the safe button,
// Escape and a click on the backdrop close it. It opens on its safe button (the footer's DialogClose); closing gives
// focus back to what opened it, or, when that is gone or unusable, to the page's heading.
import { cn } from "cn";
import { Slot } from "radix-ui";
import * as React from "react";

import { focusHere } from "@/lib/utils";

type DialogState = { open: boolean; setOpen: (open: boolean) => void; id: string };
const DialogContext = React.createContext<DialogState | null>(null);

function useDialog(): DialogState {
  const state = React.useContext(DialogContext);
  if (!state) throw new Error("Dialog parts belong inside <Dialog>");
  return state;
}

function Dialog({
  open: controlled,
  onOpenChange,
  children,
}: {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
}) {
  const [own, setOwn] = React.useState(false);
  const open = controlled ?? own;
  const id = React.useId();
  const setOpen = React.useCallback(
    (next: boolean) => {
      if (controlled === undefined) setOwn(next);
      onOpenChange?.(next);
    },
    [controlled, onOpenChange],
  );
  return <DialogContext.Provider value={{ open, setOpen, id }}>{children}</DialogContext.Provider>;
}

type PartProps = React.ComponentProps<"button"> & { asChild?: boolean };

function DialogTrigger({ asChild, onClick, ...props }: PartProps) {
  const { setOpen } = useDialog();
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      {...(asChild ? {} : { type: "button" as const })}
      {...props}
      onClick={(event: React.MouseEvent<HTMLButtonElement>) => {
        onClick?.(event);
        setOpen(true);
      }}
    />
  );
}

/** The footer's safe button ("Keep it"): it closes the dialog, and the dialog opens with focus on it. */
function DialogClose({ asChild, onClick, ...props }: PartProps) {
  const { setOpen } = useDialog();
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      data-dialog-safe=""
      {...(asChild ? {} : { type: "button" as const })}
      {...props}
      onClick={(event: React.MouseEvent<HTMLButtonElement>) => {
        onClick?.(event);
        setOpen(false);
      }}
    />
  );
}

/** Focus back where the dialog was opened from; when that is gone (a removed line) or disabled, the page's heading. */
function restoreFocus(opener: HTMLElement | null) {
  if (opener?.isConnected && !opener.matches(":disabled")) return opener.focus();
  focusHere(document.querySelector<HTMLElement>("main h1") ?? document.getElementById("main"));
}

function DialogContent({ className, children, ...props }: React.ComponentProps<"dialog">) {
  const { open, setOpen, id } = useDialog();
  const ref = React.useRef<HTMLDialogElement>(null);
  const opener = React.useRef<HTMLElement | null>(null);

  React.useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
      dialog.querySelector<HTMLElement>("[data-dialog-safe]")?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-description`}
      onClose={() => {
        setOpen(false);
        restoreFocus(opener.current);
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) setOpen(false); // the backdrop (the box's wrapper fills the box)
      }}
      className={cn(
        // centred by its margins, held against a parent's [&>*]:m-0 (the order page's) by the [open] selector's weight
        "m-auto max-h-[calc(100dvh-32px)] w-[min(32rem,calc(100%-32px))] flex-col overflow-y-auto rounded-lg border-0 bg-background p-0 text-foreground shadow-dialog open:flex [&[open]]:m-auto",
        // the backdrop's colour written out: older browsers do not give ::backdrop the page's custom properties
        "backdrop:bg-[rgba(29,34,48,0.55)] motion-safe:open:animate-in motion-safe:open:duration-150 motion-safe:open:fade-in-0",
        className,
      )}
      {...props}
    >
      {/* the padding is inside: a click on the dialog element itself is a click on the backdrop */}
      <div className="flex flex-col gap-3.5 p-[26px]">{children}</div>
    </dialog>
  );
}

function DialogHeader({ children }: { children: React.ReactNode }) {
  const { id } = useDialog();
  return (
    <h2 id={`${id}-title`} className="m-0 font-head text-[26px] leading-[1.15] font-semibold text-heading">
      {children}
    </h2>
  );
}

function DialogBody({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("flex flex-col gap-3 text-[15px] leading-[1.6] text-[#3e4454] [&>*]:m-0", className)}
      {...props}
    />
  );
}

function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-wrap justify-end gap-2.5 max-nav:[&>*]:grow", className)} {...props} />;
}

function DialogDescription(props: React.ComponentProps<"p">) {
  const { id } = useDialog();
  return <p id={`${id}-description`} {...props} />;
}

export { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTrigger };
