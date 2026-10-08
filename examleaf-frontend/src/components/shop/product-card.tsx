// A product card, Direction A: the whole card is the one link to the product; cover (or the drawn no-cover), the kind
// in the mono voice, the subject and Out of stock as chips, the title in serif, the price. No lift on hover (the
// border turns ink, from CardLink). data-subject feeds the catalogue's subject tabs; the cover still morphs.
import { Badge } from "@/components/ui/badge";
import { CardLink } from "@/components/ui/card";
import { CoverPicture, NoCover } from "@/components/ui/cover";
import { Morph } from "@/components/ui/morph";
import { Price } from "@/components/ui/price";
import type { Product } from "@/lib/api/shop";
import { subjectOf } from "@/lib/site";

import { KIND_LABEL } from "./shop";

const CARD_SIZES = "(min-width: 1168px) 230px, (min-width: 560px) 40vw, 80vw";

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
  if (!product.cover)
    return <NoCover subject={subject?.key} name={subject?.name ?? product.title} kind={KIND_LABEL[product.kind]} />;
  return (
    <span className={`cover ${subject ? `subject-${subject.key}` : ""}`}>
      <CoverPicture src={product.cover} alt={alt} sizes={sizes} priority={priority} />
    </span>
  );
}

export function ProductCard({ product }: { product: Product }) {
  const subject = subjectOf(product.subject);
  return (
    <li data-subject={product.subject ?? undefined} className="flex">
      <CardLink
        href={`/shop/${product.slug}/`}
        className="group w-full border-transparent bg-transparent hover:border-transparent"
      >
        <span className="flex flex-col gap-2.5">
          <Morph name={`cover-${product.slug}`}>
            <ProductCover product={product} />
          </Morph>
          <span className="label-mono text-xs uppercase">{KIND_LABEL[product.kind]}</span>
          <span className="font-head text-[21px] leading-tight font-semibold text-foreground underline-offset-[3px] group-hover:underline">
            {product.title}
          </span>
          <span className="flex flex-wrap gap-2">
            {subject ? <Badge variant={subject.key}>{subject.name}</Badge> : null}
            {product.in_stock ? null : <Badge variant="gold">Out of stock</Badge>}
          </span>
          <Price as="span" price={product.price} mrp={product.mrp} />
        </span>
      </CardLink>
    </li>
  );
}

export function ProductGrid({ products, label }: { products: Product[]; label: string }) {
  return (
    <ul
      aria-label={label}
      className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(min(200px,100%),1fr))] gap-x-6 gap-y-8 p-0"
    >
      {products.map((product) => (
        <ProductCard key={product.slug} product={product} />
      ))}
    </ul>
  );
}
