// The header (components.md, .nav): navy, one row at every width: the wordmark, the cart with its count (only when
// the cart has books), the links, and under 900 px the Menu button that opens them as a drawer. Signed in, the menu
// reads Shop · My record · Account · Log out; otherwise Shop · Log in · Register, which keep the current page as
// the destination (coverage matrix G15).
import { ShoppingBag } from "lucide-react";
import Link from "next/link";

import { Drawer } from "@/components/ui/drawer";

import { Brand } from "./brand";
import { NavLinks } from "./nav-links";

type SiteHeaderProps = { signedIn: boolean; cartCount?: number };

function SiteHeader({ signedIn, cartCount = 0 }: SiteHeaderProps) {
  return (
    <header className="band-night relative z-30 border-b border-header-line bg-navy">
      <div className="container-site flex min-h-16 items-center gap-2">
        <Brand className="mr-auto" />
        {cartCount > 0 ? (
          <Link
            href="/cart/"
            aria-label={`Cart, ${cartCount} book${cartCount === 1 ? "" : "s"}`}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 font-semibold text-white no-underline"
          >
            <ShoppingBag aria-hidden="true" className="size-[22px]" />
            <span className="max-nav:sr-only">Cart</span>
            <span className="inline-flex h-[22px] min-w-[22px] items-center justify-center rounded-pill bg-gold px-1.5 font-head text-xs leading-none font-bold text-night">
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
