// A book, Direction A (design: ExamLeaf A - Public.dc.html, "Book"): the hero on a Sheet (margin: the subject code,
// marks: [papers] [marks] [time]), cover morphing from the Home row, buy buttons from the shop, the log-in prompt,
// then each tier on its own Sheet with the papers as cells; the open sample is marked in red ink. Data, metadata,
// JSON-LD, 404 and Unavailable handling are unchanged.
import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Unavailable } from "@/components/site/unavailable";
import { Alert } from "@/components/ui/alert";
import { Marks, Sheet } from "@/components/ui/band";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { buttonVariants } from "@/components/ui/button";
import { CardLink } from "@/components/ui/card";
import { CoverPicture } from "@/components/ui/cover";
import { Morph } from "@/components/ui/morph";
import { EmptyState } from "@/components/ui/empty-state";
import { type Book, bookFacts, getBook, getProducts } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import { getSessionUser } from "@/lib/auth/session";
import { inrShort } from "@/lib/format";
import { absolute, breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";
import { shortCode, subjectOf, TIERS, type TierCode } from "@/lib/site";

type Props = { params: Promise<{ slug: string }> };

const TIER_SWATCH: Record<TierCode, string> = { E: "bg-easy", M: "bg-medium", H: "bg-hard" };

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

  const [config, user, products] = await Promise.all([getConfig(), getSessionUser(), getProducts().catch(() => [])]);
  const facts = bookFacts(book);
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

      <Sheet
        margin={book.subject.code}
        marks={
          facts && papers.length ? (
            <Marks
              items={[
                { value: papers.length, label: "papers" },
                { value: facts.full_marks, label: "marks each" },
                { value: facts.time_text.replace(/ hours?/, "h"), label: "each paper" },
              ]}
            />
          ) : null
        }
        bodyClassName="pt-7"
      >
        <Breadcrumb trail={[{ label: "Home", href: "/" }, { label: name }]} />
        <div className="mt-6 flex flex-wrap items-start gap-x-12 gap-y-8">
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
          <div className="flex min-w-0 flex-[1_1_380px] flex-col gap-4 [&>*]:m-0">
            <p className="label-mono uppercase">
              Sample Papers · {book.subject.board} · Class {book.subject.class_level}
              {book.edition ? ` · ${book.edition}` : ""}
            </p>
            <h1>{book.title}</h1>
            <p className="max-w-[34em] text-lg leading-relaxed text-ink/85">
              The solutions to every paper are free{requireLogin ? " for registered students" : ""}. Scan the QR code
              printed on the paper, or choose it here.
            </p>
            {sample && requireLogin ? (
              <p>
                Try{" "}
                <Link href={`/s/${sample.code}/`} className="font-bold">
                  Paper {shortCode(sample.code)}
                </Link>{" "}
                first: its solutions are open to everyone, no account needed.
              </p>
            ) : null}
            {facts && papers.length ? (
              <p className="flex flex-wrap gap-x-6 font-mono text-[15px] text-muted-foreground nav:hidden">
                <span>[{papers.length}] papers</span>
                <span>[{facts.full_marks}] marks each</span>
                <span>{facts.time_text}</span>
              </p>
            ) : null}
            {forSale.length ? (
              <div className="flex flex-wrap items-center gap-3">
                {forSale.map((product) => (
                  <Link
                    key={product.slug}
                    href={`/shop/${product.slug}/`}
                    className={buttonVariants({
                      variant: product.kind === "sample-papers" ? "primary" : "secondary",
                      size: "lg",
                    })}
                  >
                    {product.kind === "sample-papers" ? "Buy this book" : "Solutions book"} · {inrShort(product.price)}
                    {product.in_stock ? null : <span className="font-normal"> (out of stock)</span>}
                  </Link>
                ))}
              </div>
            ) : null}
            {!user ? (
              <Alert title="Keep your marks" className="max-w-[36em]">
                <p>Registered students can save their marks after each paper and see their average for each tier.</p>
                <p className="flex flex-wrap gap-x-4 gap-y-1">
                  <Link
                    href={`/account/signup/?next=/books/${slug}/`}
                    className="inline-flex min-h-11 items-center font-bold"
                  >
                    Register free
                  </Link>
                  <Link
                    href={`/account/login/?next=/books/${slug}/`}
                    className="inline-flex min-h-11 items-center font-bold"
                  >
                    Log in
                  </Link>
                </p>
              </Alert>
            ) : null}
          </div>
        </div>
      </Sheet>

      {!papers.length ? (
        <Sheet margin="—" className="border-t border-border bg-paper-2">
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
        </Sheet>
      ) : null}

      {tiers
        .filter((group) => group.papers.length)
        .map((group) => (
          <Sheet
            key={group.tier}
            margin={group.tier}
            marks={`[${group.papers.length}]`}
            className="border-t border-border bg-paper-2"
            bodyClassName="py-10 nav:py-12"
            aria-labelledby={`tier-${group.tier}`}
          >
            <div className="mb-5 flex flex-wrap items-baseline gap-x-3.5 gap-y-1">
              <span aria-hidden="true" className={`size-3 ${TIER_SWATCH[group.tier]}`} />
              <h2 id={`tier-${group.tier}`} className="m-0 text-[clamp(26px,3vw,32px)]">
                {TIERS[group.tier]} papers
              </h2>
              <span className="label-mono">
                {shortCode(group.papers[0].code)} to {shortCode(group.papers[group.papers.length - 1].code)}
              </span>
            </div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(min(150px,100%),1fr))] gap-3">
              {group.papers.map((paper) => {
                const open = paper.is_sample && requireLogin;
                return (
                  <CardLink key={paper.code} href={`/s/${paper.code}/`}>
                    <span className="flex flex-col gap-1 px-4 py-3.5">
                      <span className="flex items-center justify-between gap-2 font-head text-[22px] leading-tight font-semibold">
                        {shortCode(paper.code)}
                        <ArrowRight aria-hidden="true" className="size-[18px] text-primary" />
                      </span>
                      {facts ? (
                        <span className="text-sm text-muted-foreground">
                          {facts.full_marks} marks · {facts.time_text}
                        </span>
                      ) : null}
                      {open ? (
                        <span className="font-mono text-xs font-medium tracking-[0.04em] text-red-ink uppercase">
                          Open to everyone
                        </span>
                      ) : null}
                      <span className="sr-only">, {TIERS[group.tier]} paper: open the solutions</span>
                    </span>
                  </CardLink>
                );
              })}
            </div>
          </Sheet>
        ))}
    </>
  );
}
