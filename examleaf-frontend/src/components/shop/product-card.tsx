// A product card, Direction A (Shop artboard, Phone shop): the whole card is the one link to the product; the cover,
// or for a book without one the cover drawn in its subject's colour ("cover coming"); OUT OF STOCK on the cover; the
// kind in the mono voice (BUNDLE · BEST VALUE when a bundle saves); the title in serif; the price with the MRP struck
// through when it differs. No lift on hover (the title underlines). data-subject stays on the card; the cover morphs.
import { cn } from "cn";

import { CardLink } from "@/components/ui/card";
import { CoverPicture } from "@/components/ui/cover";
import { Morph } from "@/components/ui/morph";
import type { Product } from "@/lib/api/shop";
import { inrShort } from "@/lib/format";
import { subjectOf } from "@/lib/site";

import { KIND_LABEL } from "./shop";

const CARD_SIZES = "(min-width: 1168px) 230px, (min-width: 900px) 22vw, 45vw";

/** A book without a cover: its subject's colour, the imprint, the subject and the kind (Shop artboard). Below 120 px
 *  (a cart line's thumbnail) only the colour. */
function DrawnCover({ product }: { product: Pick<Product, "subject" | "title" | "kind"> }) {
  const subject = subjectOf(product.subject);
  return (
    <span
      aria-hidden="true"
      className={cn(
        subject && `subject-${subject.key}`,
        "@container block aspect-[480/678] rounded-[3px] bg-(--base,var(--navy)) text-white shadow-cover",
      )}
    >
      <span className="flex h-full flex-col justify-between p-[8cqi] @max-[119px]:hidden">
        <span className="font-mono text-[max(9px,5cqi)] leading-none font-medium tracking-[0.08em] opacity-85">
          EXAMLEAF · ASSEB 12
        </span>
        <span className="font-head text-[12cqi] leading-[1.05] font-semibold">
          {subject ? (
            <>
              {subject.name}
              <br />
              {KIND_LABEL[product.kind]}
            </>
          ) : (
            product.title
          )}
        </span>
        <span className="font-mono text-[max(9px,5cqi)] leading-none font-medium opacity-85">cover coming</span>
      </span>
    </span>
  );
}

export function ProductCover({
  product,
  sizes = CARD_SIZES,
  alt = "",
  priority,
}: {
  product: Pick<Product, "cover" | "subject" | "title" | "kind">;
  sizes?: string;
  alt?: string;
  priority?: boolean;
}) {
  const subject = subjectOf(product.subject);
  if (!product.cover) return <DrawnCover product={product} />;
  return (
    <span className={`cover ${subject ? `subject-${subject.key}` : ""}`}>
      <CoverPicture src={product.cover} alt={alt} sizes={sizes} priority={priority} />
    </span>
  );
}

/** The price in a card's voice: Source Serif, the MRP struck through only when it differs. */
export function CardPrice({ price, mrp, className }: { price: string; mrp?: string; className?: string }) {
  return (
    <span className={cn("flex flex-wrap items-baseline gap-x-2.5 tabular-nums", className)}>
      <strong className="font-head text-[18px] leading-none font-semibold text-foreground nav:text-[22px]">
        {inrShort(price)}
      </strong>
      {mrp && Number(mrp) > Number(price) ? (
        <s className="text-[13px] text-muted-foreground nav:text-[15px]">
          <span className="sr-only">MRP </span>
          {inrShort(mrp)}
        </s>
      ) : null}
    </span>
  );
}

export function ProductCard({ product, priority = false }: { product: Product; priority?: boolean }) {
  const best = product.kind === "bundle" && Number(product.mrp) > Number(product.price);
  return (
    <li data-subject={product.subject ?? undefined} className="flex">
      <CardLink
        href={`/shop/${product.slug}/`}
        className="group w-full border-transparent bg-transparent hover:border-transparent"
      >
        <span className="flex flex-col gap-1.5 nav:gap-2.5">
          <span className="relative block">
            <Morph name={`cover-${product.slug}`}>
              <ProductCover product={product} priority={priority} />
            </Morph>
            {product.in_stock ? null : (
              <span className="absolute top-2.5 left-2.5 border-[1.5px] border-hard bg-background px-[7px] py-[5px] font-mono text-[11px] leading-none font-semibold text-hard uppercase">
                Out of stock
              </span>
            )}
          </span>
          <span className="mt-1 font-mono text-[10px] leading-none font-medium tracking-[0.05em] text-muted-foreground uppercase nav:text-xs">
            {KIND_LABEL[product.kind]}
            {best ? " · Best value" : ""}
          </span>
          <span className="font-head text-[17px] leading-[1.2] font-semibold text-foreground underline-offset-[3px] group-hover:underline nav:text-[21px]">
            {product.title}
          </span>
          <CardPrice price={product.price} mrp={product.mrp} />
        </span>
      </CardLink>
    </li>
  );
}

export function ProductGrid({ products, label }: { products: Product[]; label: string }) {
  return (
    <ul
      aria-label={label}
      className="m-0 grid list-none grid-cols-2 gap-x-3.5 gap-y-5 p-0 nav:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] nav:gap-x-6 nav:gap-y-7"
    >
      {products.map((product, index) => (
        // a phone's first row (two covers) is the catalogue's largest paint: fetched early, the rest lazily
        <ProductCard key={product.slug} product={product} priority={index < 2} />
      ))}
    </ul>
  );
}
