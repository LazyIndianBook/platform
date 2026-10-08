"use client";

// The header's menu drawer (components.md, .nav-toggle / .nav-menu): under 900 px the links fold behind a Menu button
// and open as a full-width panel under the header; from 900 px they sit in the header row and the button is gone.
// A disclosure, not a modal: aria-expanded follows the state; Escape closes it and puts focus back on Menu; a click
// outside or a new page closes it. No focus trap, no scroll lock, no portal: nothing for a cheap phone to carry.
import { cn } from "cn";
import { Menu, X } from "lucide-react";
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
    const onClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!panel.current?.contains(target) && !toggle.current?.contains(target)) setOpenOn(null);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("click", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("click", onClick);
    };
  }, [open]);

  return (
    <>
      <nav
        ref={panel}
        id={id}
        aria-label="Main"
        data-open={open || undefined}
        className={cn(
          "items-center gap-1 nav:flex",
          "max-nav:absolute max-nav:inset-x-0 max-nav:top-full max-nav:hidden max-nav:flex-col max-nav:items-stretch max-nav:gap-0",
          "max-nav:border-t max-nav:border-header-line max-nav:bg-navy max-nav:px-(--gutter) max-nav:pt-2 max-nav:pb-5 max-nav:shadow-menu",
          "max-nav:data-open:flex",
          className,
        )}
      >
        {children}
      </nav>
      <button
        ref={toggle}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className="inline-flex min-h-11 items-center gap-2 rounded-btn border-[1.5px] border-header-line px-3 font-head text-[15px] leading-none font-bold text-white max-[359.98px]:px-2.5 nav:hidden"
      >
        {open ? <X aria-hidden="true" className="size-[22px]" /> : <Menu aria-hidden="true" className="size-[22px]" />}
        <span className="max-[359.98px]:sr-only">{open ? "Close" : label}</span>
      </button>
    </>
  );
}

export { Drawer };
