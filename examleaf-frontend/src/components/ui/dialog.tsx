"use client";

// dialog.dialog: for confirmations only (remove a cart line, cancel an order, remove a passkey or an address). The
// browser's own modal <dialog> (showModal: the page behind is inert, Escape closes it, the box sits in the top layer),
// so no dialog library ships to the page. The box is min(32rem, 100% - 32px), radius 12, the dialog shadow, never
// taller than the screen and scrolling inside (400 % zoom: accessibility review F6); footer buttons right-aligned.
// It opens on its safe button (the footer's DialogClose); closing gives focus back to what opened it, or, when that
// is gone or unusable, to the page's heading. A click on the backdrop closes it.
import { cn } from "cn";
import { X } from "lucide-react";
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
        if (event.target === event.currentTarget) setOpen(false); // the backdrop (the box's parts fill the box)
      }}
      className={cn(
        "m-auto max-h-[calc(100dvh-32px)] w-[min(32rem,calc(100%-32px))] flex-col overflow-y-auto rounded-lg border-0 bg-card p-0 text-card-foreground shadow-dialog open:flex",
        // the backdrop's colour written out: older browsers do not give ::backdrop the page's custom properties
        "backdrop:bg-[rgba(7,18,43,0.55)] motion-safe:open:animate-in motion-safe:open:duration-200 motion-safe:open:fade-in-0",
        className,
      )}
      {...props}
    >
      {children}
    </dialog>
  );
}

function DialogHeader({ children }: { children: React.ReactNode }) {
  const { setOpen, id } = useDialog();
  return (
    <div className="flex items-center justify-between gap-3 pt-5 pr-3 pl-6">
      <h2 id={`${id}-title`} className="m-0 font-head text-[22px] leading-tight font-extrabold text-heading">
        {children}
      </h2>
      <button
        type="button"
        aria-label="Close"
        onClick={() => setOpen(false)}
        className="inline-flex size-11 shrink-0 items-center justify-center rounded-btn text-primary hover:bg-secondary-hover"
      >
        <X aria-hidden="true" className="size-[22px]" />
      </button>
    </div>
  );
}

function DialogBody({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-3 px-6 pt-2 [&>*]:m-0", className)} {...props} />;
}

function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-wrap justify-end gap-3 p-6", className)} {...props} />;
}

function DialogDescription(props: React.ComponentProps<"p">) {
  const { id } = useDialog();
  return <p id={`${id}-description`} {...props} />;
}

export { Dialog, DialogBody, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTrigger };
