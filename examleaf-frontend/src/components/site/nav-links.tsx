"use client";

// The header's links, Direction A ("A Header", "Phone menu"): ink text on paper, red ink on hover; the current page
// underlined in red ink (desktop) or marked with a red rule (drawer). Signed in: Books · Shop · Revision course ·
// My record · Account | Cart · Log out. Signed out: Books · Shop · Revision course · Find your order | Cart · Log in ·
// Register. The cart (only when it has books) sits after the divider on desktop; on a phone it stays in the header row
// (SiteHeader). The drawer adds About and Contact and ends with Register (navy) and Log in (an outline), as drawn;
// Log in and Register keep the current page as ?next= (G15). Log out through allauth.headless, then a full load.
import { cn } from "cn";
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { withNext } from "@/lib/auth/next-url";

const linkClasses = cn(
  "inline-flex min-h-11 items-center gap-2 border-0 bg-transparent px-3.5 font-body text-base leading-tight font-semibold text-foreground no-underline hover:text-red-ink hover:no-underline",
  "aria-[current=page]:shadow-[inset_0_-2px_0_var(--red-ink)]",
  "max-nav:min-h-14 max-nav:w-full max-nav:justify-between max-nav:border-b max-nav:border-border max-nav:px-0 max-nav:text-lg",
  "max-nav:aria-[current=page]:pl-3 max-nav:aria-[current=page]:shadow-[inset_3px_0_0_var(--red-ink)]",
);

type NavLinkProps = {
  href: string;
  children: string;
  current?: boolean;
  desktopOnly?: boolean;
  phoneOnly?: boolean;
};

function NavLink({ href, children, current, desktopOnly = false, phoneOnly = false }: NavLinkProps) {
  const pathname = usePathname();
  const isCurrent = current ?? pathname === href.split("?")[0];
  return (
    <Link
      href={href}
      aria-current={isCurrent ? "page" : undefined}
      className={cn(linkClasses, desktopOnly && "max-nav:hidden", phoneOnly && "nav:hidden")}
    >
      <span>{children}</span>
      <ChevronRight aria-hidden="true" className="size-5 text-muted-foreground nav:hidden" />
    </Link>
  );
}

function Divider() {
  return <span aria-hidden="true" className="mx-2 h-6 w-px bg-border max-nav:hidden" />;
}

/** The cart with its count, spoken as "Cart, 2 books" (the header row on a phone, after the divider on desktop). */
function CartLink({ count, className }: { count: number; className?: string }) {
  return (
    <Link
      href="/cart/"
      aria-label={`Cart, ${count} book${count === 1 ? "" : "s"}`}
      className={cn(
        "inline-flex min-h-11 items-center gap-2 px-3.5 font-semibold text-foreground no-underline hover:text-red-ink hover:no-underline",
        className,
      )}
    >
      <span>Cart</span>
      <span className="inline-flex min-w-[22px] items-center justify-center rounded-pill bg-foreground px-[7px] py-1 font-mono text-xs leading-none font-semibold text-background">
        {count}
      </span>
    </Link>
  );
}

function NavLinks({ signedIn, cartCount = 0 }: { signedIn: boolean; cartCount?: number }) {
  const pathname = usePathname();
  const [leaving, setLeaving] = useState(false);
  const keep = pathname.startsWith("/account/") ? null : pathname;
  const cart = cartCount > 0 ? <CartLink count={cartCount} className="max-nav:hidden" /> : null;
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
  const more = (
    <>
      <NavLink href="/about/" phoneOnly>
        About
      </NavLink>
      <NavLink href="/contact/" phoneOnly>
        Contact
      </NavLink>
    </>
  );

  if (signedIn) {
    const logout = async () => {
      setLeaving(true);
      try {
        const { auth } = await import("@/lib/auth/headless");
        await auth.logout();
      } catch {
        // no answer: home all the same; the session ends at its own limits
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
        {more}
        <Divider />
        {cart}
        <button
          type="button"
          className={cn(linkClasses, "cursor-pointer")}
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

  const login = withNext("/account/login/", keep);
  return (
    <>
      {common}
      <NavLink href="/orders/lookup/">Find your order</NavLink>
      {more}
      <Divider />
      {cart}
      <NavLink href={login} desktopOnly>
        Log in
      </NavLink>
      <Link
        href={withNext("/account/signup/", keep)}
        className={buttonVariants({
          variant: "primary",
          size: "sm",
          className:
            "ml-1 px-[18px] text-base font-semibold max-nav:mt-5 max-nav:ml-0 max-nav:min-h-[54px] max-nav:text-lg max-nav:font-bold",
        })}
      >
        Register
      </Link>
      <Link
        href={login}
        className={buttonVariants({
          variant: "secondary",
          className: "mt-2.5 min-h-[50px] text-lg nav:hidden",
        })}
      >
        Log in
      </Link>
    </>
  );
}

export { CartLink, NavLinks };
