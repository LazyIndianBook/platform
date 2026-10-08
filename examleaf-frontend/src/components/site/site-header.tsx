// The header, Direction A: paper, a hairline under it, one row at every width: the wordmark, the cart with its count
// (only when the cart has books), the links, and under 900 px the Menu button that opens them as a drawer.
// Behaviour unchanged (Drawer, NavLinks keep ?next=, G15).
import { ShoppingBag } from "lucide-react";
import Link from "next/link";

import { Drawer } from "@/components/ui/drawer";

import { Brand } from "./brand";
import { NavLinks } from "./nav-links";

type SiteHeaderProps = { signedIn: boolean; cartCount?: number };

function SiteHeader({ signedIn, cartCount = 0 }: SiteHeaderProps) {
  return (
    <header className="relative z-30 border-b border-header-line bg-background">
      <div className="mx-auto flex min-h-[72px] w-full max-w-[calc(var(--container)+var(--margin-col)+var(--marks-col))] items-center gap-2 px-(--gutter) nav:px-10">
        <Brand className="mr-auto" />
        {cartCount > 0 ? (
          <Link
            href="/cart/"
            aria-label={`Cart, ${cartCount} book${cartCount === 1 ? "" : "s"}`}
            className="inline-flex min-h-11 items-center gap-2 rounded-btn px-2 font-semibold text-foreground no-underline hover:text-red-ink"
          >
            <ShoppingBag aria-hidden="true" className="size-[22px] nav:hidden" />
            <span className="max-nav:sr-only">Cart</span>
            <span className="inline-flex h-[22px] min-w-[22px] items-center justify-center rounded-pill bg-foreground px-1.5 font-mono text-xs leading-none font-semibold text-background">
              {cartCount}
            </span>
          </Link>
        ) : null}
        <Drawer id="site-menu" label="Menu">
          <NavLinks signedIn={signedIn} />
        </Drawer>
      </div>
    </header>
  );
}

export { SiteHeader };
