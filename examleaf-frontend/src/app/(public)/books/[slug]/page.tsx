// A book (Book artboard; Django's book.html): breadcrumb, the cover (its view-transition name pairs it with the
// Home tile), chips, title, facts, buy buttons from the shop, the log-in prompt, then the 30 papers by tier, each
// a link to its solutions; the open sample is marked.
import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Unavailable } from "@/components/site/unavailable";
import { Alert } from "@/components/ui/alert";
import { Badge, TIER_VARIANT } from "@/components/ui/badge";
import { QRule } from "@/components/ui/band";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { buttonVariants } from "@/components/ui/button";
import { CardLink } from "@/components/ui/card";
import { CoverPicture } from "@/components/ui/cover";
import { Morph } from "@/components/ui/morph";
import { EmptyState } from "@/components/ui/empty-state";
import { type Book, getBook, getBookFacts, getProducts } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import { getSessionUser } from "@/lib/auth/session";
import { inrShort } from "@/lib/format";
import { absolute, breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";
import { shortCode, subjectOf, TIERS, type TierCode } from "@/lib/site";

type Props = { params: Promise<{ slug: string }> };

async function load(slug: string): Promise<Book | null | "unavailable"> {
  try {
    return await getBook(slug);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    return "unavailable";
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const book = await load(slug);
  if (!book || book === "unavailable") return { title: book ? "Book" : "Page not found" };
  return pageMetadata({
    title: book.title,
    path: `/books/${slug}/`,
    description: `${book.title}: papers for the ${book.subject.board} Class ${book.subject.class_level} examination, Easy, Medium and Hard. Choose a paper and open its worked solutions.`,
    image: book.cover,
  });
}

export default async function BookPage({ params }: Props) {
  const { slug } = await params;
  const book = await load(slug);
  if (book === null) notFound();
  if (book === "unavailable") return <Unavailable what="This book's page" retry={`/books/${slug}/`} />;

  const [config, user, facts, products] = await Promise.all([
    getConfig(),
    getSessionUser(),
    getBookFacts(slug).catch(() => null),
    getProducts().catch(() => []),
  ]);
  const subject = subjectOf(book.subject.code);
  const name = subject?.name ?? book.subject.name;
  const papers = book.papers.filter((paper) => paper.is_published !== false);
  const tiers = (Object.keys(TIERS) as TierCode[]).map((tier) => ({
    tier,
    papers: papers.filter((paper) => paper.tier === tier),
  }));
  const sample = papers.find((paper) => paper.is_sample);
  const requireLogin = config?.solutions_require_login ?? true;
  const forSale = products.filter((product) => product.book === slug && product.kind !== "bundle");
  const samplePapers = forSale.find((product) => product.kind === "sample-papers");

  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "Book",
          name: book.title,
          url: absolute(`/books/${slug}/`),
          ...(book.cover ? { image: absolute(book.cover) } : {}),
          ...(book.edition ? { bookEdition: book.edition } : {}),
          inLanguage: "en",
          publisher: { "@type": "Organization", name: "ExamLeaf" },
          ...(samplePapers
            ? {
                offers: {
                  "@type": "Offer",
                  url: absolute(`/shop/${samplePapers.slug}/`),
                  priceCurrency: "INR",
                  price: samplePapers.price,
                  availability: `https://schema.org/${samplePapers.in_stock ? "InStock" : "OutOfStock"}`,
                },
              }
            : {}),
        }}
      />
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name, path: `/books/${slug}/` },
        ])}
      />

      <section className="pt-7 pb-(--section)">
        <div className="container-site">
          <Breadcrumb trail={[{ label: "Home", href: "/" }, { label: name }]} />
          <div className="flex flex-wrap items-start gap-x-12 gap-y-8">
            {book.cover ? (
              <Morph name={`book-${subject?.key ?? slug}`}>
                <div className={`cover book-cover subject-${subject?.key} flex-[0_0_260px] max-nav:basis-40`}>
                  <CoverPicture
                    src={book.cover}
                    alt={`Cover of ${book.title}`}
                    sizes="(min-width: 900px) 260px, 160px"
                    priority
                  />
                </div>
              </Morph>
            ) : null}
            <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-3.5 [&>*]:m-0">
              <div className="flex flex-wrap gap-2">
                {subject ? <Badge variant={subject.key}>{name}</Badge> : null}
                <Badge>Sample Papers</Badge>
              </div>
              <h1>{book.title}</h1>
              <p className="text-muted-foreground">
                {book.subject.board} · Class {book.subject.class_level}
                {book.edition ? ` · ${book.edition}` : ""}
              </p>
              <p>
                The solutions to every paper are free{requireLogin ? " for registered students" : ""}. Scan the QR code
                printed on the paper, or choose it here.
              </p>
              {sample && requireLogin ? (
                <p>
                  Try <Link href={`/s/${sample.code}/`}>Paper {shortCode(sample.code)}</Link> first: its solutions are
                  open to everyone, no account needed.
                </p>
              ) : null}
              {facts && papers.length ? (
                <dl className="m-0 my-1 flex flex-wrap gap-x-10 gap-y-3">
                  {[
                    ["papers", papers.length],
                    ["marks each", facts.full_marks],
                    ["each paper", facts.time_text],
                  ].map(([label, value]) => (
                    <div key={label} className="flex flex-col gap-1">
                      <dt className="order-2 text-[15px] text-muted-foreground">{label}</dt>
                      <dd className="m-0 font-head text-[28px] leading-none font-extrabold text-primary">{value}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              {forSale.length ? (
                <div className="flex flex-wrap items-center gap-3">
                  {forSale.map((product) => (
                    <Link
                      key={product.slug}
                      href={`/shop/${product.slug}/`}
                      className={buttonVariants({
                        variant: product.kind === "sample-papers" ? "accent" : "secondary",
                        size: "lg",
                      })}
                    >
                      {product.kind === "sample-papers" ? "Buy this book" : "Solutions book"} ·{" "}
                      {inrShort(product.price)}
                    </Link>
                  ))}
                </div>
              ) : null}
              {!user ? (
                <Alert title="Keep your marks">
                  <p>Registered students can save their marks after each paper and see their average for each tier.</p>
                  <p className="flex flex-wrap gap-x-4 gap-y-1">
                    <Link
                      href={`/account/signup/?next=/books/${slug}/`}
                      className="inline-flex min-h-11 items-center font-semibold"
                    >
                      Register free
                    </Link>
                    <Link
                      href={`/account/login/?next=/books/${slug}/`}
                      className="inline-flex min-h-11 items-center font-semibold"
                    >
                      Log in
                    </Link>
                  </p>
                </Alert>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <section className="bg-secondary section">
        <div className="container-site">
          {!papers.length ? (
            <EmptyState
              art="sheet"
              title="The papers are on their way"
              action={
                <Link href="/#books" className={buttonVariants({ variant: "primary" })}>
                  Choose another book
                </Link>
              }
            >
              <p>This book&apos;s papers are still being set. The other books are ready.</p>
            </EmptyState>
          ) : null}
          {tiers
            .filter((group) => group.papers.length)
            .map((group, index) => (
              <div key={group.tier} className="not-first:mt-14">
                <QRule
                  number={index + 1}
                  label={`${shortCode(group.papers[0].code)} to ${shortCode(group.papers[group.papers.length - 1].code)}`}
                />
                <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-2">
                  <Badge variant={TIER_VARIANT[group.tier]}>{TIERS[group.tier]}</Badge>
                  <h2 className="m-0">{TIERS[group.tier]} papers</h2>
                </div>
                <div className="grid-auto gap-4 [--min:180px]">
                  {group.papers.map((paper) => {
                    const open = paper.is_sample && requireLogin;
                    return (
                      <CardLink
                        key={paper.code}
                        href={`/s/${paper.code}/`}
                        aria-label={`Paper ${shortCode(paper.code)}, ${TIERS[group.tier]}: open the solutions${open ? ", no account needed" : ""}`}
                      >
                        <span className="flex flex-col gap-1 p-4">
                          <span className="flex items-center justify-between gap-2 font-head text-[22px] leading-tight font-extrabold text-primary">
                            {shortCode(paper.code)}
                            <ArrowRight aria-hidden="true" className="size-5" />
                          </span>
                          {facts ? (
                            <span className="text-[15px] text-muted-foreground">
                              {facts.full_marks} marks · {facts.time_text}
                            </span>
                          ) : null}
                          {open ? <span className="text-[15px] text-muted-foreground">Open to everyone</span> : null}
                        </span>
                      </CardLink>
                    );
                  })}
                </div>
              </div>
            ))}
        </div>
      </section>
    </>
  );
}
