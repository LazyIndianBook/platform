"use client";

// The header's menu drawer, Direction A ("A Phone Header", "Phone menu"): under 900 px the links fold behind a Menu
// button and open as one full-height paper sheet under the header (an ink rule on top, the links in 56 px rows, the
// current page marked by a red rule, Register as the navy button at the bottom: NavLinks draws the rows); from 900 px
// they sit in the header row and the button is gone. The button is ink on paper in every state (outline, 44 px; paper 2
// on hover, 1 px press, the focus ring) and says Close while open. A disclosure, not a modal: aria-expanded follows the
// state; Escape closes it and puts focus back on Menu; a click outside, Tab past the last link or a new page closes it,
// so the sheet never covers the focused element. No focus trap, no scroll lock, no portal: nothing for a cheap phone to
// carry. The button comes before the links in the page, so Tab from Menu goes into the open menu (accessibility review
// F3); the sheet is positioned under the header, so the order changes nothing on screen.
import { cn } from "cn";
import { usePathname } from "next/navigation";
import * as React from "react";

type DrawerProps = {
  id: string;
  label: string;
  className?: string;
  children: React.ReactNode;
};

function Drawer({ id, label, className, children }: DrawerProps) {
  // open on the page where it was opened: a new page closes it without an effect
  const pathname = usePathname();
  const [openOn, setOpenOn] = React.useState<string | null>(null);
  const open = openOn === pathname;
  const setOpen = (value: boolean) => setOpenOn(value ? pathname : null);
  const toggle = React.useRef<HTMLButtonElement>(null);
  const panel = React.useRef<HTMLElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenOn(null);
        toggle.current?.focus();
      }
    };
    // a click outside, or Tab past the last link: closed, so the panel never covers the focused element
    const onOutside = (event: Event) => {
      const target = event.target as Node;
      if (!panel.current?.contains(target) && !toggle.current?.contains(target)) setOpenOn(null);
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
    <>
      <button
        ref={toggle}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className={cn(
          "inline-flex min-h-11 shrink-0 cursor-pointer items-center rounded-btn border-[1.5px] border-foreground bg-transparent px-3.5",
          "font-body text-[15px] leading-none font-bold text-foreground select-none hover:bg-secondary active:translate-y-px active:bg-secondary-hover",
          "motion-safe:transition-[translate] motion-safe:duration-150 motion-safe:ease-enter max-[359.98px]:px-2.5 nav:hidden",
        )}
      >
        {open ? "Close" : label}
      </button>
      <nav
        ref={panel}
        id={id}
        aria-label="Main"
        data-open={open || undefined}
        className={cn(
          "items-center gap-1 nav:flex",
          "max-nav:absolute max-nav:inset-x-0 max-nav:top-full max-nav:hidden max-nav:min-h-[calc(100dvh-60px)] max-nav:flex-col max-nav:items-stretch max-nav:gap-0",
          "max-nav:border-t-[1.5px] max-nav:border-foreground max-nav:bg-background max-nav:px-(--gutter) max-nav:pt-2 max-nav:pb-7",
          "max-nav:data-open:flex",
          className,
        )}
      >
        {children}
      </nav>
    </>
  );
}

export { Drawer };
