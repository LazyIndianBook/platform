// /catalogue/coupons/new/: a new coupon (POST catalogue/coupons/, through coupon.create: beyond your discount limit it
// waits for FINANCE), the shelves from GET catalogue/options/; for whoever may make one.
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { CouponForm } from "@/components/modules/catalogue/terms";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getCatalogueOptions } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.newCoupon };

export default async function NewCouponPage() {
  const { manifest, transport, path } = await staffPage("/catalogue/coupons/new/");
  if (!has(manifest, P.couponsAdd)) redirect("/catalogue/coupons/");
  const options = await attempt(getCatalogueOptions(transport), path);
  return (
    <>
      <PageHeader
        title={copy.catalogue.newCoupon}
        lead={copy.catalogue.newCouponLead}
        back={{ href: "/catalogue/coupons/", label: copy.catalogue.couponsTitle }}
      />
      {options instanceof ApiError ? <Problem error={options} /> : <CouponForm coupon={null} options={options} />}
    </>
  );
}
