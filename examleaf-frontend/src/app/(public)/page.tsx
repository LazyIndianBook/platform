// Home, Direction A "Answer Script" (design: ExamLeaf A - Public.dc.html, artboard "A Home"). Same data as before
// (getBooks, getProducts, getConfig, getSessionUser) and the same honest fallbacks: Unavailable when the books can't
// be read, no prices section when the shop answers nothing, FAQ answers that follow the config. Layout: each
// section is a Sheet (margin | content behind the red double rule | marks); Q.2 is a ruled table of the books
// (subject, papers, full marks, time) and the hero's figure circles its total. Phones follow "Phone home": Q.1 in the
// eyebrow, the figures in a row under the text, no picture. One emphasis per view (the red italic), no animation on
// load; the cover morph into the Book page is kept on the subject rows.
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Unavailable } from "@/components/site/unavailable";
import { Accordion } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Marker, Marks, NightBand, Sheet } from "@/components/ui/band";
import { buttonVariants } from "@/components/ui/button";
import { CoverPicture } from "@/components/ui/cover";
import { Morph } from "@/components/ui/morph";
import { Price } from "@/components/ui/price";
import { type Book, bookFacts, getBooks, getProducts, type Product } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { getSessionUser } from "@/lib/auth/session";
import { JsonLd, organizationJsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";
import { subjectOf } from "@/lib/site";

import { PhoneFigures } from "./phone-figures";

export const metadata = pageMetadata({ path: "/" });

/** Q.2's columns (A Home): cover, subject, papers, full marks, time, the link's words; narrower between 900 and
 *  1200 px, where the drawn widths would leave the subject no room. */
const BOOK_ROW =
  "grid grid-cols-[64px_minmax(0,1fr)_64px_88px_64px_auto] gap-4 min-[1200px]:grid-cols-[72px_minmax(0,1fr)_110px_120px_110px_150px] min-[1200px]:gap-6";

const KIND_LABEL: Record<Product["kind"], string> = {
  "sample-papers": "Sample Papers",
  solutions: "Solutions",
  bundle: "Bundle · Sample Papers + Solutions",
  digital: "Digital",
};

function offers(products: Product[]) {
  const kinds = ["sample-papers", "bundle"] as const;
  return kinds.flatMap((kind) => {
    const ofKind = products
      .filter((product) => product.kind === kind)
      .sort((a, b) => Number(a.price) - Number(b.price));
    if (!ofKind.length) return [];
    return [{ product: ofKind[0], from: ofKind.some((product) => product.price !== ofKind[0].price) }];
  });
}

function offerText(product: Product) {
  if (product.kind === "sample-papers")
    return "30 full papers: 10 Easy, 10 Medium, 10 Hard. A QR code on every paper opens its solutions, free.";
  return "Both books together. The Solutions book prints the worked solutions of all 30 papers, for working without a phone.";
}

const STEPS = [
  ["i", "Buy the book", "Printed and delivered anywhere in India. Pay with UPI, a card or net banking."],
  ["ii", "Sit a paper", "Three hours against the clock, as in the examination hall."],
  ["iii", "Scan its QR code", "The code printed on the paper opens its solutions on this site."],
  ["iv", "Check, then save your marks", "Mark each step against the solution, then save your score to My record."],
] as const;

export default async function HomePage() {
  let books: Book[];
  try {
    books = await getBooks();
  } catch {
    return <Unavailable what="The home page" />;
  }
  const [config, user, products] = await Promise.all([getConfig(), getSessionUser(), getProducts().catch(() => [])]);
  const facts = books.map(bookFacts);
  const sample = books.flatMap((book) => book.papers).find((paper) => paper.is_sample);
  const bookOffers = offers(products);
  const samePrice = bookOffers.every((offer) => !offer.from);
  const requireLogin = config?.solutions_require_login ?? true;
  const consentByLink = config?.parental_consent === "verified";
  const physicsCover = books.find((book) => subjectOf(book.subject.code)?.key === "physics")?.cover;
  const maths = facts.find((_, index) => subjectOf(books[index].subject.code)?.key === "maths")?.full_marks;
  const marks = facts[0]?.full_marks;

  return (
    <>
      <JsonLd data={organizationJsonLd(config?.support.email)} />

      {/* Q.1 hero: the promise, two actions, and a real solution sheet as the picture (phones: the figures in a row
          under the text, no picture, as Phone home draws it) */}
      <Sheet
        margin="Q.1"
        className="max-nav:[&>.sheet-margin]:hidden"
        marks={
          <div className="pt-10">
            <Marks
              items={[
                { value: 30, label: "papers in each book" },
                ...(marks
                  ? [{ value: marks, label: maths && maths !== marks ? `marks; ${maths} in Maths` : "marks each" }]
                  : []),
                { value: "3h", label: "every paper" },
              ]}
            />
          </div>
        }
        bodyClassName="flex flex-wrap items-center gap-12 max-nav:gap-8 max-nav:pt-7"
      >
        <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-6 max-nav:gap-[18px] [&>*]:m-0">
          <p className="label-mono uppercase">
            <span className="nav:hidden">
              <span aria-hidden="true">Q.1 · </span>ASSEB · Class 12 · 2027 exam
            </span>
            <span className="max-nav:hidden">Assam Board (ASSEB) · Class 12 · for the 2027 exam</span>
          </p>
          <h1 className="text-display leading-[0.98] tracking-[-0.025em]">
            Sample papers with <Marker>free solutions</Marker>
          </h1>
          <p className="max-w-[30em] text-lead leading-[1.65] text-ink/85 max-nav:text-[17px]">
            Physics, Chemistry, Mathematics and Biology, in the board&apos;s pattern. Sit a paper, scan its QR code, and
            check every step with the marks it earns.
          </p>
          <PhoneFigures
            items={[
              { value: 30, label: "papers" },
              ...(marks ? [{ value: marks, label: "marks" }] : []),
              { value: "3h", label: "each" },
            ]}
          />
          <div className="flex flex-wrap gap-3">
            <Link
              href="/shop/"
              className={buttonVariants({ variant: "primary", size: "lg", className: "max-nav:w-full" })}
            >
              <span>Buy the books</span>
              <ArrowRight aria-hidden="true" />
            </Link>
            {sample ? (
              <Link
                href={`/s/${sample.code}/`}
                className={buttonVariants({ variant: "secondary", size: "lg", className: "max-nav:w-full" })}
              >
                See a sample paper
              </Link>
            ) : null}
          </div>
          <p className="flex flex-wrap gap-x-5 gap-y-1 text-[15px] text-muted-foreground max-nav:hidden">
            <span>Free QR solutions</span>
            <span aria-hidden="true">·</span>
            <span>Secure payment through Razorpay</span>
            <span aria-hidden="true">·</span>
            <span>Delivered across India</span>
          </p>
        </div>
        <figure className="relative m-0 h-[500px] min-w-0 flex-[0_1_440px] max-nav:hidden">
          {physicsCover ? (
            // decorative (the same cover is a real link in Q.2): the AVIF/WebP sizes, not the 176 KB PNG original,
            // fetched lazily so a phone, where it is hidden, never loads it and the words paint first
            <CoverPicture
              src={physicsCover}
              alt=""
              sizes="250px"
              className="absolute top-0 right-0 w-[250px] rotate-[5deg] rounded-cover shadow-cover max-nav:hidden"
            />
          ) : null}
          <div className="absolute bottom-0 left-0 flex w-[390px] max-w-full flex-col gap-3.5 border border-border bg-card px-6 py-6 shadow-sheet max-nav:static max-nav:w-full">
            <div className="flex justify-between label-mono text-xs">
              <span>PHY-M04 · MEDIUM</span>
              <span>SOLUTIONS</span>
            </div>
            <div className="grid grid-cols-[40px_minmax(0,1fr)_30px] gap-2 font-head text-base leading-normal">
              <strong className="font-bold">2(c)</strong>
              <span>
                An electrical appliance draws a current of 2.5 A from a 220 V supply. Calculate the power consumed, and
                the energy consumed in 10 minutes.
              </span>
              <span className="text-right font-mono text-sm text-muted-foreground">[2]</span>
            </div>
            <div className="flex flex-col gap-2 border-t border-rule-soft pt-3 font-head text-base">
              <div className="flex items-baseline justify-between pl-12">
                <span>
                  <i>P</i> = <i>VI</i> = 220 × 2.5 = 550 W
                </span>
                <span className="font-mono text-[15px] font-semibold text-red-ink">✓ 1</span>
              </div>
              <div className="flex items-baseline justify-between pl-12">
                <span>
                  <i>W</i> = <i>Pt</i> = 550 × 600 = 3.30 × 10<sup>5</sup> J
                </span>
                <span className="font-mono text-[15px] font-semibold text-red-ink">✓ 1</span>
              </div>
              <div className="flex items-center justify-between border-t border-dashed border-border pt-2 pl-12">
                <span className="font-body text-sm font-semibold text-muted-foreground">Total</span>
                <span className="inline-flex size-[30px] items-center justify-center rounded-full border-[1.5px] border-red-ink font-mono text-[15px] font-semibold text-red-ink">
                  2
                </span>
              </div>
            </div>
            <figcaption className="text-[13px] text-muted-foreground">
              From Sample Paper M-04, Physics: the page its QR code opens.
            </figcaption>
          </div>
        </figure>
      </Sheet>

      {/* Q.2 the books as a contents table: subject, papers, full marks, time (phones: one line of figures). Each row
          is the link to its book; the cover still morphs into the Book page's. */}
      <Sheet
        margin="Q.2"
        marks={books.length ? `[${books.length} books]` : null}
        className="border-t border-border"
        id="books"
      >
        <div className="mb-8 flex flex-col gap-2.5 max-nav:mb-4 [&>*]:m-0">
          <h2 className="max-nav:text-[28px]">Open a book, then any paper&apos;s solutions</h2>
          <p className="text-lg text-muted-foreground">
            Each book holds 30 papers. The solutions of every one are free.
          </p>
        </div>
        {books.length ? (
          <div>
            <div aria-hidden="true" className={`${BOOK_ROW} border-b-[1.5px] border-foreground pb-3 max-nav:hidden`}>
              <span />
              <span className="label-mono text-xs tracking-[0.06em] uppercase">Subject</span>
              <span className="label-mono text-xs tracking-[0.06em] uppercase">Papers</span>
              <span className="label-mono text-xs tracking-[0.06em] uppercase">Full marks</span>
              <span className="label-mono text-xs tracking-[0.06em] uppercase">Time</span>
              <span />
            </div>
            <ul className="m-0 list-none p-0">
              {books.map((book, index) => {
                const subject = subjectOf(book.subject.code);
                const key = subject?.key ?? "physics";
                const fullMarks = facts[index]?.full_marks;
                const time = facts[index]?.time_text;
                const short = time?.replace(/ hours?$/, " h");
                return (
                  <li key={book.slug}>
                    <Link
                      href={`/books/${book.slug}/`}
                      className={`${BOOK_ROW} items-center border-b border-border py-4 text-foreground no-underline hover:bg-paper-2 hover:text-foreground hover:no-underline active:translate-y-px max-nav:grid-cols-[48px_minmax(0,1fr)_auto] max-nav:gap-3.5 max-nav:border-t max-nav:border-b-0 max-nav:py-2.5`}
                    >
                      {book.cover ? (
                        <Morph name={`book-${key}`}>
                          <CoverPicture
                            src={book.cover}
                            alt=""
                            sizes="(min-width: 900px) 64px, 44px"
                            className="w-16 rounded-[3px] shadow-cover max-nav:w-11"
                          />
                        </Morph>
                      ) : (
                        <span
                          aria-hidden="true"
                          className={`subject-${key} block aspect-[480/678] w-16 rounded-[3px] bg-(--base) max-nav:w-11`}
                        />
                      )}
                      <span className="flex min-w-0 flex-col gap-1 max-nav:gap-0.5">
                        <span className="font-head text-[30px] leading-[1.1] font-semibold max-nav:text-[21px]">
                          {subject?.name ?? book.subject.name}
                        </span>
                        <span className="text-[15px] text-muted-foreground max-nav:hidden">{book.title}</span>
                        <span className="text-[13px] text-muted-foreground nav:hidden">
                          {book.papers.length} papers{fullMarks ? ` · ${fullMarks} marks` : ""}
                          {short ? ` · ${short}` : ""}
                        </span>
                      </span>
                      <span className="font-mono text-[22px] leading-none font-medium max-nav:hidden">
                        {book.papers.length}
                        <span className="sr-only"> papers,</span>
                      </span>
                      <span className="font-mono text-[22px] leading-none font-medium max-nav:hidden">
                        {fullMarks ?? "—"}
                        <span className="sr-only"> full marks,</span>
                      </span>
                      <span className="font-mono text-[22px] leading-none font-medium max-nav:hidden">
                        <span aria-hidden="true">{short ?? "—"}</span>
                        <span className="sr-only">{time}</span>
                      </span>
                      <span className="inline-flex items-center gap-1.5 justify-self-end font-bold whitespace-nowrap text-primary">
                        <span className="max-[1200px]:sr-only">Open the book</span>
                        <ArrowRight aria-hidden="true" className="size-5" />
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : (
          <p>The books are being prepared. Please come back soon.</p>
        )}
        <ul className="m-0 mt-8 grid list-none grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-6 p-0">
          {[
            ["bg-easy", "10 Easy", "E-01 to E-10", "build your basics"],
            ["bg-medium", "10 Medium", "M-01 to M-10", "strengthen your preparation"],
            ["bg-hard", "10 Hard", "H-01 to H-10", "challenge like a topper"],
          ].map(([swatch, title, range, text]) => (
            <li key={title} className="flex items-baseline gap-3">
              <span aria-hidden="true" className={`size-3 flex-none ${swatch}`} />
              <span>
                <strong>{title}</strong> <span className="font-mono text-sm text-muted-foreground">{range}</span>
                <br />
                <span className="text-[15px] text-muted-foreground">{text}</span>
              </span>
            </li>
          ))}
        </ul>
      </Sheet>

      {/* Q.3 how it works */}
      <Sheet margin="Q.3" className="border-t border-border bg-paper-2">
        <div className="mb-10 flex flex-col gap-3.5 [&>*]:m-0">
          <h2>Buy, sit, scan, check</h2>
          <p className="max-w-[22em] font-head text-[clamp(22px,2.6vw,30px)] leading-snug text-ink/85 italic">
            The book is the exam hall; this site is the answer key.
          </p>
        </div>
        <ol className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(200px,100%),1fr))] border-t-[1.5px] border-foreground p-0">
          {STEPS.map(([n, title, text]) => (
            <li key={n} className="flex flex-col gap-2.5 pt-5 pr-6">
              <span aria-hidden="true" className="font-mono text-[15px] font-semibold text-red-ink">
                {n}
              </span>
              <strong className="font-head text-[22px] leading-tight font-semibold">{title}</strong>
              <span className="text-base leading-relaxed text-muted-foreground">{text}</span>
            </li>
          ))}
        </ol>
      </Sheet>

      {/* Q.4 the books and their prices, from the shop */}
      {bookOffers.length ? (
        <Sheet margin="Q.4" marks="[₹]" className="border-t border-border" id="prices">
          <div className="mb-8 flex flex-col gap-2.5 [&>*]:m-0">
            <h2>Two books for each subject</h2>
            {samePrice ? (
              <p className="text-lg text-muted-foreground">The price is the same for every subject.</p>
            ) : null}
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-6">
            {bookOffers.map(({ product, from }) => (
              <div
                key={product.slug}
                className={`relative flex flex-col gap-3.5 bg-card p-7 ${product.kind === "bundle" ? "border-[1.5px] border-foreground" : "border border-border"}`}
              >
                {product.kind === "bundle" ? (
                  <Badge variant="stamp" className="absolute top-5 right-5">
                    Best value
                  </Badge>
                ) : null}
                {/* the stamp's room beside the long bundle label, so the two never overlap on a narrow card */}
                <span className={`label-mono text-xs uppercase ${product.kind === "bundle" ? "pr-28" : ""}`}>
                  {KIND_LABEL[product.kind]}
                </span>
                <Price price={product.price} mrp={product.mrp} from={from} size="offer" />
                <p className="m-0 text-base leading-relaxed text-muted-foreground">{offerText(product)}</p>
                <Link
                  href={product.kind === "bundle" ? `/shop/${product.slug}/` : "/shop/"}
                  className="mt-auto inline-flex min-h-11 items-center gap-1.5 font-bold"
                >
                  {product.kind === "bundle" ? "See the bundle" : "Choose a subject"}
                  <ArrowRight aria-hidden="true" className="size-5" />
                </Link>
              </div>
            ))}
          </div>
          <p className="mt-6 mb-0 flex flex-wrap gap-x-7 gap-y-1 text-[15px] text-muted-foreground">
            <span>Delivered anywhere in India</span>
            <span>UPI, card or net banking through Razorpay</span>
            <span>Cancel on the order&apos;s page until it is packed</span>
          </p>
        </Sheet>
      ) : null}

      {/* Q.5 questions */}
      <Sheet
        margin={bookOffers.length ? "Q.5" : "Q.4"}
        className="border-t border-border"
        bodyClassName="grid grid-cols-[minmax(0,340px)_minmax(0,1fr)] gap-12 max-nav:grid-cols-1 max-nav:gap-6"
      >
        <h2 className="m-0">Questions parents and students ask</h2>
        <div className="border-t-[1.5px] border-foreground">
          <Accordion summary="Are the solutions really free?" name="faq" open>
            <p>
              Yes. Every paper in a Sample Papers book has a QR code; scanning it opens that paper&apos;s worked
              solutions on this site. You can also choose the paper on its book&apos;s page.
              {requireLogin ? " You only need to register once, with your email address." : null}
            </p>
          </Accordion>
          <Accordion summary="Do I need the Solutions book as well?" name="faq">
            <p>
              Not to see the answers: they are free online. The Solutions book prints the worked solutions of all 30
              papers, for working without a phone.
            </p>
          </Accordion>
          <Accordion summary="How much is delivery?" name="faq">
            <p>
              It depends on your state, and it is free above an order value. The <Link href="/shipping/">Shipping</Link>{" "}
              page has the fees.
            </p>
          </Accordion>
          <Accordion summary="Can I cancel an order?" name="faq">
            <p>
              Yes, on the order&apos;s page, until it is packed. A paid order is refunded in full to the account, card
              or UPI ID you paid from, within 5–7 working days. The <Link href="/refunds/">Refunds</Link> page has the
              details.
            </p>
          </Accordion>
          <Accordion summary="I am under 18. Can I register?" name="faq">
            <p>
              {consentByLink
                ? `Yes. Give your parent's or guardian's email address${config?.auth.sms ? " or mobile number" : ""} and we send them a link to confirm. Until they do, you can read the solutions but not save marks or order books.`
                : "Yes. Your parent or guardian reads the privacy notice and ticks the consent box on the Register page for you."}
            </p>
          </Accordion>
        </div>
      </Sheet>

      {/* the closing call to action on the ink band */}
      <NightBand>
        <div className="sheet">
          <div className="sheet-margin" />
          <div className="sheet-body flex flex-wrap items-center justify-between gap-8 border-l-[3px] border-double border-red-ink">
            <div className="flex min-w-0 flex-[1_1_380px] flex-col gap-2.5 [&>*]:m-0">
              <h2>Start with one paper this week</h2>
              <p className="text-muted-foreground">
                Delivered anywhere in India. The solutions of every paper are free.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link href="/shop/" className={buttonVariants({ variant: "primary", size: "lg" })}>
                <span>Buy the books</span>
                <ArrowRight aria-hidden="true" />
              </Link>
              <Link
                href={user ? "/account/orders/" : "/orders/lookup/"}
                className={buttonVariants({ variant: "secondary", size: "lg" })}
              >
                {user ? "My orders" : "Find your order"}
              </Link>
            </div>
          </div>
          <div className="sheet-marks" />
        </div>
      </NightBand>
    </>
  );
}
