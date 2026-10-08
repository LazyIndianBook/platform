"use client";

// The header's links, Direction A: ink text on paper, the current page underlined in red ink (desktop) or marked
// with a red rule (drawer). Signed in: Books · Shop · Revision course · My record · Account · Log out. Signed out:
// Books · Shop · Revision course · Find your order · Log in · Register; Log in and Register keep the current page
// as ?next= (G15). Log out through allauth.headless, then a full load.
import { cn } from "cn";
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { withNext } from "@/lib/auth/next-url";

const linkClasses = cn(
  "inline-flex min-h-11 items-center gap-2 border-0 bg-transparent px-3 font-body text-base leading-tight font-semibold text-foreground no-underline hover:text-red-ink hover:no-underline",
  "aria-[current=page]:shadow-[inset_0_-2px_0_var(--red-ink)]",
  "max-nav:min-h-14 max-nav:w-full max-nav:justify-between max-nav:border-b max-nav:border-border max-nav:px-1 max-nav:text-lg",
  "max-nav:aria-[current=page]:pl-3 max-nav:aria-[current=page]:shadow-[inset_3px_0_0_var(--red-ink)]",
);

type NavLinkProps = { href: string; children: string; current?: boolean; desktopOnly?: boolean };

function NavLink({ href, children, current, desktopOnly = false }: NavLinkProps) {
  const pathname = usePathname();
  const isCurrent = current ?? pathname === href.split("?")[0];
  return (
    <Link
      href={href}
      aria-current={isCurrent ? "page" : undefined}
      className={cn(linkClasses, desktopOnly && "max-nav:hidden")}
    >
      <span>{children}</span>
      <ChevronRight aria-hidden="true" className="size-5 text-muted-foreground nav:hidden" />
    </Link>
  );
}

function Divider() {
  return <span aria-hidden="true" className="mx-2 h-6 w-px bg-border max-nav:hidden" />;
}

function NavLinks({ signedIn }: { signedIn: boolean }) {
  const pathname = usePathname();
  const [leaving, setLeaving] = useState(false);
  const keep = pathname.startsWith("/account/") ? null : pathname;
  const common = (
    <>
      <NavLink href="/#books" current={pathname.startsWith("/books/")}>
        Books
      </NavLink>
      <NavLink href="/shop/" current={pathname.startsWith("/shop/")}>
        Shop
      </NavLink>
      <NavLink href="/revision/" current={pathname.startsWith("/revision/")}>
        Revision course
      </NavLink>
    </>
  );

  if (signedIn) {
    const logout = async () => {
      setLeaving(true);
      try {
        const { auth } = await import("@/lib/auth/headless");
        await auth.logout();
      } finally {
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.assign("/");
      }
    };
    return (
      <>
        {common}
        <NavLink href="/account/record/" current={pathname.startsWith("/account/record/")}>
          My record
        </NavLink>
        <NavLink href="/account/" current={/^\/account\/(?!record\/)/.test(pathname)}>
          Account
        </NavLink>
        <Divider />
        <button
          type="button"
          className={linkClasses}
          onClick={logout}
          aria-busy={leaving || undefined}
          disabled={leaving}
        >
          <span>{leaving ? "Logging out…" : "Log out"}</span>
          <ChevronRight aria-hidden="true" className="size-5 text-muted-foreground nav:hidden" />
        </button>
      </>
    );
  }

  return (
    <>
      {common}
      <NavLink href="/orders/lookup/">Find your order</NavLink>
      <Divider />
      <NavLink href={withNext("/account/login/", keep)}>Log in</NavLink>
      <Link
        href={withNext("/account/signup/", keep)}
        className={cn(
          buttonVariants({ variant: "primary", size: "sm" }),
          "ml-1 max-nav:mt-5 max-nav:ml-0 max-nav:min-h-[52px] max-nav:text-[17px]",
        )}
      >
        Register
      </Link>
    </>
  );
}

export { NavLinks };
