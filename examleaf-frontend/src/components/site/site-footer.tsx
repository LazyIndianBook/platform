// The footer, Direction A: the ink band behind a red double rule; the wordmark and one line, then Books, Shop and
// ExamLeaf columns (44 px links), then © and the payments line. Same props as before.
import Link from "next/link";

import { Brand } from "./brand";

type FooterBook = { href: string; name: string };

const linkClasses =
  "inline-flex min-h-11 items-center text-[15px] text-white no-underline hover:text-red-ink hover:underline";

function FooterColumn({ title, links }: { title: string; links: { href: string; label: string }[] }) {
  return (
    <div className="min-w-0 flex-[1_1_140px]">
      <h2 className="m-0 mb-1 font-mono text-xs leading-snug font-medium tracking-[0.06em] text-muted-foreground uppercase">
        {title}
      </h2>
      <ul className="m-0 list-none p-0">
        {links.map((link) => (
          <li key={link.href}>
            <Link href={link.href} className={linkClasses}>
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SiteFooter({ books, signedIn }: { books: FooterBook[]; signedIn: boolean }) {
  return (
    <footer className="band-night pt-12 pb-8">
      <div className="mx-auto flex w-full max-w-[calc(var(--container)+var(--margin-col)+var(--marks-col))] flex-col gap-10 px-(--gutter) nav:pr-10 nav:pl-[calc(var(--margin-col)+40px)]">
        <div className="flex flex-wrap gap-8">
          <div className="flex min-w-0 flex-[2_1_300px] flex-col items-start gap-3">
            <Brand />
            <p className="m-0 max-w-[22rem] text-[15px] leading-[1.7] text-muted-foreground">
              Sample papers for the Assam Board (ASSEB) Class 12 examination, with free worked solutions behind a QR
              code.
            </p>
          </div>
          <FooterColumn
            title="Books"
            links={[
              ...books.map((book) => ({ href: book.href, label: book.name })),
              { href: "/revision/", label: "Revision course" },
            ]}
          />
          <FooterColumn
            title="Shop"
            links={[
              { href: "/shop/", label: "All books" },
              signedIn
                ? { href: "/account/orders/", label: "My orders" }
                : { href: "/orders/lookup/", label: "Find your order" },
              { href: "/shipping/", label: "Shipping" },
              { href: "/refunds/", label: "Refunds" },
            ]}
          />
          <FooterColumn
            title="ExamLeaf"
            links={[
              { href: "/about/", label: "About" },
              { href: "/contact/", label: "Contact" },
              { href: "/privacy/", label: "Privacy" },
              { href: "/terms/", label: "Terms" },
            ]}
          />
        </div>
        <div className="flex flex-wrap justify-between gap-x-6 gap-y-2 border-t border-night-line pt-5 text-sm text-muted-foreground">
          <span>© ExamLeaf LLP</span>
          <span>Payments through Razorpay: UPI, cards, net banking</span>
        </div>
      </div>
    </footer>
  );
}

export { SiteFooter, type FooterBook };
