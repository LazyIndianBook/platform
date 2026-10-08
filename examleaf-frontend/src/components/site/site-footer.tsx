// The footer, Direction A ("A Footer"): the ink band, its text in the margin's indent from 900 px; the wordmark alone
// and one line, then Books, Shop and ExamLeaf columns (mono headings, 44 px links in paper white, red ink on hover) on
// a 1.6 : 1 : 1 : 1 grid, then © and the payments line over a hairline. On a phone the columns wrap. Same props.
import Link from "next/link";

import { Brand } from "./brand";

type FooterBook = { href: string; name: string };

const linkClasses =
  "inline-flex min-h-11 items-center text-[15px] text-[#f8f5ee] no-underline hover:text-red-ink hover:underline";

function FooterColumn({ title, links }: { title: string; links: { href: string; label: string }[] }) {
  return (
    <div className="min-w-0 flex-[1_1_140px]">
      <h2 className="m-0 mb-1 font-mono text-xs leading-snug font-medium tracking-[0.06em] text-[#aeb3c0] uppercase">
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
    <footer className="band-night pt-12 pb-8 text-[#f8f5ee]">
      <div className="mx-auto flex w-full max-w-[calc(var(--container)+var(--margin-col)+var(--marks-col))] flex-col gap-10 px-(--gutter) nav:pr-10 nav:pl-[calc(var(--margin-col)+40px)]">
        <div className="flex flex-wrap gap-8 nav:grid nav:grid-cols-[minmax(0,1.6fr)_repeat(3,minmax(0,1fr))]">
          <div className="flex min-w-0 flex-[2_1_300px] flex-col items-start gap-3">
            <Brand className="[&>svg]:hidden" />
            <p className="m-0 max-w-[22em] text-[15px] leading-[1.7] text-[#aeb3c0]">
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
        <div className="flex flex-wrap justify-between gap-x-6 gap-y-2 border-t border-night-line pt-[18px] text-sm text-[#aeb3c0]">
          <span>© ExamLeaf LLP</span>
          <span>Payments through Razorpay: UPI, cards, net banking</span>
        </div>
      </div>
    </footer>
  );
}

export { SiteFooter, type FooterBook };
