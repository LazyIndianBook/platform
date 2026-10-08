"use client";

// After a client-side navigation, focus moves to the new page's h1 (or the main region), where a full page load would
// start a screen reader, instead of staying on a link that is gone or in the header; a field the page focused itself
// keeps it. The first load and changes of the query alone (a filter, a page of a list) are left alone. Next's route
// announcer still reads the new title.
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

export function RouteFocus() {
  const pathname = usePathname();
  const previous = useRef(pathname);
  useEffect(() => {
    if (previous.current === pathname) return;
    previous.current = pathname;
    if (document.activeElement?.matches("input, select, textarea")) return;
    const main = document.getElementById("main");
    const target = main?.querySelector<HTMLElement>("h1") ?? main;
    if (!target) return;
    if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
  }, [pathname]);
  return null;
}
