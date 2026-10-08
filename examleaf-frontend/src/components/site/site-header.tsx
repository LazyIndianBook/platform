// The header, Direction A ("A Header", "A Phone Header"): paper, a hairline under it, one row at every width, 72 px
// tall from 900 px and 60 px under it. The wordmark, then the links (NavLinks; the cart after their divider) on
// desktop; on a phone the cart with its count (only when the cart has books) and the Menu button that opens the links
// as a drawer. Behaviour unchanged (Drawer, NavLinks keep ?next=, G15).
import { Drawer } from "@/components/ui/drawer";

import { Brand } from "./brand";
import { CartLink, NavLinks } from "./nav-links";

type SiteHeaderProps = { signedIn: boolean; cartCount?: number };

function SiteHeader({ signedIn, cartCount = 0 }: SiteHeaderProps) {
  return (
    <header className="relative z-30 border-b border-header-line bg-background">
      <div className="mx-auto flex min-h-[60px] w-full max-w-[calc(var(--container)+var(--margin-col)+var(--marks-col))] items-center gap-2 px-(--gutter) nav:min-h-[72px] nav:px-10">
        <Brand className="mr-auto" />
        {cartCount > 0 ? (
          <CartLink count={cartCount} className="px-2.5 text-[15px] font-bold max-[359.98px]:px-1.5 nav:hidden" />
        ) : null}
        <Drawer id="site-menu" label="Menu">
          <NavLinks signedIn={signedIn} cartCount={cartCount} />
        </Drawer>
      </div>
    </header>
  );
}

export { SiteHeader };
