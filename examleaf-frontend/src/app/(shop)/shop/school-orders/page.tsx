// /shop/school-orders/ (School orders artboard, Phone lookup and school): on the sheet with "×N" in the margin, what a
// school gets beside the quote form (QuoteForm: the buyer's details and the copies of each book in a grid by subject
// and kind). Printed books on sale only: courses, and bundles holding one, are left out (the API's rule).
import "../shop.css";

import { QuoteForm, type QuoteBook } from "@/components/shop/quote-form";
import { isDigital } from "@/components/shop/shop";
import { Unavailable } from "@/components/site/unavailable";
import { Sheet } from "@/components/ui/band";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { getProducts } from "@/lib/api/catalogue";
import { breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "School and bulk orders",
  path: "/shop/school-orders/",
  description:
    "Schools, coaching centres and booksellers: ask for a quotation for ExamLeaf books in bulk, delivered anywhere in India.",
});

const POINTS = [
  "Every student gets the free QR solutions",
  "Delivered to the school",
  "A quotation by email, valid for 15 days; the books follow payment, with a GST invoice",
];

export default async function SchoolOrdersPage() {
  let books: QuoteBook[];
  try {
    const products = await getProducts();
    const bySlug = new Map(products.map((product) => [product.slug, product]));
    books = products
      .filter(
        (product) =>
          product.kind !== "digital" &&
          !product.bundle_items.some((item) => isDigital(bySlug.get(item.product), bySlug)),
      )
      .map((product) => ({ slug: product.slug, title: product.title, subject: product.subject, kind: product.kind }));
  } catch {
    return <Unavailable what="The school order form" retry="/shop/school-orders/" />;
  }
  return (
    <Sheet margin="×N" className="shop-page" bodyClassName="nav:pt-[52px] nav:pb-[72px]">
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Shop", path: "/shop/" },
          { name: "School and bulk orders", path: "/shop/school-orders/" },
        ])}
      />
      <Breadcrumb trail={[{ label: "Shop", href: "/shop/" }, { label: "School and bulk orders" }]} />
      <div className="grid gap-x-14 gap-y-6 nav:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div className="flex flex-col gap-[18px] [&>*]:m-0">
          <h1 className="text-[32px] leading-none nav:text-[56px] nav:leading-[1.02]">Books for your school</h1>
          <p className="text-[17px] leading-[1.65] text-ink/85 nav:text-lg">
            Tell us how many copies of each book your school needs. We reply with a quote and a GST invoice for the
            school.
          </p>
          <ul className="m-0 hidden list-none border-t-[1.5px] border-foreground p-0 nav:block">
            {POINTS.map((point) => (
              <li key={point} className="border-b border-border py-3">
                {point}
              </li>
            ))}
          </ul>
        </div>
        <QuoteForm books={books} />
      </div>
    </Sheet>
  );
}
