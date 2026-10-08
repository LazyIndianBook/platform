// What the catalogue, a shelf (category) and a collection share (Shop artboard, Phone shop): the sheet with "₹" in the
// margin and the count of books in the marks, the shop-closed notice (States, "Shop closed and out of stock"), links
// as chips (subjects, kinds, shelves, collections, sub-shelves), and the attribute filters: links that set
// ?attr_<code>=<value> (the API's own filter, server-rendered, no script), the current value marked.
import { cn } from "cn";
import Link from "next/link";

import { MarkdownBlock } from "@/components/solutions/markdown";
import { Alert } from "@/components/ui/alert";
import { Sheet } from "@/components/ui/band";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import type { Product } from "@/lib/api/shop";

import { ProductGrid } from "./product-card";

/** A filter as a chip: a hairline box, the current one in an ink box on white (the kind chips of the Shop artboard). */
export const chip = (current = false) =>
  cn(
    "inline-flex min-h-11 shrink-0 items-center rounded-[3px] border border-border px-3 text-sm leading-tight font-semibold whitespace-nowrap text-foreground no-underline hover:border-foreground hover:text-foreground",
    current && "border-[1.5px] border-foreground bg-card px-[11.5px]",
  );

export function ShopClosed({ open }: { open: boolean | undefined }) {
  if (open !== false) return null;
  return (
    <Alert variant="warning" title="The shop is closed for now">
      <p>
        You can&apos;t place new orders at the moment. Orders you&apos;ve already placed go ahead as normal, and the
        free solutions stay open.
      </p>
    </Alert>
  );
}

export function ChipNav({ label, links }: { label: string; links: { href: string; name: string }[] }) {
  if (!links.length) return null;
  return (
    <nav aria-label={label} className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="label-mono uppercase">{label}</span>
      <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
        {links.map((link) => (
          <li key={link.href}>
            <Link href={link.href} className={chip()}>
              {link.name}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** The catalogue's sheet: "₹" in the margin, the number of books shown in the marks column. */
export function CatalogueSheet({ count, children }: { count: number; children: React.ReactNode }) {
  return (
    <Sheet
      margin="₹"
      marks={`[${count}]`}
      className="shop-page"
      bodyClassName="flex flex-col gap-5 nav:pt-[52px] nav:pb-16"
    >
      {children}
    </Sheet>
  );
}

export type Filters = Record<string, string>;

/** The ?attr_<code>= values of the address (the first of each; empty ones dropped). */
export function readFilters(params: Record<string, string | string[] | undefined>): Filters {
  const filters: Filters = {};
  for (const [name, raw] of Object.entries(params)) {
    const value = Array.isArray(raw) ? raw[0] : raw;
    if (name.startsWith("attr_") && name.length > 5 && value) filters[name.slice(5)] = value;
  }
  return filters;
}

/** Each attribute the products have, with its values in order: what the filters offer. */
export function attributeOptions(products: Product[]) {
  const options = new Map<string, { name: string; values: Set<string> }>();
  for (const attribute of products.flatMap((product) => product.attributes)) {
    const option = options.get(attribute.code) ?? { name: attribute.name, values: new Set<string>() };
    option.values.add(attribute.value);
    options.set(attribute.code, option);
  }
  return [...options].map(([code, { name, values }]) => ({
    code,
    name,
    values: [...values].sort((a, b) => a.localeCompare(b, "en", { numeric: true })),
  }));
}

export function filterHref(path: string, filters: Filters, code: string, value: string | null) {
  const next = new URLSearchParams();
  for (const [name, current] of Object.entries({ ...filters, [code]: value ?? "" })) {
    if (current) next.set(`attr_${name}`, current);
  }
  const query = next.toString();
  return query ? `${path}?${query}` : path;
}

export function AttributeFilters({ path, products, filters }: { path: string; products: Product[]; filters: Filters }) {
  const options = attributeOptions(products).filter((option) => option.values.length > 1 || filters[option.code]);
  if (!options.length) return null;
  return (
    <div className="flex flex-col gap-3 border-y border-border py-3">
      <h2 className="sr-only">Filter</h2>
      {options.map((option) => (
        <nav key={option.code} aria-label={option.name} className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="min-w-24 label-mono uppercase">{option.name}</span>
          <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
            {[null, ...option.values].map((value) => {
              const current = (filters[option.code] ?? null) === value;
              return (
                <li key={value ?? ""}>
                  <Link
                    href={filterHref(path, filters, option.code, value)}
                    aria-current={current ? "true" : undefined}
                    className={chip(current)}
                    scroll={false}
                  >
                    {value ?? "Any"}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      ))}
    </div>
  );
}

/** A shelf's or a collection's page: the catalogue's sheet with its own heading and intro, sub-shelves, filters, then
 *  the books (or what to do when none match). */
export function ListingPage({
  title,
  intro,
  trail,
  path,
  shelves = [],
  all,
  products,
  filters,
  open,
}: {
  title: string;
  intro: string;
  trail: { label: string; href?: string }[];
  path: string;
  shelves?: { href: string; name: string }[];
  all: Product[];
  products: Product[];
  filters: Filters;
  open: boolean | undefined;
}) {
  const filtered = Object.keys(filters).length > 0;
  return (
    <CatalogueSheet count={products.length}>
      <div className="flex max-w-[46rem] flex-col gap-3 [&>*]:m-0">
        <Breadcrumb trail={trail} className="-mb-3" />
        <h1 className="text-[clamp(38px,5vw,60px)] leading-none">{title}</h1>
        {intro ? (
          <div className="text-[18px] leading-relaxed text-ink/85 [&_p]:m-0 [&_p+p]:mt-3">
            <MarkdownBlock>{intro}</MarkdownBlock>
          </div>
        ) : null}
      </div>
      <ShopClosed open={open} />
      <ChipNav label="Shelves" links={shelves} />
      <AttributeFilters path={path} products={all} filters={filters} />
      {products.length ? (
        <ProductGrid products={products} label={title} />
      ) : (
        <EmptyState
          art="results"
          title={filtered ? "No books match these filters" : "No books here yet"}
          action={
            <Link href={filtered ? path : "/shop/"} className={buttonVariants({ variant: "primary" })}>
              {filtered ? "Clear the filters" : "All books"}
            </Link>
          }
        >
          <p>
            {filtered
              ? "Choose Any for one of them to see more."
              : "The books are being prepared. Please come back soon."}
          </p>
        </EmptyState>
      )}
    </CatalogueSheet>
  );
}
