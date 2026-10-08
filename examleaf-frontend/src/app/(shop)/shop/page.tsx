// The catalogue (Shop artboard, Phone shop): "The shop" on the sheet ("₹" in the margin, the count of books shown in
// the marks), the school-orders link, the shop-closed notice, the subject tabs and the kind chips (?subject=, ?kind=:
// links the server answers, so they work without script and can be shared; G13: ?kind= has its control), shelves and
// collections, then a card per product: Sample Papers, Solutions, then bundles, as the artboard orders them. A filter
// that matches nothing says so, with the way back to every book.
import "./shop.css";

import { cn } from "cn";
import Link from "next/link";

import { CatalogueSheet, ChipNav, chip, ShopClosed } from "@/components/shop/listing";
import { ProductGrid } from "@/components/shop/product-card";
import { Unavailable } from "@/components/site/unavailable";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { getProducts } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { getCategories, getCollections, type Product } from "@/lib/api/shop";
import { breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";
import { SUBJECTS } from "@/lib/site";

export const metadata = pageMetadata({
  title: "Shop: printed books",
  path: "/shop/",
  description:
    "Buy ExamLeaf Sample Papers and Solutions books for the Assam Board (ASSEB) Class 12 examination, delivered across India.",
});

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

const KINDS: { kind: Product["kind"]; label: string }[] = [
  { kind: "sample-papers", label: "Sample Papers" },
  { kind: "solutions", label: "Solutions" },
  { kind: "bundle", label: "Bundles" },
  { kind: "digital", label: "Revision course" },
];
const ORDER = KINDS.map((item) => item.kind);

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

function href(subject: string | null, kind: string | null) {
  const query = new URLSearchParams();
  if (subject) query.set("subject", subject);
  if (kind) query.set("kind", kind);
  const text = query.toString();
  return text ? `/shop/?${text}` : "/shop/";
}

export default async function ShopPage({ searchParams }: Props) {
  let products: Product[];
  try {
    products = await getProducts();
  } catch {
    return <Unavailable what="The shop" retry="/shop/" />;
  }
  const [config, categories, collections, params] = await Promise.all([
    getConfig(),
    getCategories().catch(() => []),
    getCollections().catch(() => []),
    searchParams,
  ]);
  const subjects = Object.entries(SUBJECTS).filter(([code]) => products.some((product) => product.subject === code));
  const kinds = KINDS.filter(({ kind }) => products.some((product) => product.kind === kind));
  // only what the catalogue has: an unknown value is no filter at all
  const subject = subjects.some(([code]) => code === first(params.subject)) ? first(params.subject)! : null;
  const kind = kinds.some((item) => item.kind === first(params.kind)) ? first(params.kind)! : null;
  // four Sample Papers, then four Solutions, then the bundles (the artboard's order), each kind in the API's order
  const shown = products
    .filter((product) => (!subject || product.subject === subject) && (!kind || product.kind === kind))
    .sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));
  const subjectName = subject ? SUBJECTS[subject].name : null;
  const kindName = kinds.find((item) => item.kind === kind)?.label ?? null;

  return (
    <CatalogueSheet count={shown.length}>
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Shop", path: "/shop/" },
        ])}
      />
      <div className="flex flex-col gap-3 nav:flex-row nav:items-end nav:justify-between nav:gap-6">
        <div className="flex flex-col gap-2.5 [&>*]:m-0">
          <h1 className="text-[38px] leading-none nav:text-[60px]">The shop</h1>
          <p className="hidden text-lg text-ink/85 nav:block">
            Printed books for ASSEB Class 12, delivered anywhere in India.
          </p>
        </div>
        <Link href="/shop/school-orders/" className="text-[15px] font-bold nav:text-base">
          Ordering for a school? Get a quote →
        </Link>
      </div>
      <ShopClosed open={config?.shop.open} />

      {products.length ? (
        <div className="flex flex-col gap-3 border-b border-border pb-3.5 nav:flex-row nav:items-center nav:justify-between nav:gap-6 nav:pb-0">
          {subjects.length > 1 ? (
            <nav aria-label="Subject" className="-m-1 flex gap-2 overflow-x-auto p-1 nav:gap-0">
              {[[null, "All"] as const, ...subjects.map(([code, item]) => [code, item.name] as const)].map(
                ([code, name]) => {
                  const current = code === subject;
                  return (
                    <Link
                      key={name}
                      href={href(code, kind)}
                      aria-current={current ? "page" : undefined}
                      scroll={false}
                      className={cn(
                        "inline-flex min-h-11 shrink-0 items-center border border-input px-3 text-sm leading-tight font-semibold whitespace-nowrap text-foreground no-underline hover:text-foreground",
                        "nav:border-0 nav:px-4 nav:text-base nav:text-muted-foreground nav:first:pl-0 nav:hover:text-foreground",
                        current &&
                          "border-foreground bg-foreground text-background hover:text-background nav:bg-transparent nav:text-foreground nav:shadow-[inset_0_-2px_0_var(--red-ink)]",
                      )}
                    >
                      {name}
                    </Link>
                  );
                },
              )}
            </nav>
          ) : null}
          {kinds.length > 1 ? (
            <nav aria-label="Kind of book" className="-m-1 flex gap-2 overflow-x-auto p-1 nav:pb-1.5">
              {[{ kind: null, label: "Every book" }, ...kinds].map((item) => (
                <Link
                  key={item.label}
                  href={href(subject, item.kind)}
                  aria-current={item.kind === kind ? "page" : undefined}
                  scroll={false}
                  className={chip(item.kind === kind)}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          ) : null}
        </div>
      ) : null}

      <ChipNav
        label="Shelves"
        links={categories
          .filter((category) => category.depth === 1)
          .map((category) => ({ href: `/shop/category/${category.slug}/`, name: category.name }))}
      />
      <ChipNav
        label="Collections"
        links={collections.map((collection) => ({
          href: `/shop/collection/${collection.slug}/`,
          name: collection.name,
        }))}
      />

      {shown.length ? (
        <ProductGrid
          products={shown}
          label={[kindName ?? "Books", subjectName ? `for ${subjectName}` : ""].filter(Boolean).join(" ")}
        />
      ) : products.length ? (
        <EmptyState
          art="results"
          title="No books match these filters"
          action={
            <Link href="/shop/" className={buttonVariants({ variant: "primary" })}>
              See every book
            </Link>
          }
        >
          <p>
            There {kindName ? `are no ${kindName}` : "is nothing"}
            {subjectName ? ` for ${subjectName}` : ""} in the shop yet.
          </p>
        </EmptyState>
      ) : (
        <EmptyState art="results" title="No books here yet">
          <p>The books are being prepared. Please come back soon.</p>
        </EmptyState>
      )}

      <p className="m-0 text-[15px] text-muted-foreground">
        Ordered without an account? <Link href="/orders/lookup/">Find your order</Link>.
      </p>
    </CatalogueSheet>
  );
}
