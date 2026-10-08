// A product (Product artboard; Django's shop/product.html): the cover beside the buy column (chips, title, price with
// MRP and saving, the description, the bundle choice, copies and Add to cart, or the shop-closed and out-of-stock
// states), the bundle's books, what is inside the book, details and pictures, related books, then the reviews with
// the form for a buyer whose order was delivered. JSON-LD: Product (and Book) with its offer and rating, breadcrumbs.
import { ArrowLeft, ArrowRight, Package, QrCode, Smartphone, Truck } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AddToCart, type BuyOption, ReviewForm, StockAlert } from "@/components/shop/product-actions";
import { ProductCover, ProductGrid } from "@/components/shop/product-card";
import { formatDate, isDigital, KIND_LABEL } from "@/components/shop/shop";
import { Unavailable } from "@/components/site/unavailable";
import { MarkdownBlock } from "@/components/solutions/markdown";
import { Alert } from "@/components/ui/alert";
import { Badge, TIER_VARIANT } from "@/components/ui/badge";
import { QRule } from "@/components/ui/band";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent } from "@/components/ui/card";
import { Price } from "@/components/ui/price";
import { getBook, getBookFacts, getProducts } from "@/lib/api/catalogue";
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
    return "unavailable";
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const product = await load(slug);
  if (!product || product === "unavailable") return { title: product ? "Shop" : "Page not found" };
  const where = product.kind === "digital" ? "in the ExamLeaf app" : "delivered across India";
  return pageMetadata({
    title: product.title,
    path: `/shop/${slug}/`,
    description: `${product.title} for the Assam Board (ASSEB) Class 12 examination: ${inrShort(product.price)}, ${where}.`,
    image: product.cover,
  });
}

const TIER_TEXT: Record<TierCode, string> = {
  E: "to build your basics",
  M: "at the board's level",
  H: "to stretch you",
};

export default async function ProductPage({ params }: Props) {
  const { slug } = await params;
  const here = `/shop/${slug}/`;
  const product = await load(slug);
  if (product === null) notFound();
  if (product === "unavailable") return <Unavailable what="This book's page" retry={here} />;

  const user = await getSessionUser();
  const [config, all, reviews, categories, book, facts] = await Promise.all([
    getConfig(),
    getProducts().catch(() => [product]),
    getReviews(slug, Boolean(user)).catch(() => null),
    product.categories.length ? getCategories().catch(() => []) : [],
    product.book ? getBook(product.book).catch(() => null) : null,
    product.book ? getBookFacts(product.book).catch(() => null) : null,
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
  const sample = papers.find((paper) => paper.is_sample) ?? papers[0];
  const tiers = (Object.keys(TIERS) as TierCode[])
    .map((tier) => ({ tier, papers: papers.filter((paper) => paper.tier === tier) }))
    .filter((group) => group.papers.length);
  const rated = reviews && reviews.count > 0 && reviews.average;
  const kindName = digital ? "course" : "book";
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
          ...(product.cover ? { image: [product.cover, ...product.images.map((image) => image.url)] } : {}),
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

      <section className="pt-7 pb-(--section)">
        <div className="container-site">
          <Breadcrumb
            trail={[
              { label: "Shop", href: "/shop/" },
              ...(book && subject
                ? [{ label: subject.name, href: `/books/${book.slug}/` }, { label: KIND_LABEL[product.kind] }]
                : [{ label: product.title }]),
            ]}
          />
          <div className="flex flex-wrap items-start gap-x-12 gap-y-8">
            <div className="flex-[0_1_340px] max-nav:basis-44">
              <ProductCover
                product={product}
                alt={`Cover of ${product.title}`}
                sizes="(min-width: 900px) 340px, 176px"
                priority
              />
            </div>
            <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-4 [&>*]:m-0">
              <p className="flex flex-wrap gap-2">
                <Badge>{KIND_LABEL[product.kind]}</Badge>
                {subject ? <Badge variant={subject.key}>{subject.name}</Badge> : null}
              </p>
              {book ? (
                <p className="text-[15px] font-semibold text-muted-foreground">
                  {book.subject.board} · Class {book.subject.class_level}
                </p>
              ) : null}
              <h1>{product.title}</h1>
              <Price price={product.price} mrp={product.mrp} size="page" />
              {product.description ? (
                <div className="prose">
                  <MarkdownBlock>{product.description}</MarkdownBlock>
                </div>
              ) : null}
              {!open ? (
                <Alert title="Shop opens soon">
                  <p>Orders open in a few days.</p>
                </Alert>
              ) : product.in_stock ? (
                <AddToCart options={options} />
              ) : (
                <StockAlert slug={slug} signedIn={Boolean(user)} here={here} />
              )}
              <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
                {digital ? (
                  <li className="flex items-start gap-2">
                    <Smartphone aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-accent" />
                    Opens in the ExamLeaf app as soon as you have paid
                  </li>
                ) : (
                  <li className="flex items-start gap-2">
                    <Truck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-accent" />
                    <span>
                      Delivered anywhere in India: charges in the <Link href="/shipping/">Shipping Policy</Link>
                    </span>
                  </li>
                )}
                {product.kind === "sample-papers" || product.kind === "bundle" ? (
                  <li className="flex items-start gap-2">
                    <QrCode aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-accent" />A QR code on every paper
                    opens its solutions on this site, free
                  </li>
                ) : null}
                {digital ? null : (
                  <li className="flex items-start gap-2">
                    <Package aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-accent" />
                    Cancel on the order&apos;s page until it is packed
                  </li>
                )}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {product.bundle_items.length ? (
        <section className="bg-secondary section">
          <div className="container-site">
            <QRule number={++section} label="In the bundle" />
            <h2>In this bundle</h2>
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {product.bundle_items.map((line) => (
                <li key={line.product}>
                  <Link
                    href={`/shop/${line.product}/`}
                    className="inline-flex min-h-11 items-center gap-2 font-semibold"
                  >
                    {line.quantity} × {line.title}
                    <ArrowRight aria-hidden="true" className="size-5" />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      {tiers.length ? (
        <section className="section">
          <div className="container-site">
            <QRule number={++section} label="In the book" />
            <h2>What&apos;s inside</h2>
            <ul className="m-0 grid-auto list-none p-0 [--min:190px]">
              {tiers.map(({ tier, papers: group }) => (
                <li key={tier}>
                  <Card className="h-full">
                    <CardContent>
                      <span className="numeral text-[56px] text-primary">{group.length}</span>
                      <Badge variant={TIER_VARIANT[tier]} className="self-start">
                        {TIERS[tier]}
                      </Badge>
                      <h3 className="text-[19px]">
                        {TIERS[tier]} paper{group.length === 1 ? "" : "s"}
                      </h3>
                      <p className="text-muted-foreground">
                        {shortCode(group[0].code)} to {shortCode(group[group.length - 1].code)}, {TIER_TEXT[tier]}.
                      </p>
                    </CardContent>
                  </Card>
                </li>
              ))}
              {facts ? (
                <li>
                  <Card className="h-full">
                    <CardContent>
                      <span className="numeral text-[56px] text-primary">{facts.full_marks}</span>
                      <h3 className="text-[19px]">marks, {facts.time_text}</h3>
                      <p className="text-muted-foreground">Each paper, in the board&apos;s pattern.</p>
                    </CardContent>
                  </Card>
                </li>
              ) : null}
              {product.kind === "sample-papers" ? (
                <li>
                  <Card className="h-full">
                    <CardContent>
                      <QrCode aria-hidden="true" className="size-8 text-accent" />
                      <h3 className="text-[19px]">Free solutions</h3>
                      <p className="text-muted-foreground">
                        A QR code on every paper opens its marking-scheme solutions here.
                      </p>
                    </CardContent>
                  </Card>
                </li>
              ) : null}
            </ul>
            {sample && book ? (
              <p className="mt-5 mb-0">
                See a sample: <Link href={`/s/${sample.code}/`}>Paper {shortCode(sample.code)}</Link> ·{" "}
                <Link href={`/books/${book.slug}/`}>all the papers in the book</Link>
              </p>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className={tiers.length ? "bg-secondary section" : "section"}>
        <div className="container-site">
          <QRule number={++section} label={digital ? "About the course" : "About the book"} />
          <h2>Details</h2>
          <dl className="m-0 grid max-w-[46rem] grid-cols-[minmax(7rem,auto)_1fr] gap-x-6 gap-y-3">
            {details.map(([term, value]) => (
              <div key={term} className="contents">
                <dt className="font-semibold">{term}</dt>
                <dd className="m-0">{value}</dd>
              </div>
            ))}
          </dl>
          {product.images.length ? (
            <div className="mt-8 grid-auto [--min:200px]">
              {product.images.map((image) => (
                <figure key={image.url} className="m-0 flex flex-col gap-2">
                  {/* eslint-disable-next-line @next/next/no-img-element -- the API's picture as it is (no sizes in the API yet) */}
                  <img
                    src={image.url}
                    alt={image.alt ?? ""}
                    loading="lazy"
                    decoding="async"
                    className="h-auto w-full rounded-lg"
                  />
                  {image.alt ? (
                    <figcaption className="text-[15px] text-muted-foreground">{image.alt}</figcaption>
                  ) : null}
                </figure>
              ))}
            </div>
          ) : null}
        </div>
      </section>

      {related.length ? (
        <section className="section">
          <div className="container-site">
            <QRule number={++section} label={digital ? "With this course" : "With this book"} />
            <h2>You may also need</h2>
            <ProductGrid products={related} label="You may also need" />
          </div>
        </section>
      ) : null}

      <section id="reviews" className="section">
        <div className="container-site flex flex-col gap-5 [&>*]:m-0">
          <QRule number={++section} label="From buyers" />
          <h2>Reviews</h2>
          {reviews === null ? (
            <p className="text-muted-foreground">The reviews cannot be loaded just now.</p>
          ) : (
            <>
              {rated ? (
                <p className="text-lead">
                  <strong>{reviews.average} out of 5</strong> from {reviews.count} review
                  {reviews.count === 1 ? "" : "s"} by buyers
                </p>
              ) : null}
              {reviews.results.length ? (
                <ul className="m-0 grid-auto list-none p-0 [--min:280px]">
                  {reviews.results.map((review, index) => (
                    <li key={`${review.created}-${index}`}>
                      <Card className="h-full">
                        <CardContent>
                          <p className="flex flex-wrap items-center gap-2">
                            <span aria-hidden="true" className="text-gold">
                              {"★".repeat(review.rating)}
                              <span className="text-border">{"★".repeat(5 - review.rating)}</span>
                            </span>
                            <Badge>{review.rating} out of 5</Badge>
                          </p>
                          {review.text ? <p className="whitespace-pre-line">{review.text}</p> : null}
                          <p className="text-[15px] text-muted-foreground">
                            Verified buyer · {formatDate(review.created)}
                          </p>
                        </CardContent>
                      </Card>
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
            <Link href="/shop/" className="inline-flex min-h-11 items-center gap-2 font-semibold">
              <ArrowLeft aria-hidden="true" className="size-5" />
              All books
            </Link>
          </p>
        </div>
      </section>
    </>
  );
}
