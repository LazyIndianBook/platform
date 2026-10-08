// A product (Product artboard, Phone product; States "Shop closed and out of stock"): on the sheet with the subject's
// code in the margin and the papers inside in the marks, the cover beside the buy column (the kind and board in the
// mono voice, the title, the description, the choice as radio cards with BEST VALUE stamped, copies, Add to cart and
// Buy now, the three facts: stock, delivery, cancel; or the shop-closed and out-of-stock states), then on paper 2
// "What's inside" and "Try before you buy" (the open sample), the bundle's books, details and pictures, related books,
// and the reviews with the form for a buyer whose order was delivered. JSON-LD: Product (and Book) with its offer and
// rating, breadcrumbs. A renamed product's old address redirects to its new one (the API's 301).
import "../shop.css";

import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";

import { ShopClosed } from "@/components/shop/listing";
import { AddToCart, type BuyOption, ReviewForm, StockAlert } from "@/components/shop/product-actions";
import { CardPrice, ProductCover, ProductGrid } from "@/components/shop/product-card";
import { formatDate, isDigital, KIND_LABEL } from "@/components/shop/shop";
import { Unavailable } from "@/components/site/unavailable";
import { MarkdownBlock } from "@/components/solutions/markdown";
import { Marks, Sheet } from "@/components/ui/band";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { CoverPicture } from "@/components/ui/cover";
import { Morph } from "@/components/ui/morph";
import { getBook, getProducts } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import { getCategories, getProduct, getReviews, type Product } from "@/lib/api/shop";
import { getSessionUser } from "@/lib/auth/session";
import { inrShort } from "@/lib/format";
import { absolute, breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";
import { shortCode, subjectOf, TIERS, type TierCode } from "@/lib/site";

type Props = { params: Promise<{ slug: string }> };

async function load(slug: string): Promise<Product | null | "unavailable"> {
  try {
    return await getProduct(slug);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    const moved =
      error instanceof ApiError && error.status === 301 && (error.body as { redirect_to?: string })?.redirect_to;
    if (moved) permanentRedirect(`/shop/${moved}/`);
    return "unavailable";
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const product = await load(slug);
  if (!product || product === "unavailable") return { title: product ? "Shop" : "Page not found" };
  const where = product.kind === "digital" ? "in the ExamLeaf app" : "delivered across India";
  const { cover } = product;
  return pageMetadata({
    title: product.meta_title || product.title,
    path: `/shop/${product.slug}/`,
    description:
      product.meta_description ||
      `${product.title} for the Assam Board (ASSEB) Class 12 examination: ${inrShort(product.price)}, ${where}.`,
    image: product.og_image
      ? { url: product.og_image, width: 1200, height: 630 }
      : cover && { url: cover.src, width: cover.width, height: cover.height },
  });
}

/** What each tier of papers does for the student (the words printed on the books' covers). */
const TIER_TEXT: Record<TierCode, string> = {
  E: "build your basics",
  M: "strengthen your preparation",
  H: "challenge like a topper",
};

/** "E-01 to E-10", or "M-01" alone, for papers in their order. */
const range = (codes: string[]) =>
  codes.length > 1 ? `${shortCode(codes[0])} to ${shortCode(codes[codes.length - 1])}` : shortCode(codes[0]);

/** One of the three facts under Add to cart. */
function Fact({
  title,
  children,
  first = false,
}: {
  title: React.ReactNode;
  children: React.ReactNode;
  first?: boolean;
}) {
  return (
    <div
      className={first ? "flex flex-col gap-1 pt-3.5 pr-4" : "flex flex-col gap-1 border-l border-border px-4 pt-3.5"}
    >
      <strong className="text-[15px] leading-snug">{title}</strong>
      <span className="text-sm leading-snug text-muted-foreground">{children}</span>
    </div>
  );
}

export default async function ProductPage({ params }: Props) {
  const { slug } = await params;
  const here = `/shop/${slug}/`;
  const product = await load(slug);
  if (product === null) notFound();
  if (product === "unavailable") return <Unavailable what="This book's page" retry={here} />;

  const user = await getSessionUser();
  const [config, all, reviews, categories, book] = await Promise.all([
    getConfig(),
    getProducts().catch(() => [product]),
    getReviews(slug, Boolean(user)).catch(() => null),
    product.categories.length ? getCategories().catch(() => []) : [],
    product.book ? getBook(product.book).catch(() => null) : null,
  ]);
  const bySlug = new Map(all.map((item) => [item.slug, item]));
  const digital = isDigital(product, bySlug);
  const subject = subjectOf(product.subject);
  const open = config?.shop.open ?? false;

  // the choice: this book alone, or a bundle that holds it (Best value when it saves)
  const bundles =
    product.kind === "bundle"
      ? []
      : all.filter((item) => item.kind === "bundle" && item.bundle_items.some((line) => line.product === slug));
  const option = (item: Product, label: string): BuyOption => ({
    slug: item.slug,
    title: item.title,
    label,
    price: item.price,
    mrp: item.mrp,
    inStock: item.in_stock,
    digital: isDigital(item, bySlug),
    best: item.kind === "bundle" && Number(item.mrp) > Number(item.price),
  });
  const options = [
    option(product, bundles.length ? `${KIND_LABEL[product.kind]} only` : product.title),
    ...bundles.map((bundle) =>
      option(
        bundle,
        bundle.bundle_items.map((line) => KIND_LABEL[bySlug.get(line.product)?.kind ?? "bundle"]).join(" + "),
      ),
    ),
  ];
  const related = product.related.map((item) => bySlug.get(item)).filter((item): item is Product => Boolean(item));
  const shelves = categories.filter((category) => product.categories.includes(category.slug));
  const papers = book?.papers.filter((paper) => paper.is_published !== false) ?? [];
  const sample = papers.find((paper) => paper.is_sample);
  const tiers = (Object.keys(TIERS) as TierCode[])
    .map((tier) => ({ tier, papers: papers.filter((paper) => paper.tier === tier) }))
    .filter((group) => group.papers.length);
  const rated = reviews && reviews.count > 0 && reviews.average;
  const kindName = digital ? "course" : "book";
  const eyebrow = [
    KIND_LABEL[product.kind],
    subject?.name,
    book?.subject.board,
    book ? `Class ${book.subject.class_level}` : null,
  ].filter(Boolean);
  let section = 0;

  const details: [string, React.ReactNode][] = [
    ...(book
      ? ([
          ["Subject", book.subject.name],
          ["Board", book.subject.board],
          ["Class", book.subject.class_level],
        ] as [string, React.ReactNode][])
      : []),
    ...(book?.edition ? [["Edition", book.edition] as [string, React.ReactNode]] : []),
    ...(product.pages ? [["Pages", product.pages] as [string, React.ReactNode]] : []),
    ...(product.isbn ? [["ISBN", product.isbn] as [string, React.ReactNode]] : []),
    ...product.attributes.map((attribute) => [attribute.name, attribute.value] as [string, React.ReactNode]),
    ...(shelves.length
      ? [
          [
            "Shelves",
            shelves.map((shelf, index) => (
              <span key={shelf.slug}>
                {index ? " · " : ""}
                <Link href={`/shop/category/${shelf.slug}/`}>{shelf.name}</Link>
              </span>
            )),
          ] as [string, React.ReactNode],
        ]
      : []),
    digital
      ? [
          "Access",
          <>
            In the ExamLeaf app, for the account you buy with, as soon as you have paid ·{" "}
            <Link href="/refunds/">Refund and Cancellation Policy</Link>
          </>,
        ]
      : [
          "Delivery",
          <>
            Anywhere in India. Dispatch times and charges: <Link href="/shipping/">Shipping Policy</Link> · returns:{" "}
            <Link href="/refunds/">Refund and Cancellation Policy</Link>
          </>,
        ],
  ];

  // stock (from the product), delivery (the config's lowest fee), cancel (the API's refund terms)
  const feeFrom = config?.shipping.fee_from;
  const factsRow = digital ? (
    <>
      <Fact title="Opens when paid" first>
        In the ExamLeaf app, for the account you buy with
      </Fact>
      <Fact title="Nothing to post">No delivery fee</Fact>
      <Fact title="Refunds">
        <Link href="/refunds/">Refund and Cancellation Policy</Link>
      </Fact>
    </>
  ) : (
    <>
      <Fact title={product.in_stock ? "In stock" : <span className="text-hard">Out of stock</span>} first>
        Delivered anywhere in India
      </Fact>
      <Fact title="Delivery fee by state">
        {feeFrom ? `From ${inrShort(feeFrom)}; free` : "Free"} above an order value ·{" "}
        <Link href="/shipping/">Shipping</Link>
      </Fact>
      <Fact title="Cancel until packed">Refunded in 5–7 working days</Fact>
    </>
  );

  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": digital ? "Product" : ["Product", "Book"],
          name: product.title,
          url: absolute(here),
          sku: product.slug,
          ...(product.description ? { description: product.description } : {}),
          ...(product.cover ? { image: [product.cover.src, ...product.images.map((image) => image.src)] } : {}),
          ...(product.isbn ? { isbn: product.isbn } : {}),
          brand: { "@type": "Brand", name: "ExamLeaf" },
          offers: {
            "@type": "Offer",
            url: absolute(here),
            priceCurrency: "INR",
            price: product.price,
            availability: `https://schema.org/${product.in_stock ? "InStock" : "OutOfStock"}`,
          },
          ...(rated
            ? {
                aggregateRating: {
                  "@type": "AggregateRating",
                  ratingValue: reviews.average,
                  reviewCount: reviews.count,
                },
              }
            : {}),
        }}
      />
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Shop", path: "/shop/" },
          { name: product.title, path: here },
        ])}
      />

      <Sheet
        margin={product.subject ?? "₹"}
        marks={
          papers.length ? (
            <div className="pt-[248px]">
              <Marks items={[{ value: papers.length, label: "papers inside" }]} />
            </div>
          ) : null
        }
        className="shop-page"
        bodyClassName="nav:pt-7 nav:pb-16"
      >
        <Breadcrumb
          trail={[
            { label: "Shop", href: "/shop/" },
            ...(book && subject
              ? [{ label: subject.name, href: `/books/${book.slug}/` }, { label: KIND_LABEL[product.kind] }]
              : [{ label: product.title }]),
          ]}
        />
        <div className="grid gap-x-14 gap-y-4 nav:mt-3 nav:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
          <div className="flex flex-col items-center gap-3.5 nav:items-stretch">
            <div className="w-[200px] max-w-full nav:w-full">
              <Morph name={`cover-${product.slug}`}>
                <ProductCover
                  product={product}
                  alt={`Cover of ${product.title}`}
                  sizes="(min-width: 900px) 360px, 200px"
                  priority
                />
              </Morph>
            </div>
            {digital ? null : (
              <span className="hidden text-sm text-muted-foreground nav:block">An ExamLeaf publication</span>
            )}
          </div>
          <div className="flex min-w-0 flex-col gap-3.5 nav:gap-[18px] [&>*]:m-0">
            <p className="font-mono text-[11px] leading-[1.4] font-medium tracking-[0.05em] text-muted-foreground uppercase nav:text-[13px]">
              {eyebrow.join(" · ")}
            </p>
            <h1 className="text-[30px] leading-[1.05] nav:text-[52px] nav:leading-[1.02]">{product.title}</h1>
            {product.description ? (
              <div className="text-[15px] leading-relaxed text-ink/85 nav:text-lg nav:leading-[1.65] [&_p]:m-0 [&_p+p]:mt-3">
                <MarkdownBlock>{product.description}</MarkdownBlock>
              </div>
            ) : null}
            {options.length === 1 || !open || !product.in_stock ? (
              <p className="flex flex-wrap items-baseline gap-3">
                <CardPrice price={product.price} mrp={product.mrp} className="[&>strong]:text-[32px]" />
                {product.in_stock ? null : (
                  <span className="border-[1.5px] border-hard px-[7px] py-[5px] font-mono text-xs leading-none font-semibold text-hard uppercase">
                    Out of stock
                  </span>
                )}
              </p>
            ) : null}
            {!open ? (
              <ShopClosed open={false} />
            ) : product.in_stock ? (
              <>
                <AddToCart
                  options={options}
                  note={
                    <p className="m-0 text-sm text-muted-foreground nav:hidden">
                      {digital
                        ? "Opens in the app when paid · nothing to post"
                        : "In stock · delivery fee by state · cancel until packed"}
                    </p>
                  }
                />
                <div className="hidden grid-cols-3 border-t-[1.5px] border-foreground nav:grid">{factsRow}</div>
              </>
            ) : (
              <div className="flex flex-col gap-3.5 [&>*]:m-0">
                <Button
                  type="button"
                  size="lg"
                  disabled
                  className="self-stretch disabled:border-[#c9ccd2] disabled:bg-[#c9ccd2] disabled:text-[#4a5060] disabled:opacity-100 nav:self-start"
                >
                  Add to cart
                </Button>
                <p className="text-[15px] leading-relaxed text-ink/85">
                  {product.title} is out of stock for now. The worked solutions are free online behind each paper&apos;s
                  QR code meanwhile.
                </p>
                <StockAlert slug={slug} signedIn={Boolean(user)} here={here} />
              </div>
            )}
          </div>
        </div>
      </Sheet>

      {tiers.length || sample ? (
        <Sheet
          margin={`Q.${++section}`}
          className="shop-page border-t border-border bg-paper-2"
          bodyClassName="grid gap-8 py-9 nav:grid-cols-2 nav:gap-12 nav:pb-14"
        >
          {tiers.length ? (
            <div className="flex flex-col gap-3 [&>*]:m-0">
              <h2 className="text-[26px] leading-[1.15] nav:text-[30px]">What&apos;s inside</h2>
              <p className="leading-[1.7] text-ink/85">
                {product.kind === "solutions"
                  ? `The worked solutions of papers ${range(papers.map((paper) => paper.code))}, printed for working without a phone.`
                  : `Papers ${tiers
                      .map(({ tier, papers: group }) => `${range(group.map((paper) => paper.code))} ${TIER_TEXT[tier]}`)
                      .join(", ")}.`}
                {product.kind === "sample-papers" || product.kind === "bundle"
                  ? " A QR code on every paper opens its worked solutions on this site, free."
                  : ""}
              </p>
            </div>
          ) : null}
          {sample ? (
            <div className="flex flex-col gap-3 [&>*]:m-0">
              <h2 className="text-[26px] leading-[1.15] nav:text-[30px]">Try before you buy</h2>
              <p className="leading-[1.7] text-ink/85">
                Paper {shortCode(sample.code)}&apos;s solutions are open to everyone.{" "}
                <Link href={`/s/${sample.code}/`} className="font-bold">
                  Open them
                </Link>{" "}
                to see exactly what the QR codes lead to.
                {book ? (
                  <>
                    {" "}
                    Every paper of the book: <Link href={`/books/${book.slug}/`}>{book.title}</Link>.
                  </>
                ) : null}
              </p>
            </div>
          ) : null}
        </Sheet>
      ) : null}

      {product.bundle_items.length ? (
        <Sheet margin={`Q.${++section}`} className="shop-page border-t border-border" bodyClassName="py-9 nav:py-12">
          <h2 className="mt-0 mb-3 text-[26px] nav:text-[30px]">In this bundle</h2>
          <ul className="m-0 list-none border-t-[1.5px] border-foreground p-0">
            {product.bundle_items.map((line) => (
              <li key={line.product} className="border-b border-border">
                <Link href={`/shop/${line.product}/`} className="flex min-h-12 items-center gap-2 font-semibold">
                  {line.quantity} × {line.title} →
                </Link>
              </li>
            ))}
          </ul>
        </Sheet>
      ) : null}

      <Sheet
        margin={`Q.${++section}`}
        className={`shop-page border-t border-border ${product.bundle_items.length ? "bg-paper-2" : ""}`}
        bodyClassName="py-9 nav:py-12"
      >
        <h2 className="mt-0 mb-4 text-[26px] nav:text-[30px]">Details</h2>
        <dl className="m-0 max-w-[46rem] border-t-[1.5px] border-foreground">
          {details.map(([term, value]) => (
            <div
              key={term}
              className="grid grid-cols-1 gap-x-6 gap-y-0.5 border-b border-border py-2.5 nav:grid-cols-[10rem_1fr]"
            >
              <dt className="font-mono text-xs leading-6 font-medium tracking-[0.05em] text-muted-foreground uppercase">
                {term}
              </dt>
              <dd className="m-0 min-w-0 [overflow-wrap:anywhere]">{value}</dd>
            </div>
          ))}
        </dl>
        {product.images.length ? (
          <div className="mt-8 grid-auto [--min:200px]">
            {product.images.map((image) => (
              <figure key={image.src} className="m-0 flex flex-col gap-2">
                <CoverPicture
                  src={image}
                  alt={image.alt}
                  sizes="(min-width: 1168px) 280px, (min-width: 560px) 45vw, 90vw"
                  className="h-auto w-full rounded-lg"
                />
                {image.alt ? <figcaption className="text-[15px] text-muted-foreground">{image.alt}</figcaption> : null}
              </figure>
            ))}
          </div>
        ) : null}
      </Sheet>

      {related.length ? (
        <Sheet margin={`Q.${++section}`} className="shop-page border-t border-border" bodyClassName="py-9 nav:py-12">
          <h2 className="mt-0 mb-5 text-[26px] nav:text-[30px]">You may also need</h2>
          <ProductGrid products={related} label="You may also need" />
        </Sheet>
      ) : null}

      <Sheet
        id="reviews"
        margin={`Q.${++section}`}
        className="shop-page border-t border-border"
        bodyClassName="flex flex-col gap-5 py-9 nav:py-12 [&>*]:m-0"
      >
        <h2 className="text-[26px] nav:text-[30px]">Reviews</h2>
        {reviews === null ? (
          <p className="text-muted-foreground">The reviews cannot be loaded just now.</p>
        ) : (
          <>
            {rated ? (
              <p className="text-lg">
                <strong>{reviews.average} out of 5</strong> from {reviews.count} review
                {reviews.count === 1 ? "" : "s"} by buyers
              </p>
            ) : null}
            {reviews.results.length ? (
              <ul className="m-0 max-w-[46rem] list-none border-t-[1.5px] border-foreground p-0">
                {reviews.results.map((review, index) => (
                  <li
                    key={`${review.created}-${index}`}
                    className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 border-b border-border py-4"
                  >
                    <div className="flex min-w-0 flex-col gap-1.5 [&>*]:m-0">
                      {review.text ? (
                        <p className="font-read text-[17px] leading-[1.6] whitespace-pre-line">{review.text}</p>
                      ) : null}
                      <p className="text-sm text-muted-foreground">Verified buyer · {formatDate(review.created)}</p>
                    </div>
                    <span className="font-mono text-base font-semibold text-red-ink">
                      {review.rating}/5<span className="sr-only"> stars</span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">No reviews yet.</p>
            )}
            {reviews.can_review ? <ReviewForm slug={slug} what={kindName} /> : null}
          </>
        )}
        <p>
          <Link href="/shop/" className="inline-flex min-h-11 items-center font-bold">
            ← All books
          </Link>
        </p>
      </Sheet>
    </>
  );
}
