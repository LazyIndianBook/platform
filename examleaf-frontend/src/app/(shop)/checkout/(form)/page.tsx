// /checkout/ (Checkout artboard, Phone checkout; States "Checkout delivery"): the address and delivery steps of the
// checkout (CheckoutForm draws the sheet): signed in, with the address book and the server's cash-on-delivery terms;
// a visitor checks out as a guest (an email address and a typed-in address), except for a course, which opens in an
// account. An empty cart goes back to the cart. While the shop is closed the page says so first (only staff can order
// then: the API's 403 for the others); while a parent's consent is awaited the form is disabled and says why.
// ?pay=cod (the pay page's "Pay cash on delivery instead") starts with cash on delivery chosen.
import "../../shop/shop.css";

import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { CheckoutForm, type LineProduct } from "@/components/shop/checkout-form";
import { ShopClosed } from "@/components/shop/listing";
import { ShopProblem, SignInToBuy } from "@/components/shop/notices";
import { WhileImpersonated } from "@/components/site/impersonation";
import { isDigital } from "@/components/shop/shop";
import { getMe } from "@/lib/api/account";
import { getProducts } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import { getAddresses, getCart, orProblem } from "@/lib/api/shop";
import { getSessionUser } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Checkout",
  description: "Enter your delivery address and choose how to pay for your ExamLeaf order.",
  robots: { index: false, follow: false },
};

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function CheckoutPage({ searchParams }: Props) {
  const user = await getSessionUser();
  const [cart, addresses, config, products, me, params] = await Promise.all([
    orProblem(getCart(), "/checkout/"),
    user ? orProblem(getAddresses(), "/checkout/") : [],
    getConfig(),
    getProducts().catch(() => []),
    user ? getMe().catch(() => null) : null,
    searchParams,
  ]);
  if (cart instanceof ApiError) return <ShopProblem error={cart} retry="/checkout/" what="The checkout" />;
  if (addresses instanceof ApiError) return <ShopProblem error={addresses} retry="/checkout/" what="The checkout" />;
  if (!cart.items.length) redirect("/cart/");
  const bySlug = new Map(products.map((product) => [product.slug, product]));
  const digital = cart.items.every((line) => isDigital(bySlug.get(line.product), bySlug));
  const course = cart.items.some((line) => isDigital(bySlug.get(line.product), bySlug));
  // a course opens in an account: the API refuses a guest's order of one
  if (!user && course) return <SignInToBuy next="/checkout/" />;
  const info: Record<string, LineProduct> = {};
  for (const line of cart.items) {
    const product = bySlug.get(line.product);
    if (product) info[line.product] = { cover: product.cover, subject: product.subject, kind: product.kind };
  }

  return (
    <WhileImpersonated what="Placing an order">
      <CheckoutForm
        cart={cart}
        addresses={addresses}
        email={user?.email ?? ""}
        cod={{ offered: config?.shop.cod ?? false, max: config?.shop.cod_max_value ?? "0" }}
        digital={digital}
        guest={!user}
        info={info}
        consentPending={me?.consent_pending ?? false}
        payOnDelivery={params.pay === "cod"}
        notice={<ShopClosed open={config?.shop.open} />}
      />
    </WhileImpersonated>
  );
}
