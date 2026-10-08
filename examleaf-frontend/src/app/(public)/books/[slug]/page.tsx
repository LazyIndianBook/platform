// A book, Direction A (design: ExamLeaf A - Public.dc.html, "Book"): the hero on a Sheet (margin: the subject code,
// marks: [papers] [marks] [time]), cover morphing from the Home row, buy buttons from the shop, the log-in prompt,
// then each tier on its own Sheet with the papers as cells; the open sample is marked in red ink. Phones follow "Phone
// book": the cover beside the title, the figures in a row, five codes to a row in each tier. Data, metadata, JSON-LD,
// 404 and Unavailable handling are unchanged.
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

import { PhoneFigures } from "../../phone-figures";

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
  const figures =
    facts && papers.length
      ? { papers: papers.length, marks: facts.full_marks, time: facts.time_text.replace(/ hours?/, "h") }
      : null;

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
        className="max-nav:[&>.sheet-margin]:hidden"
        marks={
          figures ? (
            <div className="pt-10">
              <Marks
                items={[
                  { value: figures.papers, label: "papers" },
                  { value: figures.marks, label: "marks each" },
                  { value: figures.time, label: "each paper" },
                ]}
              />
            </div>
          ) : null
        }
        bodyClassName="pt-7 max-nav:pt-4"
      >
        <Breadcrumb trail={[{ label: "Home", href: "/" }, { label: name }]} />
        {/* the cover beside the title; on phones the rest runs under both (Phone book) */}
        <div
          className={
            book.cover
              ? "mt-6 grid grid-cols-[minmax(160px,260px)_minmax(0,1fr)] grid-rows-[auto_1fr] items-start gap-x-12 gap-y-4 max-nav:mt-0 max-nav:grid-cols-[120px_minmax(0,1fr)] max-nav:grid-rows-none max-nav:items-end max-nav:gap-x-4 max-nav:gap-y-3.5"
              : "mt-6 flex flex-col gap-4 max-nav:mt-0"
          }
        >
          {book.cover ? (
            <Morph name={`book-${subject?.key ?? slug}`}>
              <div className={`cover book-cover subject-${subject?.key} row-span-2 max-nav:row-span-1`}>
                <CoverPicture
                  src={book.cover}
                  alt={`Cover of ${book.title}`}
                  sizes="(min-width: 900px) 260px, 120px"
                  priority
                />
              </div>
            </Morph>
          ) : null}
          <div className="flex min-w-0 flex-col gap-4 max-nav:gap-2 [&>*]:m-0">
            <p className="label-mono uppercase max-nav:text-[11px]">
              <span className="nav:hidden">
                Sample Papers · {book.subject.board} {book.subject.class_level}
              </span>
              <span className="max-nav:hidden">
                Sample Papers · {book.subject.board} · Class {book.subject.class_level}
                {book.edition ? ` · ${book.edition}` : ""}
              </span>
            </p>
            <h1 className="max-nav:text-[28px] max-nav:leading-[1.05]">{book.title}</h1>
          </div>
          <div className="flex min-w-0 flex-col gap-4 max-nav:col-span-2 max-nav:gap-3.5 [&>*]:m-0">
            {figures ? (
              <PhoneFigures
                items={[
                  { value: figures.papers, label: "papers" },
                  { value: figures.marks, label: "marks each" },
                  { value: figures.time, label: "each" },
                ]}
              />
            ) : null}
            <p className="max-w-[34em] text-lg leading-relaxed text-ink/85 max-nav:text-base">
              The solutions to every paper are free{requireLogin ? " for registered students" : ""}.
              <span className="max-nav:hidden"> Scan the QR code printed on the paper, or choose it here.</span>
              {sample && requireLogin ? (
                <span className="nav:hidden">
                  {" "}
                  Try{" "}
                  <Link href={`/s/${sample.code}/`} className="font-bold">
                    Paper {shortCode(sample.code)}
                  </Link>{" "}
                  first: open to everyone.
                </span>
              ) : null}
            </p>
            {sample && requireLogin ? (
              <p className="max-nav:hidden">
                Try{" "}
                <Link href={`/s/${sample.code}/`} className="font-bold">
                  Paper {shortCode(sample.code)}
                </Link>{" "}
                first: its solutions are open to everyone, no account needed.
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
                      className: "max-nav:w-full",
                    })}
                  >
                    {product.kind === "sample-papers" ? `Buy this book · ${inrShort(product.price)}` : "Solutions book"}
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
            className="border-t border-border bg-paper-2 max-nav:[&>.sheet-margin]:hidden"
            bodyClassName="py-10 nav:py-12 max-nav:py-[18px]"
            aria-labelledby={`tier-${group.tier}`}
          >
            <div className="mb-5 flex flex-wrap items-baseline gap-x-3.5 gap-y-1 max-nav:mb-3 max-nav:gap-x-2.5">
              <span aria-hidden="true" className={`size-3 max-nav:size-2.5 ${TIER_SWATCH[group.tier]}`} />
              <h2 id={`tier-${group.tier}`} className="m-0 text-[clamp(26px,3vw,32px)] max-nav:text-[22px]">
                {TIERS[group.tier]}
                <span className="max-nav:hidden"> papers</span>
              </h2>
              <span className="label-mono max-nav:text-xs">
                {shortCode(group.papers[0].code)} to {shortCode(group.papers[group.papers.length - 1].code)}
              </span>
            </div>
            {/* phones: five codes to a row, the open sample ruled in red (its words stay for screen readers) */}
            <div className="grid grid-cols-[repeat(auto-fill,minmax(min(150px,100%),1fr))] gap-3 max-nav:grid-cols-5 max-nav:gap-1.5">
              {group.papers.map((paper) => {
                const open = paper.is_sample && requireLogin;
                return (
                  <CardLink
                    key={paper.code}
                    href={`/s/${paper.code}/`}
                    className={open ? "max-nav:border-red-ink" : ""}
                  >
                    <span className="flex flex-col gap-1 px-4 py-3.5 max-nav:min-h-12 max-nav:items-center max-nav:justify-center max-nav:p-0">
                      <span className="flex items-center justify-between gap-2 font-head text-[22px] leading-tight font-semibold max-nav:font-mono max-nav:text-sm">
                        {shortCode(paper.code)}
                        <ArrowRight aria-hidden="true" className="size-[18px] text-primary max-nav:hidden" />
                      </span>
                      {facts ? (
                        <span className="text-sm text-muted-foreground max-nav:hidden">
                          {facts.full_marks} marks · {facts.time_text}
                        </span>
                      ) : null}
                      {open ? (
                        <span className="font-mono text-xs font-medium tracking-[0.04em] text-red-ink uppercase max-nav:sr-only">
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
