"use client";

// A disclosure that opens a small panel under its button (the column chooser, the person's menu): aria-expanded on
// the button, Escape closes it and gives the focus back, a click or the focus going outside closes it. Not a modal
// and no focus trap, as the kit's Drawer: nothing for a cheap phone to carry.
import { cn } from "cn";
import { useEffect, useId, useRef, useState } from "react";

type PopoverProps = {
  button: React.ReactNode;
  /** The button's accessible name when its content is not enough. */
  label?: string;
  buttonClassName?: string;
  panelClassName?: string;
  align?: "start" | "end";
  children: (close: () => void) => React.ReactNode;
};

export function Popover({ button, label, buttonClassName, panelClassName, align = "end", children }: PopoverProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      toggle.current?.focus();
    };
    const onOutside = (event: Event) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("click", onOutside);
    document.addEventListener("focusin", onOutside);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("click", onOutside);
      document.removeEventListener("focusin", onOutside);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        ref={toggle}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={label}
        onClick={() => setOpen(!open)}
        className={cn(
          "inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-btn border-[1.5px] border-foreground bg-transparent px-3.5 text-[15px] font-bold text-foreground hover:bg-secondary",
          buttonClassName,
        )}
      >
        {button}
      </button>
      <div
        id={id}
        hidden={!open}
        className={cn(
          "absolute top-full z-30 mt-1.5 min-w-60 rounded-lg border border-border bg-card p-3 text-foreground shadow-menu",
          align === "end" ? "right-0" : "left-0",
          panelClassName,
        )}
      >
        {open ? children(() => setOpen(false)) : null}
      </div>
    </div>
  );
}
