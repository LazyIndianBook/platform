// The catalogue (Catalogue artboard; Django's shop/catalogue.html): heading and trust row, the shop-closed alert,
// shelves and collections, the subject tabs (radios, CSS only: shop.css), the featured bundle with its books' covers
// fanned, a card per book, then the lines for guests and schools.
import "./shop.css";

import Link from "next/link";

import { AddToCart } from "@/components/shop/product-actions";
import { ChipNav, ShopClosed, TrustRow } from "@/components/shop/listing";
import { ProductCover, ProductGrid } from "@/components/shop/product-card";
import { isDigital, KIND_LABEL } from "@/components/shop/shop";
import { Unavailable } from "@/components/site/unavailable";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Price } from "@/components/ui/price";
import { Tabs } from "@/components/ui/tabs";
import { getProducts } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { getCategories, getCollections, type Product } from "@/lib/api/shop";
import { breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";
import { SUBJECTS, subjectOf } from "@/lib/site";

export const metadata = pageMetadata({
  title: "Shop: printed books",
  path: "/shop/",
  description:
    "Buy ExamLeaf Sample Papers and Solutions books for the Assam Board (ASSEB) Class 12 examination, delivered across India.",
});

const KINDS: Product["kind"][] = ["sample-papers", "solutions", "digital"];

function Featured({ bundle, bySlug, open }: { bundle: Product; bySlug: Map<string, Product>; open: boolean }) {
  const subject = subjectOf(bundle.subject);
  const items = bundle.bundle_items
    .map((item) => bySlug.get(item.product))
    .filter((item): item is Product => Boolean(item));
  const covers = items.length ? items.slice(0, 2) : [bundle];
  const saving = Number(bundle.mrp) > Number(bundle.price);
  return (
    <div
      data-subject={bundle.subject ?? undefined}
      className="mb-8 flex flex-wrap items-center gap-x-10 gap-y-6 rounded-lg border border-border bg-card p-6 shadow-card"
    >
      <div aria-hidden="true" className="flex w-[240px] max-w-full items-end">
        {covers.map((product, index) => (
          <div
            key={product.slug}
            className={index ? "-ml-12 w-[150px] translate-y-2 rotate-3" : "relative z-10 w-[150px] -rotate-3"}
          >
            <ProductCover product={product} sizes="150px" priority={index === 0} />
          </div>
        ))}
      </div>
      <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-3 [&>*]:m-0">
        <p className="flex flex-wrap gap-2">
          {saving ? <Badge variant="gold">Best value</Badge> : null}
          <Badge>{KIND_LABEL.bundle}</Badge>
          {subject ? <Badge variant={subject.key}>{subject.name}</Badge> : null}
        </p>
        <h2>{bundle.title}</h2>
        {items.length ? (
          <p className="text-muted-foreground">
            {subject ? `Both ${subject.name} books together: ` : "Together: "}
            {items.map((item) => KIND_LABEL[item.kind]).join(" and ")}.
          </p>
        ) : null}
        <Price price={bundle.price} mrp={bundle.mrp} size="offer" />
        <div className="flex flex-wrap items-start gap-3">
          {open && bundle.in_stock ? (
            <AddToCart
              compact
              options={[
                {
                  slug: bundle.slug,
                  title: bundle.title,
                  label: bundle.title,
                  price: bundle.price,
                  mrp: bundle.mrp,
                  inStock: bundle.in_stock,
                  digital: isDigital(bundle, bySlug),
                },
              ]}
            />
          ) : null}
          <Link href={`/shop/${bundle.slug}/`} className={buttonVariants({ variant: "secondary", size: "lg" })}>
            See the bundle
          </Link>
        </div>
      </div>
    </div>
  );
}

export default async function ShopPage() {
  let products: Product[];
  try {
    products = await getProducts();
  } catch {
    return <Unavailable what="The shop" retry="/shop/" />;
  }
  const [config, categories, collections] = await Promise.all([
    getConfig(),
    getCategories().catch(() => []),
    getCollections().catch(() => []),
  ]);
  const bySlug = new Map(products.map((product) => [product.slug, product]));
  const bundles = products.filter((product) => product.kind === "bundle");
  // four Sample Papers, then four Solutions (the artboard's order), each kind in the API's order
  const books = products
    .filter((product) => product.kind !== "bundle")
    .sort((a, b) => KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind));
  const subjects = Object.entries(SUBJECTS).filter(([code]) => products.some((product) => product.subject === code));
  const open = config?.shop.open ?? false;

  return (
    <section className="shop-catalogue pt-7 pb-(--section)">
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Shop", path: "/shop/" },
        ])}
      />
      <div className="container-site flex flex-col gap-5">
        <div className="flex max-w-[46rem] flex-col gap-4 [&>*]:m-0">
          <p className="text-[15px] font-semibold text-muted-foreground">Shop · ASSEB Class 12</p>
          <h1>Buy the books</h1>
          <p className="text-lead text-muted-foreground">
            Printed Sample Papers and Solutions books, delivered anywhere in India. Pay online with UPI, a card or net
            banking.
          </p>
          <TrustRow />
        </div>
        <ShopClosed open={config?.shop.open} />
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

        {products.length ? (
          <div className="mt-2">
            {subjects.length > 1 ? (
              <Tabs
                name="subject"
                legend="Subject"
                className="mb-6"
                options={[
                  { value: "all", label: "All subjects" },
                  ...subjects.map(([code, subject]) => ({ value: code, label: subject.name })),
                ]}
              />
            ) : null}
            {bundles.map((bundle) => (
              <Featured key={bundle.slug} bundle={bundle} bySlug={bySlug} open={open} />
            ))}
            <ProductGrid products={books} label="Books" />
          </div>
        ) : (
          <EmptyState art="results" title="No books here yet">
            <p>The books are being prepared. Please come back soon.</p>
          </EmptyState>
        )}

        <p className="m-0 mt-4 text-muted-foreground">
          Ordered without an account? <Link href="/orders/lookup/">Find your order</Link>. For a school or a bookshop:{" "}
          <Link href="/shop/school-orders/">school and bulk orders</Link>.
        </p>
      </div>
    </section>
  );
}
