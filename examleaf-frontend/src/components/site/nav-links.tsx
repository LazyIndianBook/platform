"use client";

// The header's links: aria-current on the page's own link, the current page kept as ?next= on Log in and Register,
// Log out through allauth.headless (DELETE the session), then a fresh page.
import { cn } from "cn";
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { auth } from "@/lib/auth/headless";
import { withNext } from "@/lib/auth/next-url";

const linkClasses = cn(
  "inline-flex min-h-11 items-center gap-2 rounded-lg border-0 bg-transparent px-3 font-body text-base leading-tight font-semibold text-white no-underline hover:bg-white/8 hover:no-underline",
  "aria-[current=page]:rounded-b-none aria-[current=page]:shadow-[inset_0_-3px_0_var(--leaf-light)]",
  "max-nav:min-h-12 max-nav:w-full max-nav:justify-between max-nav:rounded-none max-nav:border-b max-nav:border-header-line max-nav:px-1 max-nav:text-[17px]",
  "max-nav:aria-[current=page]:pl-3 max-nav:aria-[current=page]:shadow-[inset_3px_0_0_var(--leaf-light)]",
);

function NavLink({ href, children, phoneOnly = false }: { href: string; children: string; phoneOnly?: boolean }) {
  const pathname = usePathname();
  return (
    <Link
      href={href}
      aria-current={pathname === href.split("?")[0] ? "page" : undefined}
      className={cn(linkClasses, phoneOnly && "nav:hidden")}
    >
      <span>{children}</span>
      <ChevronRight aria-hidden="true" className="size-5 nav:hidden" />
    </Link>
  );
}

function NavLinks({ signedIn }: { signedIn: boolean }) {
  const pathname = usePathname();
  const [leaving, setLeaving] = useState(false);
  const keep = pathname.startsWith("/account/") ? null : pathname;

  if (signedIn) {
    const logout = async () => {
      setLeaving(true);
      try {
        await auth.logout();
      } finally {
        // a full load: the header, the cart and every layout read the ended session
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.assign("/");
      }
    };
    return (
      <>
        <NavLink href="/shop/">Shop</NavLink>
        <NavLink href="/account/record/">My record</NavLink>
        <NavLink href="/account/">Account</NavLink>
        <button
          type="button"
          className={linkClasses}
          onClick={logout}
          aria-busy={leaving || undefined}
          disabled={leaving}
        >
          <span>Log out</span>
          <ChevronRight aria-hidden="true" className="size-5 nav:hidden" />
        </button>
      </>
    );
  }

  return (
    <>
      <NavLink href="/shop/">Shop</NavLink>
      <NavLink href="/orders/lookup/" phoneOnly>
        Find your order
      </NavLink>
      <NavLink href={withNext("/account/login/", keep)}>Log in</NavLink>
      <Link
        href={withNext("/account/signup/", keep)}
        className={cn(
          buttonVariants({ variant: "accent", size: "sm" }),
          "ml-2 max-nav:mt-4 max-nav:ml-0 max-nav:min-h-[52px] max-nav:text-[17px]",
        )}
      >
        Register
      </Link>
    </>
  );
}

export { NavLinks };
