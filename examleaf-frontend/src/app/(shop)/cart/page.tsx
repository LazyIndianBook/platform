// /cart/ (Cart artboard; Django's shop/cart.html): the account's cart, or a visitor's guest cart (the session's), as
// the API answers it (CartView does the changes). Personal: not indexed, never cached. While the shop is closed it
// says so above the cart (its changes and the checkout are the API's to refuse).
import type { Metadata } from "next";

import { CartView, type LineInfo } from "@/components/shop/cart-view";
import { ShopClosed } from "@/components/shop/listing";
import { ShopProblem } from "@/components/shop/notices";
import { isDigital } from "@/components/shop/shop";
import { getProducts } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import { getCart, orProblem } from "@/lib/api/shop";
import { getSessionUser } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Your cart",
  description: "Your ExamLeaf cart: the books you chose, the copies of each, a coupon code and the way to checkout.",
  robots: { index: false, follow: false },
};

export default async function CartPage() {
  const [user, cart, config] = await Promise.all([getSessionUser(), orProblem(getCart(), "/cart/"), getConfig()]);
  if (cart instanceof ApiError) return <ShopProblem error={cart} retry="/cart/" what="Your cart" />;
  const products = await getProducts().catch(() => []);
  const bySlug = new Map(products.map((product) => [product.slug, product]));
  const info: Record<string, LineInfo> = {};
  for (const line of cart.items) {
    const product = bySlug.get(line.product);
    if (product)
      info[line.product] = {
        cover: product.cover,
        subject: product.subject,
        kind: product.kind,
        digital: isDigital(product, bySlug),
      };
  }

  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site flex flex-col gap-4 [&>h1]:m-0">
        <h1>Your cart</h1>
        <ShopClosed open={config?.shop.open} />
        <CartView initial={cart} info={info} guest={!user} />
      </div>
    </section>
  );
}
