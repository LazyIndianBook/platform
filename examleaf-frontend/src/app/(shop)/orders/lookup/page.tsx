// /orders/lookup/ (Order lookup artboard, Phone lookup and school): on the sheet with "?" in the margin, a guest asks
// for the link to their order again (LookupForm: the same answer whether an order matched or not). Signed in, the
// orders are in My orders.
import "@/app/(shop)/shop/shop.css";

import type { Metadata } from "next";
import Link from "next/link";

import { LookupForm } from "@/components/shop/lookup-form";
import { Sheet } from "@/components/ui/band";
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
    <Sheet margin="?" className="shop-page" bodyClassName="nav:pt-11 nav:pb-16">
      <div className="flex max-w-[34rem] flex-col gap-4 [&>*]:m-0">
        <h1 className="text-[32px] leading-none nav:text-[44px] nav:leading-[1.05]">Find your order</h1>
        <p className="text-base leading-relaxed text-ink/85">
          No account needed. Use the number from your confirmation email.
        </p>
        <LookupForm />
        {user ? (
          <p className="text-[15px]">
            Orders placed while logged in are in <Link href="/account/orders/">My orders</Link>.
          </p>
        ) : null}
      </div>
    </Sheet>
  );
}
