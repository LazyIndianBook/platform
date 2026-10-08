// A shelf of the category tree (Django's CategoryView), on the catalogue's sheet with its own heading (Shop artboard):
// its books and those of its sub-shelves, the sub-shelves as chips, and filters by the books' attributes
// (?attr_<code>=, server-rendered).
import "../../shop.css";

import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ListingPage, readFilters } from "@/components/shop/listing";
import { Unavailable } from "@/components/site/unavailable";
import { getConfig, type SiteConfig } from "@/lib/api/config";
import { type Category, getCategories, getListing, type Product } from "@/lib/api/shop";
import { breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

async function shelf(slug: string): Promise<{ category: Category; tree: Category[] } | null | "unavailable"> {
  try {
    const tree = await getCategories();
    const category = tree.find((item) => item.slug === slug);
    return category ? { category, tree } : null;
  } catch {
    return "unavailable";
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const found = await shelf(slug);
  if (!found || found === "unavailable") return { title: "Shop" };
  const { name } = found.category;
  return pageMetadata({
    title: `${name}: ExamLeaf shop`,
    path: `/shop/category/${slug}/`,
    description: `${name}: ExamLeaf books for the Assam Board (ASSEB) Class 12 examination, delivered across India.`,
  });
}

export default async function CategoryPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const path = `/shop/category/${slug}/`;
  const found = await shelf(slug);
  if (found === null) notFound();
  if (found === "unavailable") return <Unavailable what="This shelf" retry={path} />;
  const { category, tree } = found;
  const filters = readFilters(await searchParams);

  const ancestors: Category[] = [];
  for (let parent = category.parent; parent;) {
    const above = tree.find((item) => item.slug === parent);
    if (!above || ancestors.includes(above)) break;
    ancestors.unshift(above);
    parent = above.parent;
  }
  let all: Product[], products: Product[] | null, config: SiteConfig | null;
  try {
    [all, products, config] = await Promise.all([
      getListing({ category: slug }),
      Object.keys(filters).length ? getListing({ category: slug, attrs: filters }) : null,
      getConfig(),
    ]);
  } catch {
    return <Unavailable what="This shelf" retry={path} />;
  }
  const crumbs = [...ancestors, category].map((item) => ({ name: item.name, path: `/shop/category/${item.slug}/` }));

  return (
    <>
      <JsonLd data={breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Shop", path: "/shop/" }, ...crumbs])} />
      <ListingPage
        title={category.name}
        intro={category.description}
        path={path}
        trail={[{ label: "Shop", href: "/shop/" }, ...crumbs.map((crumb) => ({ label: crumb.name, href: crumb.path }))]}
        shelves={tree
          .filter((item) => item.parent === slug)
          .map((item) => ({ href: `/shop/category/${item.slug}/`, name: item.name }))}
        all={all}
        products={products ?? all}
        filters={filters}
        open={config?.shop.open}
      />
    </>
  );
}
