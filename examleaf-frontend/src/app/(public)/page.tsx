// Home (Design canvas, Main and HomePhone artboards; the Django site's home.html for the copy): the hero with the
// cover stage, Q.1 what's inside, Q.2 the subject tiles, Q.3 how it works, Q.4 the books with prices from the shop,
// the FAQ and the final call to action. Two effects in view at most: the cover lift and the sticker press; the
// marker draws further down.
import {
  ArrowRight,
  ChartLine,
  CircleCheck,
  Clock,
  CreditCard,
  FileText,
  Lock,
  Package,
  QrCode,
  Truck,
} from "lucide-react";
import Link from "next/link";

import { Unavailable } from "@/components/site/unavailable";
import { Accordion } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { NightBand, Marker, QRule } from "@/components/ui/band";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { CoverStage } from "@/components/ui/cover-stage";
import { Price } from "@/components/ui/price";
import { QrCard } from "@/components/ui/qr-card";
import { SubjectTile } from "@/components/ui/subject-tile";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { type Book, bookFacts, getBooks, getProducts, type Product } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { getSessionUser } from "@/lib/auth/session";
import { JsonLd, organizationJsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";
import { subjectOf } from "@/lib/site";

export const metadata = pageMetadata({ path: "/" });

const KIND_LABEL: Record<Product["kind"], string> = {
  "sample-papers": "Sample Papers",
  solutions: "Solutions",
  bundle: "Bundle",
  digital: "Digital",
};

/** Q.4: per kind of printed book, the cheapest one on sale; "from" when others of the kind cost more. */
function offers(products: Product[]) {
  const kinds = ["sample-papers", "solutions", "bundle"] as const;
  return kinds.flatMap((kind) => {
    const ofKind = products
      .filter((product) => product.kind === kind)
      .sort((a, b) => Number(a.price) - Number(b.price));
    if (!ofKind.length) return [];
    return [{ product: ofKind[0], from: ofKind.some((product) => product.price !== ofKind[0].price) }];
  });
}

function offerTitle(product: Product) {
  const subject = subjectOf(product.subject)?.name;
  return product.kind !== "bundle" && subject ? product.title.replace(`${subject} `, "") : product.title;
}

function offerText(product: Product) {
  if (product.kind === "sample-papers")
    return "30 full papers: 10 Easy, 10 Medium, 10 Hard. A QR code on every paper opens its solutions, free.";
  if (product.kind === "solutions")
    return "The worked solutions of all 30 papers, step by step, with the marks each step earns.";
  return `Both ${subjectOf(product.subject)?.name ?? "the"} books together.`;
}

const iconClasses = "size-5 shrink-0 text-accent";

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

  return (
    <>
      <JsonLd data={organizationJsonLd(config?.support.email)} />

      <NightBand className="bg-[radial-gradient(52%_60%_at_76%_50%,rgba(76,194,101,0.3),transparent_70%),linear-gradient(180deg,#0b2a5b_0,#07122b_260px)] pt-12 pb-18 max-nav:bg-[radial-gradient(70%_34%_at_50%_44%,rgba(76,194,101,0.3),transparent_70%),linear-gradient(180deg,#0b2a5b_0,#07122b_200px)] max-nav:pt-6 max-nav:pb-10">
        <div className="container-site flex flex-wrap items-center gap-10 max-nav:flex-col max-nav:items-stretch max-nav:gap-5">
          <div className="flex min-w-0 flex-[1_1_460px] flex-col gap-5 max-nav:contents [&>*]:m-0">
            <p className="text-[15px] leading-normal font-semibold text-muted-foreground">
              Assam Board (ASSEB) · Class 12 · for the 2027 exam
            </p>
            <h1 className="text-display leading-[1.08] max-nav:text-[34px]">Sample papers with free solutions</h1>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-3 max-nav:order-2">
              <span className="numeral text-[clamp(88px,10vw,128px)]">30</span>
              <div className="flex min-w-0 flex-[1_1_180px] flex-col gap-2.5">
                <span className="font-head text-[22px] leading-snug font-bold text-balance">papers in each book</span>
                <span className="flex flex-wrap gap-2">
                  <Badge variant="easy">10 Easy</Badge>
                  <Badge variant="medium">10 Medium</Badge>
                  <Badge variant="hard">10 Hard</Badge>
                </span>
              </div>
            </div>
            <p className="max-w-[34rem] text-lead leading-[1.7] text-muted-foreground max-nav:order-2">
              Physics, Chemistry, Mathematics and Biology, in the board&apos;s pattern. Sit a paper, scan its QR code,
              and check every step with the marks it earns.
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-3 max-nav:order-2">
              <Link
                href="/shop/"
                className={buttonVariants({ variant: "accent", size: "lg", className: "max-nav:w-full" })}
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
            <ul className="m-0 flex list-none flex-wrap gap-x-6 gap-y-2.5 p-0 text-[15px] leading-normal font-semibold text-muted-foreground max-nav:order-2">
              <li className="inline-flex items-center gap-2">
                <FileText aria-hidden="true" className={iconClasses} />
                Board&apos;s pattern
              </li>
              <li className="inline-flex items-center gap-2">
                <QrCode aria-hidden="true" className={iconClasses} />
                Free QR solutions
              </li>
              <li className="inline-flex items-center gap-2">
                <Lock aria-hidden="true" className={iconClasses} />
                Secure payment through Razorpay
              </li>
              <li className="inline-flex items-center gap-2">
                <Truck aria-hidden="true" className={iconClasses} />
                Delivered across India
              </li>
            </ul>
          </div>
          <div className="min-w-0 flex-[1_1_420px] max-nav:order-1 max-nav:flex-none [&_.stage]:max-nav:pt-2 [&_.stage]:max-nav:pb-6">
            <CoverStage
              books={books
                .filter((book) => book.cover)
                .map((book) => ({ href: `/books/${book.slug}/`, cover: book.cover!, title: book.title }))}
            />
          </div>
        </div>
      </NightBand>

      <section className="section">
        <div className="container-site">
          <div className="mb-8 [&>*]:m-0">
            <QRule number={1} label="What's inside" />
            <h2 className="mb-3!">
              Everything you need to practise, and <Marker draw>the solutions free</Marker>
            </h2>
            <p className="max-w-[40rem] text-lead text-muted-foreground">
              Each subject has two books: Sample Papers, and Solutions printed for working without a phone.
            </p>
          </div>
          <div className="flex flex-wrap gap-(--gap)">
            <Card className="flex-[1_1_400px]">
              <CardContent className="flex-1 gap-3.5 p-7">
                <span className="numeral text-[112px]">30</span>
                <h3>full papers in every book</h3>
                <p className="text-muted-foreground">
                  In the board&apos;s pattern, each with its time and marks. Start with the Easy ten, finish with the
                  Hard ten.
                </p>
                <div aria-hidden="true" className="mt-auto flex h-2.5 gap-1">
                  <span className="flex-1 rounded-pill bg-easy" />
                  <span className="flex-1 rounded-pill bg-medium" />
                  <span className="flex-1 rounded-pill bg-hard" />
                </div>
                <ul className="m-0 list-none p-0">
                  {[
                    ["easy", "10 Easy", "E-01 to E-10", "build your basics"],
                    ["medium", "10 Medium", "M-01 to M-10", "strengthen your preparation"],
                    ["hard", "10 Hard", "H-01 to H-10", "challenge like a topper"],
                  ].map(([variant, chip, range, text]) => (
                    <li
                      key={variant}
                      className="flex flex-wrap items-center gap-x-3 gap-y-0.5 border-b border-border py-2.5 text-small text-muted-foreground"
                    >
                      <Badge variant={variant as "easy" | "medium" | "hard"} className="min-w-[88px] justify-center">
                        {chip}
                      </Badge>
                      <span className="font-head text-small leading-snug font-bold text-foreground">{range}</span>
                      <span>{text}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
            <div className="grid flex-[1_1_400px] grid-cols-[repeat(auto-fit,minmax(min(240px,100%),1fr))] gap-(--gap)">
              {[
                [
                  QrCode,
                  "A QR code on every paper",
                  "Scan it and that paper's worked solutions open on this site, free.",
                ],
                [
                  CircleCheck,
                  "Marks for every step",
                  "Each solution shows the steps and the marks each one earns, as the board's marking scheme gives them.",
                ],
                [
                  Clock,
                  "70 or 80 marks, 3 hours",
                  "Physics, Chemistry and Biology papers carry 70 marks, Mathematics 80. Every paper runs 3 hours.",
                ],
                [ChartLine, "Your own record", "Save your marks after each paper and see your average for each tier."],
              ].map(([Icon, title, text]) => {
                const FeatureIcon = Icon as typeof QrCode;
                return (
                  <Card key={title as string}>
                    <CardContent>
                      <span className="inline-flex size-11 items-center justify-center rounded-lg bg-secondary text-accent">
                        <FeatureIcon aria-hidden="true" className="size-6" />
                      </span>
                      <h3>{title as string}</h3>
                      <p className="text-muted-foreground">{text as string}</p>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
          <Card className="mt-(--gap)">
            <CardContent>
              <ul className="m-0 flex list-none flex-wrap gap-x-8 gap-y-3 p-0 text-[15px] leading-normal font-semibold text-foreground">
                <li className="inline-flex items-center gap-2">
                  <Truck aria-hidden="true" className={iconClasses} />
                  Delivered anywhere in India
                </li>
                <li className="inline-flex items-center gap-2">
                  <CreditCard aria-hidden="true" className={iconClasses} />
                  UPI, card or net banking through Razorpay
                </li>
                <li className="inline-flex items-center gap-2">
                  <Package aria-hidden="true" className={iconClasses} />
                  Cancel on the order&apos;s page until it is packed
                </li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="bg-secondary section" id="books">
        <div className="container-site">
          <div className="mb-8 [&>*]:m-0">
            <QRule number={2} label="Choose your subject" />
            <h2 className="mb-3!">Open a book, then any paper&apos;s solutions</h2>
            <p className="max-w-[40rem] text-lead text-muted-foreground">
              Each book holds 30 papers. The solutions of every one are free.
            </p>
          </div>
          {books.length ? (
            <div className="grid-auto max-nav:-mx-(--gutter) max-nav:snap-x max-nav:snap-mandatory max-nav:scroll-px-(--gutter) max-nav:auto-cols-[80%] max-nav:grid-flow-col max-nav:grid-cols-none max-nav:overflow-x-auto max-nav:px-(--gutter) max-nav:pt-1 max-nav:pb-3 max-nav:[&>*]:snap-start">
              {books.map((book, index) => {
                const subject = subjectOf(book.subject.code);
                return (
                  <SubjectTile
                    key={book.slug}
                    subject={subject?.key ?? "physics"}
                    name={subject?.name ?? book.subject.name}
                    href={`/books/${book.slug}/`}
                    papers={book.papers.length}
                    marks={facts[index]?.full_marks}
                    time={facts[index]?.time_text}
                    cover={book.cover}
                  />
                );
              })}
            </div>
          ) : (
            <p>The books are being prepared. Please come back soon.</p>
          )}
        </div>
      </section>

      <section className="section">
        <div className="container-site">
          <div className="mb-8 [&>*]:m-0">
            <QRule number={3} label="How it works" />
            <h2 className="mb-3!">Buy, sit, scan, check</h2>
            <p className="max-w-[40rem] text-lead text-muted-foreground">
              The book is the exam hall; this site is the answer key.
            </p>
          </div>
          <div className="flex flex-wrap items-start gap-x-10 gap-y-8">
            <ol className="m-0 flex min-w-0 flex-[1_1_360px] list-none flex-col gap-6 p-0">
              {[
                ["Buy the book", "Printed and delivered anywhere in India. Pay with UPI, a card or net banking."],
                ["Sit a paper", "Three hours against the clock, as in the examination hall."],
                ["Scan its QR code", "The code printed on the paper opens its solutions on this site."],
                [
                  "Check, then save your marks",
                  "Mark each step against the solution, then save your score to My record.",
                ],
              ].map(([title, text], index) => (
                <li key={title} className="grid grid-cols-[40px_1fr] gap-4">
                  <span
                    aria-hidden="true"
                    className="flex size-10 items-center justify-center rounded-full border-2 border-primary font-head text-[17px] leading-none font-extrabold text-primary"
                  >
                    {index + 1}
                  </span>
                  <div>
                    <strong className="block font-head text-[19px] leading-snug font-bold text-heading">{title}</strong>
                    <p className="mt-1 mb-0 text-muted-foreground">{text}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="flex min-w-0 flex-[1_1_440px] flex-col gap-4">
              <QrCard
                subject="physics"
                subjectName="Physics"
                tier="M"
                code="PHY-M04"
                eyebrow="Sample Paper M-04 · Medium · ASSEB Class 12"
                title="Physics: solutions"
                headingLevel="p"
                compact
                facts={[
                  { label: "Full marks", value: 70 },
                  { label: "Pass marks", value: 21 },
                  { label: "Time", value: "3 hours" },
                ]}
              />
              <Card>
                <CardContent>
                  <p className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-3">
                    <span className="font-head text-[17px] leading-[1.7] font-extrabold text-primary">2(c)</span>
                    <span>
                      An electrical appliance draws a current of 2.5 A from a 220 V supply. Calculate the power
                      consumed, and the energy consumed in 10 minutes.
                    </span>
                    <span className="font-semibold text-muted-foreground">[2]</span>
                  </p>
                  <Table caption="Marking steps">
                    <thead>
                      <tr>
                        <TableHead>Step</TableHead>
                        <TableHead numeric>Marks</TableHead>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <TableCell>
                          <i>P</i> = <i>VI</i> = 220 × 2.5 = 550 W
                        </TableCell>
                        <TableCell numeric>1</TableCell>
                      </tr>
                      <tr>
                        <TableCell>
                          <i>W</i> = <i>Pt</i> = 550 × 600 = 3.30 × 10<sup>5</sup> J
                        </TableCell>
                        <TableCell numeric>1</TableCell>
                      </tr>
                    </tbody>
                    <tfoot>
                      <tr>
                        <td>Total</td>
                        <td className="num">2</td>
                      </tr>
                    </tfoot>
                  </Table>
                  <p className="rounded-btn bg-secondary px-3.5 py-2.5">
                    <strong>Final answer:</strong> 550 W; 3.30 × 10<sup>5</sup> J
                  </p>
                </CardContent>
              </Card>
              <p className="m-0 text-caption text-muted-foreground">
                From Sample Paper M-04, Physics: the page its QR code opens.
              </p>
            </div>
          </div>
        </div>
      </section>

      {bookOffers.length ? (
        <section className="bg-secondary section" id="prices">
          <div className="container-site">
            <div className="mb-8 [&>*]:m-0">
              <QRule number={4} label="The books" />
              <h2 className="mb-3!">Two books for each subject</h2>
              {samePrice ? (
                <p className="text-lead text-muted-foreground">The price is the same for every subject.</p>
              ) : null}
            </div>
            <div className="grid-auto [--min:280px]">
              {bookOffers.map(({ product, from }) => (
                <Card key={product.slug}>
                  <CardContent className="flex-1">
                    <div className="flex flex-wrap gap-2">
                      <Badge>{KIND_LABEL[product.kind]}</Badge>
                      {product.kind === "bundle" ? <Badge variant="gold">Best value</Badge> : null}
                    </div>
                    <h3>{offerTitle(product)}</h3>
                    <Price price={product.price} mrp={product.mrp} from={from} size="offer" />
                    <p className="text-muted-foreground">{offerText(product)}</p>
                  </CardContent>
                  <CardFooter>
                    <Link
                      href={product.kind === "bundle" ? `/shop/${product.slug}/` : "/shop/"}
                      className="inline-flex min-h-11 items-center gap-1.5 font-semibold"
                    >
                      {product.kind === "bundle" ? "See the bundle" : "Choose a subject"}
                      <ArrowRight aria-hidden="true" className="size-5" />
                    </Link>
                  </CardFooter>
                </Card>
              ))}
            </div>
            <div className="mt-8 flex">
              <Link href="/shop/" className={buttonVariants({ variant: "primary", size: "lg" })}>
                <span>Go to the shop</span>
                <ArrowRight aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>
      ) : null}

      <section className={bookOffers.length ? "section" : "bg-secondary section"}>
        <div className="container-site">
          <div className="mb-8 [&>*]:m-0">
            <QRule number={bookOffers.length ? 5 : 4} label="Questions" />
            <h2>Questions parents and students ask</h2>
          </div>
          <div className="max-w-(--measure)">
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
                It depends on your state, and it is free above an order value. The{" "}
                <Link href="/shipping/">Shipping</Link> page has the fees.
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
        </div>
      </section>

      <NightBand className="border-b border-night-line section">
        <div className="container-site flex flex-wrap items-center justify-between gap-x-10 gap-y-6">
          <div className="[&>*]:m-0">
            <h2 className="mb-2!">Start with one paper this week</h2>
            <p className="text-muted-foreground">Delivered anywhere in India. The solutions of every paper are free.</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Link href="/shop/" className={buttonVariants({ variant: "accent", size: "lg" })}>
              <span>Buy the books</span>
              <ArrowRight aria-hidden="true" />
            </Link>
            {user ? (
              <Link href="/account/orders/" className={buttonVariants({ variant: "ghost", size: "lg" })}>
                My orders
              </Link>
            ) : (
              <Link href="/orders/lookup/" className={buttonVariants({ variant: "ghost", size: "lg" })}>
                Find your order
              </Link>
            )}
          </div>
        </div>
      </NightBand>
    </>
  );
}
