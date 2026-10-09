// /orders/new/: a staff order (POST orders/, shop.add_order): the books, the customer, the discount and what it all
// comes to (POST orders/preview/) with the approval rule's answer before saving; a 202 says a second person approves
// it first and nothing exists until then.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { StaffOrderForm } from "@/components/modules/orders/staff-order-form";
import { PageHeader } from "@/components/shell/page-header";
import { staffPage } from "@/lib/api/page";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.orders.create.title };

export default async function NewOrderPage() {
  const { manifest } = await staffPage("/orders/new/");
  if (!has(manifest, P.ordersAdd)) notFound();
  return (
    <>
      <PageHeader
        title={copy.orders.create.title}
        lead={copy.orders.create.lead}
        back={{ href: "/orders/", label: copy.orders.title }}
      />
      <StaffOrderForm />
    </>
  );
}
