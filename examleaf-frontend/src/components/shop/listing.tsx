// What the catalogue, a shelf (category) and a collection share (Django's shop/catalogue.html): the trust row, the
// shop-closed alert, links as chips (shelves, collections, sub-shelves), and the attribute filters: links that set
// ?attr_<code>=<value> (the API's own filter, server-rendered, no script), the current value marked.
import { cn } from "cn";
import { Lock, Package, Truck } from "lucide-react";
import Link from "next/link";

import { MarkdownBlock } from "@/components/solutions/markdown";
import { Alert } from "@/components/ui/alert";
import { badgeVariants } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import type { Product } from "@/lib/api/shop";

import { ProductGrid } from "./product-card";

const chip = (current = false) =>
  cn(
    badgeVariants({ variant: "muted" }),
    "h-auto min-h-11 px-4 text-[15px] hover:underline",
    current && "bg-primary text-primary-foreground",
  );

const TRUST = [
  { Icon: Truck, text: "Delivered anywhere in India" },
  { Icon: Lock, text: "Secure payment through Razorpay" },
  { Icon: Package, text: "Cancel until it is packed" },
];

export function TrustRow() {
  return (
    <ul className="m-0 flex list-none flex-wrap gap-x-6 gap-y-2 p-0 text-[15px] font-semibold text-muted-foreground">
      {TRUST.map(({ Icon, text }) => (
        <li key={text} className="inline-flex items-center gap-2">
          <Icon aria-hidden="true" className="size-5 shrink-0 text-accent" />
          {text}
        </li>
      ))}
    </ul>
  );
}

export function ShopClosed({ open }: { open: boolean | undefined }) {
  if (open !== false) return null;
  return (
    <Alert title="Shop opens soon">
      <p>The books and their prices are here; orders open in a few days.</p>
    </Alert>
  );
}

export function ChipNav({ label, links }: { label: string; links: { href: string; name: string }[] }) {
  if (!links.length) return null;
  return (
    <nav aria-label={label} className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="font-semibold">{label}</span>
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
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
      <h2 className="m-0 text-[17px] leading-snug">Filter</h2>
      {options.map((option) => (
        <nav key={option.code} aria-label={option.name} className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="min-w-24 font-semibold">{option.name}</span>
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

/** A shelf's or a collection's page: breadcrumb, heading and intro, sub-shelves, filters, then the books. */
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
    <section className="pt-7 pb-(--section)">
      <div className="container-site flex flex-col gap-5">
        <div className="flex max-w-[46rem] flex-col gap-4 [&>*]:m-0">
          <Breadcrumb trail={trail} className="-mb-4" />
          <h1>{title}</h1>
          {intro ? (
            <div className="prose text-lead text-muted-foreground">
              <MarkdownBlock>{intro}</MarkdownBlock>
            </div>
          ) : null}
          <TrustRow />
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
      </div>
    </section>
  );
}
