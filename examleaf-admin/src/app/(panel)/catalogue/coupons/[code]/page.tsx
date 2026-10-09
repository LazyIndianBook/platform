// /catalogue/coupons/<code>/ (or its id): a coupon (GET catalogue/coupons/{code}/): its terms, what it applies to, its
// uses and the changes waiting for approval; a change behind the save bar (coupon.change), a single-use coupon's codes
// (GET …/codes/?used=&cursor=) and a school's batch made by a job; its versions (GET …/history/).
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { CodesTable, MakeCodes } from "@/components/modules/catalogue/codes";
import { Versions } from "@/components/modules/catalogue/history";
import { discountText, rupees, TERM_TONES } from "@/components/modules/catalogue/shared";
import { CouponForm } from "@/components/modules/catalogue/terms";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { couponHistory, getCatalogueOptions, getCoupon, listCouponCodes } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, formatNumber } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.couponsTitle };

const list = (items: readonly string[]) => items.join(", ") || copy.common.none;

export default async function CouponPage({
  params,
  searchParams,
}: {
  params: Promise<{ code: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { code } = await params;
  if (!/^[-a-zA-Z0-9]+$/.test(code)) notFound();
  const query = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf(`/catalogue/coupons/${code}/`, query));
  const found = await attempt(getCoupon(code, transport), path, "404");
  const back = { href: "/catalogue/coupons/", label: copy.catalogue.couponsTitle };
  if (found instanceof ApiError) {
    return (
      <RecordPage title={code} back={back}>
        <Problem error={found} />
      </RecordPage>
    );
  }
  const can = (permission: string) => has(manifest, permission);
  const codes = found.single_use && can(P.codesView);
  const [options, codePage, history] = await Promise.all([
    can(P.couponsChange) ? attempt(getCatalogueOptions(transport), path) : null,
    codes
      ? attempt(
          listCouponCodes(found.code, { used: param(query, "used"), cursor: param(query, "cursor") }, transport),
          path,
        )
      : null,
    attempt(couponHistory(found.code, transport), path),
  ]);
  return (
    <RecordPage
      eyebrow={copy.catalogue.coupon}
      title={<span className="font-mono">{found.code}</span>}
      lead={found.description || undefined}
      back={back}
      status={
        <StatusChip tone={TERM_TONES[found.state] ?? "stopped"}>
          {labelOf(copy.catalogue.termStates, found.state)}
        </StatusChip>
      }
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "shop.coupon", target_id: String(found.id) },
        note: { type: "shop.coupon", id: String(found.id) },
      })}
    >
      {found.waiting.length ? (
        <Alert variant="info" title={copy.catalogue.waitingTitle}>
          <ul className="m-0 pl-5">
            {found.waiting.map((change) => (
              <li key={change.id}>
                <Link href={`/approvals/${change.id}/`} className="font-semibold">
                  {copy.catalogue.waitingChange(change.id, formatDateTime(change.created))}
                </Link>{" "}
                {change.rule}
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}
      <Facts
        items={[
          { label: copy.catalogue.columns.discount, value: discountText(found.kind, found.value) },
          { label: copy.catalogue.fields.min_order, value: rupees(found.min_order) },
          { label: copy.catalogue.fields.valid_from, value: formatDateTime(found.valid_from) },
          {
            label: copy.catalogue.fields.valid_until,
            value: found.valid_until ? formatDateTime(found.valid_until) : copy.catalogue.noEnd,
          },
          { label: copy.catalogue.columns.uses, value: formatNumber(found.uses) },
          {
            label: copy.catalogue.fields.max_uses,
            value: found.max_uses === null ? copy.catalogue.noLimit : formatNumber(found.max_uses),
          },
          {
            label: copy.catalogue.fields.max_uses_per_customer,
            value:
              found.max_uses_per_customer === null ? copy.catalogue.noLimit : formatNumber(found.max_uses_per_customer),
          },
          { label: copy.catalogue.fields.include_products, value: list(found.include_products) },
          { label: copy.catalogue.fields.include_categories, value: list(found.include_categories) },
          { label: copy.catalogue.fields.exclude_products, value: list(found.exclude_products) },
          { label: copy.catalogue.fields.exclude_categories, value: list(found.exclude_categories) },
          {
            label: copy.catalogue.rules,
            value: [
              found.first_order_only ? copy.catalogue.firstOrderOnly : null,
              found.stackable ? copy.catalogue.stackable : copy.catalogue.notStackable,
              found.single_use ? copy.catalogue.singleUse : null,
            ]
              .filter(Boolean)
              .join(" "),
          },
          { label: copy.catalogue.fields.note, value: found.note || copy.common.none },
        ]}
      />
      {options ? (
        <Section id="change" title={copy.catalogue.changeCoupon} lead={copy.catalogue.changeTermsLead}>
          {options instanceof ApiError ? <Problem error={options} /> : <CouponForm coupon={found} options={options} />}
        </Section>
      ) : null}
      {codePage ? (
        <Section
          id="codes"
          title={copy.catalogue.codesTitle}
          lead={copy.catalogue.codesLead(found.codes.made, found.codes.used)}
        >
          {codePage instanceof ApiError ? (
            <Problem error={codePage} />
          ) : (
            <CodesTable rows={codePage.results} next={codePage.next} previous={codePage.previous} />
          )}
          {can(P.codesAdd) ? <MakeCodes coupon={found.code} /> : null}
        </Section>
      ) : null}
      <Section id="history" title={copy.catalogue.sections.history}>
        {history instanceof ApiError ? (
          <Problem error={history} />
        ) : (
          <Versions versions={history.results} labels={copy.catalogue.fields} />
        )}
      </Section>
    </RecordPage>
  );
}
