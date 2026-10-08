// The footer (components.md, .footer): a night band; the wordmark and one line, then Books, Shop and ExamLeaf
// columns with 44 px links, then © and the payments line.
import Link from "next/link";

import { Brand } from "./brand";

type FooterBook = { href: string; name: string };

const linkClasses = "inline-flex min-h-11 items-center text-base text-white no-underline hover:underline";

function FooterColumn({ title, links }: { title: string; links: { href: string; label: string }[] }) {
  return (
    <div className="min-w-0 flex-[1_1_140px]">
      <h2 className="m-0 mb-1 font-head text-[15px] leading-snug font-bold text-muted-foreground">{title}</h2>
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
    <footer className="band-night pt-14 pb-8">
      <div className="container-site flex flex-col gap-10">
        <div className="flex flex-wrap gap-8">
          <div className="flex min-w-0 flex-[2_1_300px] flex-col items-start gap-3">
            <Brand />
            <p className="m-0 max-w-[22rem] text-base leading-[1.7] text-muted-foreground">
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
        <div className="flex flex-wrap justify-between gap-x-6 gap-y-2 border-t border-night-line pt-5 text-[15px] text-muted-foreground">
          <span>© ExamLeaf LLP</span>
          <span>Payments through Razorpay: UPI, cards, net banking</span>
        </div>
      </div>
    </footer>
  );
}

export { SiteFooter, type FooterBook };
