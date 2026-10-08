// A collection (Django's CollectionView), on the catalogue's sheet with its own heading (Shop artboard): books picked
// by staff, in their order, with the attribute filters.
import "../../shop.css";

import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ListingPage, readFilters } from "@/components/shop/listing";
import { Unavailable } from "@/components/site/unavailable";
import { getConfig } from "@/lib/api/config";
import { type Collection, getCollections, getListing, type Product } from "@/lib/api/shop";
import { breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

async function find(slug: string): Promise<Collection | null | "unavailable"> {
  try {
    return (await getCollections()).find((item) => item.slug === slug) ?? null;
  } catch {
    return "unavailable";
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const collection = await find(slug);
  if (!collection || collection === "unavailable") return { title: "Shop" };
  return pageMetadata({
    title: `${collection.name}: ExamLeaf shop`,
    path: `/shop/collection/${slug}/`,
    description: `${collection.name}: ExamLeaf books for the Assam Board (ASSEB) Class 12 examination, delivered across India.`,
  });
}

export default async function CollectionPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const path = `/shop/collection/${slug}/`;
  const collection = await find(slug);
  if (collection === null) notFound();
  if (collection === "unavailable") return <Unavailable what="This collection" retry={path} />;
  const filters = readFilters(await searchParams);
  let all: Product[], filtered: Product[] | null;
  try {
    [all, filtered] = await Promise.all([
      getListing({ collection: slug }),
      Object.keys(filters).length ? getListing({ collection: slug, attrs: filters }) : null,
    ]);
  } catch {
    return <Unavailable what="This collection" retry={path} />;
  }
  const config = await getConfig();
  // in the staff's order (the collection's list), not the products list's
  const inOrder = (products: Product[]) =>
    [...products].sort((a, b) => collection.products.indexOf(a.slug) - collection.products.indexOf(b.slug));

  return (
    <>
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Shop", path: "/shop/" },
          { name: collection.name, path },
        ])}
      />
      <ListingPage
        title={collection.name}
        intro={collection.description}
        path={path}
        trail={[{ label: "Shop", href: "/shop/" }, { label: collection.name }]}
        all={all}
        products={inOrder(filtered ?? all)}
        filters={filters}
        open={config?.shop.open}
      />
    </>
  );
}
