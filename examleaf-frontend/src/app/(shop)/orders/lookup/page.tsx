// /orders/lookup/ (Django's shop/lookup.html): a guest asks for the link to their order again (LookupForm). Signed
// in, the orders are in My orders.
import type { Metadata } from "next";
import Link from "next/link";

import { LookupForm } from "@/components/shop/lookup-form";
import { getSessionUser } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Find your order",
  description: "Find an ExamLeaf order placed without an account: type its number and the email address used.",
  alternates: { canonical: "/orders/lookup/" },
  robots: { index: false, follow: true },
};

export default async function LookupPage() {
  const user = await getSessionUser();
  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site flex max-w-[calc(38rem+2*var(--gutter))] flex-col gap-4 [&>h1]:m-0 [&>p]:m-0">
        <h1>Find your order</h1>
        <p>
          Ordered without an account? Every email about your order has a link to it. Lost them? Type the order number
          and the email address you used: we email the link to that address.
        </p>
        <LookupForm />
        {user ? (
          <p>
            Orders placed while logged in are in <Link href="/account/orders/">My orders</Link>.
          </p>
        ) : null}
      </div>
    </section>
  );
}
