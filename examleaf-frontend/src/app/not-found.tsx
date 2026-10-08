// 404 (Django's 404.html): the drawing, "We could not find that page", a hint for a mistyped QR address or a cut
// order link, one button, then the four books to open.
import { BookOpen } from "lucide-react";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
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
  const books = await getBooks().catch(() => []);
  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site">
        <EmptyState
          art="missing"
          eyebrow="Error 404"
          title="We could not find that page"
          headingLevel={1}
          action={
            <Link href="/" className={buttonVariants({ variant: "primary", size: "lg" })}>
              <BookOpen aria-hidden="true" />
              <span>See the books</span>
            </Link>
          }
          after={
            <p>
              or <Link href="/shop/">open the shop</Link>
            </p>
          }
        >
          <p>The address may have a typing mistake, or the page has moved.</p>
          {path.startsWith("/s/") ? (
            <p className="text-foreground">
              Looking for the solutions to a paper? Choose your book below and open the paper from there, or scan the QR
              code on the paper again.
            </p>
          ) : null}
          {path.startsWith("/orders/t/") ? (
            <p className="text-foreground">
              Opening an order from its email? The link may have been cut short:{" "}
              <Link href="/orders/lookup/">find your order</Link> with its number and your email address.
            </p>
          ) : null}
        </EmptyState>
        {books.length ? (
          <>
            <h2 className="mt-14 mb-6 text-title">Open a book</h2>
            <div className="grid-auto">
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
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
