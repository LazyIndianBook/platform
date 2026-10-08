"use client";

// The account's own navigation, Direction A ("A Account Nav", "Phone account"): a quiet list in the left margin on
// desktop (15 px 600 over soft hairlines, a red dot on the current page), a row of 14 px chips over a hairline that
// scrolls sideways under 900 px (the current chip in an ink box on white; chips stay 44 px tall). The current chip is
// brought into the row's view with scrollLeft (no scrollIntoView, which can also scroll the page). Links unchanged.
import { cn } from "cn";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

const LINKS = [
  { href: "/account/", label: "My account" },
  { href: "/account/record/", label: "My record" },
  { href: "/account/learning/", label: "Learning" },
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
  useEffect(() => {
    const row = list.current;
    const chip = row?.querySelector<HTMLElement>("[aria-current]");
    if (!row || !chip || row.scrollWidth <= row.clientWidth) return;
    const left = chip.offsetLeft - row.offsetLeft;
    if (left < row.scrollLeft || left + chip.offsetWidth > row.scrollLeft + row.clientWidth) {
      row.scrollLeft = Math.max(0, left - 16);
    }
  }, [pathname]);
  const current = (link: (typeof LINKS)[number]) =>
    pathname === link.href ||
    (link.href !== "/account/" && pathname.startsWith(link.href)) ||
    (link.also !== undefined && pathname.startsWith(link.also));
  return (
    <nav aria-label="My account" className="min-w-0 flex-[0_0_220px] max-nav:basis-full">
      <ul
        ref={list}
        className={cn(
          "m-0 flex list-none flex-col p-0",
          "max-nav:-mx-(--gutter) max-nav:flex-row max-nav:gap-2 max-nav:overflow-x-auto max-nav:border-b max-nav:border-border max-nav:px-(--gutter) max-nav:py-2.5",
        )}
      >
        {LINKS.map((link) => (
          <li key={link.href} className="max-nav:flex-none">
            <Link
              href={link.href}
              aria-current={current(link) ? "page" : undefined}
              className={cn(
                "group flex min-h-11 items-center gap-2.5 border-b border-rule-soft text-[15px] font-semibold text-foreground no-underline hover:text-red-ink hover:no-underline",
                "aria-[current=page]:font-bold",
                "max-nav:rounded-[3px] max-nav:border max-nav:border-input max-nav:px-3 max-nav:text-sm max-nav:whitespace-nowrap max-nav:aria-[current=page]:border-[1.5px] max-nav:aria-[current=page]:border-foreground max-nav:aria-[current=page]:bg-card",
              )}
            >
              <span
                aria-hidden="true"
                className="size-[7px] flex-none rounded-full bg-transparent group-aria-[current=page]:bg-red-ink max-nav:hidden"
              />
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
