// 404 (Django's 404.html), Direction A (ExamLeaf A - Public.dc.html, "404"; Phone 404 and offline): "404" in the
// margin and [0] in the marks column, a hint for a mistyped QR address, then the four books to open. A wrong or cut
// order link (/orders/t/…) gets its own words and the way on instead (G19).
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";

import { Sheet } from "@/components/ui/band";
import { buttonVariants } from "@/components/ui/button";
import { SubjectTile } from "@/components/ui/subject-tile";
import { getBooks } from "@/lib/api/catalogue";
import { subjectOf } from "@/lib/site";

export const metadata: Metadata = {
  title: "Page not found",
  description: "This page does not exist on the ExamLeaf website. Choose a book or open the shop.",
  robots: { index: false, follow: false },
};

export default async function NotFound() {
  const path = (await headers()).get("x-pathname") ?? "";
  const orderLink = path.startsWith("/orders/t/");
  const books = orderLink ? [] : await getBooks().catch(() => []);
  return (
    <Sheet
      margin="404"
      marks={<span className="text-[30px] leading-none">[0]</span>}
      className="max-nav:[&>.sheet-margin]:hidden"
      bodyClassName="max-nav:pt-6"
    >
      <div className="flex max-w-[760px] flex-col gap-7 max-nav:gap-3 [&>*]:m-0">
        <p aria-hidden="true" className="font-mono text-sm font-semibold text-red-ink nav:hidden">
          404 · [0]
        </p>
        {orderLink ? (
          <>
            <h1 className="text-[clamp(32px,5vw,64px)] leading-none tracking-[-0.025em]">
              We can&apos;t open this order link
            </h1>
            <p className="max-w-[34em] text-lg leading-relaxed text-ink/85 max-nav:text-[15px]">
              It may have been copied only partly. Ask for a fresh private link with your order number.
            </p>
            <p className="flex flex-wrap gap-x-4 font-bold">
              <Link href="/orders/lookup/" className="inline-flex min-h-11 items-center">
                Find your order
              </Link>
              <Link href="/account/login/?next=/account/orders/" className="inline-flex min-h-11 items-center">
                Log in
              </Link>
            </p>
          </>
        ) : (
          <>
            <h1 className="text-[clamp(32px,5vw,64px)] leading-none tracking-[-0.025em]">
              This page isn&apos;t in the book
            </h1>
            <p className="max-w-[34em] text-lg leading-relaxed text-ink/85 max-nav:text-[15px]">
              If you typed a paper code, check it against the code under the QR on the paper (for example PHY-E01). Or
              open a book and choose the paper there.
            </p>
            {books.length ? (
              <nav aria-label="The books" className="border-t-[1.5px] border-foreground">
                {books.map((book) => {
                  const subject = subjectOf(book.subject.code);
                  return (
                    <SubjectTile
                      key={book.slug}
                      subject={subject?.key ?? "physics"}
                      name={subject?.name ?? book.subject.name}
                      href={`/books/${book.slug}/`}
                      papers={book.papers.length}
                      cover={book.cover}
                    />
                  );
                })}
              </nav>
            ) : (
              <p>
                <Link href="/" className={buttonVariants({ variant: "primary", size: "lg" })}>
                  Go to Home
                </Link>
              </p>
            )}
          </>
        )}
      </div>
    </Sheet>
  );
}
