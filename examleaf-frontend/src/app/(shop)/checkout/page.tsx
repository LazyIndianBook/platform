// /checkout/ (Checkout artboard; Django's shop/checkout.html): the stepper at Address, then the form (CheckoutForm):
// signed in, with the saved addresses and the server's cash-on-delivery terms; a visitor checks out as a guest (an
// email address and a typed-in address), except for a course, which opens in an account. An empty cart goes back to
// the cart. While the shop is closed the page says so first: only staff can order then (the API's 403 for the others).
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { CheckoutForm } from "@/components/shop/checkout-form";
import { ShopClosed } from "@/components/shop/listing";
import { ShopProblem, SignInToBuy } from "@/components/shop/notices";
import { checkoutSteps, isDigital } from "@/components/shop/shop";
import { Stepper } from "@/components/ui/stepper";
import { getProducts } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import { getAddresses, getCart, orProblem } from "@/lib/api/shop";
import { withNext } from "@/lib/auth/next-url";
import { getSessionUser } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Checkout",
  description: "Enter your delivery address and choose how to pay for your ExamLeaf order.",
  robots: { index: false, follow: false },
};

export default async function CheckoutPage() {
  const user = await getSessionUser();
  const [cart, addresses, config, products] = await Promise.all([
    orProblem(getCart(), "/checkout/"),
    user ? orProblem(getAddresses(), "/checkout/") : [],
    getConfig(),
    getProducts().catch(() => []),
  ]);
  if (cart instanceof ApiError) return <ShopProblem error={cart} retry="/checkout/" what="The checkout" />;
  if (addresses instanceof ApiError) return <ShopProblem error={addresses} retry="/checkout/" what="The checkout" />;
  if (!cart.items.length) redirect("/cart/");
  const bySlug = new Map(products.map((product) => [product.slug, product]));
  const digital = cart.items.every((line) => isDigital(bySlug.get(line.product), bySlug));
  const course = cart.items.some((line) => isDigital(bySlug.get(line.product), bySlug));
  // a course opens in an account: the API refuses a guest's order of one
  if (!user && course) return <SignInToBuy next="/checkout/" />;

  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site flex flex-col gap-2">
        <div className="flex flex-col gap-1 [&>*]:m-0">
          <h1>Checkout</h1>
          {user?.email ? (
            <p className="text-muted-foreground">Logged in as {user.email}</p>
          ) : (
            <p className="text-muted-foreground">
              Have an account? <Link href={withNext("/account/login/", "/checkout/")}>Log in</Link> to use your saved
              addresses and see the order in your account. Or go on as a guest.
            </p>
          )}
        </div>
        <Stepper label="Checkout" steps={checkoutSteps()} current={0} />
        <ShopClosed open={config?.shop.open} />
        <CheckoutForm
          cart={cart}
          addresses={addresses}
          email={user?.email ?? ""}
          cod={{ offered: config?.shop.cod ?? false, max: config?.shop.cod_max_value ?? "0" }}
          digital={digital}
          guest={!user}
        />
      </div>
    </section>
  );
}
