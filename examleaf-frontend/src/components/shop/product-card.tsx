// A product card (Django's shop/_product_card.html; components.md .card-interactive): the whole card is the one link
// to the product, with its cover (or the drawn no-cover), the kind and subject chips, Out of stock, title and price.
// data-subject feeds the catalogue's subject tabs. The cover morphs into the product page's (Morph, motion.md d).
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
      <CardLink href={`/shop/${product.slug}/`} className="w-full">
        <span className="flex flex-col gap-3 p-4">
          <Morph name={`cover-${product.slug}`}>
            <ProductCover product={product} />
          </Morph>
          <span className="flex flex-wrap gap-2">
            <Badge>{KIND_LABEL[product.kind]}</Badge>
            {subject ? <Badge variant={subject.key}>{subject.name}</Badge> : null}
            {product.in_stock ? null : <Badge variant="hard">Out of stock</Badge>}
          </span>
          <span className="font-head text-card-title leading-tight font-bold text-heading">{product.title}</span>
          <Price as="span" price={product.price} mrp={product.mrp} />
        </span>
      </CardLink>
    </li>
  );
}

export function ProductGrid({ products, label }: { products: Product[]; label: string }) {
  return (
    <ul aria-label={label} className="m-0 grid-auto list-none p-0 [--min:220px]">
      {products.map((product) => (
        <ProductCard key={product.slug} product={product} />
      ))}
    </ul>
  );
}
