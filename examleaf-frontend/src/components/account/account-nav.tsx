"use client";

// The account's own navigation (Account artboard; Django's .side-nav): a column of links beside the cards on desktop,
// a row of chips that scrolls sideways above them under 900 px (it comes first in the page, so it lands on top). The
// current page's link is marked. The revision course (/revision/, public too) has a layout of its own.
import { cn } from "cn";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

const LINKS = [
  { href: "/account/", label: "My account" },
  { href: "/account/record/", label: "My record" },
  { href: "/account/orders/", label: "My orders" },
  { href: "/account/details/", label: "Details" },
  { href: "/account/addresses/", label: "Addresses" },
  { href: "/account/security/", label: "Log-in and security", also: "/account/2fa/" },
  { href: "/account/privacy/", label: "Consent and your data" },
  { href: "/account/teacher/", label: "Teacher access" },
  { href: "/revision/", label: "Revision course" },
];

export function AccountNav() {
  const pathname = usePathname();
  const list = useRef<HTMLUListElement>(null);
  // on a phone the current chip may sit beyond the screen's edge: bring it into the row's view
  useEffect(() => {
    list.current?.querySelector("[aria-current]")?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [pathname]);
  const current = (link: (typeof LINKS)[number]) =>
    pathname === link.href ||
    (link.href !== "/account/" && pathname.startsWith(link.href)) ||
    (link.also !== undefined && pathname.startsWith(link.also));
  return (
    <nav aria-label="My account" className="min-w-0 flex-[1_1_220px] max-nav:basis-full">
      <ul
        ref={list}
        className={cn(
          "m-0 flex list-none flex-col gap-1 p-0",
          "max-nav:-mx-(--gutter) max-nav:flex-row max-nav:gap-2 max-nav:overflow-x-auto max-nav:px-(--gutter) max-nav:pt-0.5 max-nav:pb-1.5",
        )}
      >
        {LINKS.map((link) => (
          <li key={link.href} className="max-nav:flex-none">
            <Link
              href={link.href}
              aria-current={current(link) ? "page" : undefined}
              className={cn(
                "flex min-h-11 items-center rounded-btn px-3.5 text-base font-semibold text-primary no-underline hover:bg-secondary hover:no-underline",
                "aria-[current=page]:bg-secondary aria-[current=page]:font-bold",
                "max-nav:rounded-pill max-nav:border-[1.5px] max-nav:border-input max-nav:whitespace-nowrap max-nav:aria-[current=page]:border-primary",
              )}
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
