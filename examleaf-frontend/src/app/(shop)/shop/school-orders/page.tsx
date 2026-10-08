// /shop/school-orders/ (Django's shop/quote_request.html): schools, coaching centres and bookshops ask for a quotation
// (QuoteForm), for the printed books on sale: courses, and bundles holding one, are left out (the API's rule).
import { QuoteForm } from "@/components/shop/quote-form";
import { isDigital } from "@/components/shop/shop";
import { Unavailable } from "@/components/site/unavailable";
import { getProducts } from "@/lib/api/catalogue";
import { breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";
import { Breadcrumb } from "@/components/ui/breadcrumb";

export const metadata = pageMetadata({
  title: "School and bulk orders",
  path: "/shop/school-orders/",
  description:
    "Schools, coaching centres and booksellers: ask for a quotation for ExamLeaf books in bulk, delivered anywhere in India.",
});

export default async function SchoolOrdersPage() {
  let books;
  try {
    const products = await getProducts();
    const bySlug = new Map(products.map((product) => [product.slug, product]));
    books = products
      .filter(
        (product) =>
          product.kind !== "digital" &&
          !product.bundle_items.some((item) => isDigital(bySlug.get(item.product), bySlug)),
      )
      .map((product) => ({ slug: product.slug, title: product.title }));
  } catch {
    return <Unavailable what="The school order form" retry="/shop/school-orders/" />;
  }
  return (
    <section className="pt-7 pb-(--section)">
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Shop", path: "/shop/" },
          { name: "School and bulk orders", path: "/shop/school-orders/" },
        ])}
      />
      <div className="container-site flex max-w-[calc(52rem+2*var(--gutter))] flex-col gap-4 [&>h1]:m-0 [&>p]:m-0">
        <Breadcrumb
          trail={[{ label: "Shop", href: "/shop/" }, { label: "School and bulk orders" }]}
          className="-mb-4"
        />
        <h1>School and bulk orders</h1>
        <p className="text-lead text-muted-foreground">
          For a school, a coaching centre or a bookshop: tell us which books and how many copies, and we email you a
          quotation, valid for 15 days. Payment is in advance, by NEFT, UPI or a payment link; the books are then
          dispatched with a GST invoice.
        </p>
        <QuoteForm books={books} />
      </div>
    </section>
  );
}
