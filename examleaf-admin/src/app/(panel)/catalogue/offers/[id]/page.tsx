// /catalogue/offers/<id>/: an automatic offer (GET catalogue/offers/{id}/): its terms, what it covers, its countdown,
// its uses and the changes waiting for approval; a change behind the save bar (offer.change); its versions (GET
// …/history/, its scope's products, shelves and collections among the changes).
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { Versions } from "@/components/modules/catalogue/history";
import { discountText, rupees, TERM_TONES } from "@/components/modules/catalogue/shared";
import { OfferForm } from "@/components/modules/catalogue/terms";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getCatalogueOptions, getOffer, offerHistory } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, formatNumber } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.offersTitle };

const list = (items: readonly string[]) => items.join(", ") || copy.common.none;

export default async function OfferPage({ params }: { params: Promise<{ id: string }> }) {
  const id = recordId((await params).id);
  const { manifest, transport, path } = await staffPage(`/catalogue/offers/${id}/`);
  const found = await attempt(getOffer(id, transport), path, "404");
  const back = { href: "/catalogue/offers/", label: copy.catalogue.offersTitle };
  if (found instanceof ApiError) {
    return (
      <RecordPage title={String(id)} back={back}>
        <Problem error={found} />
      </RecordPage>
    );
  }
  const [options, history] = await Promise.all([
    has(manifest, P.offersChange) ? attempt(getCatalogueOptions(transport), path) : null,
    attempt(offerHistory(found.id, transport), path),
  ]);
  const covers =
    found.scope === "products"
      ? list(found.products)
      : found.scope === "categories"
        ? list(found.categories)
        : found.scope === "collections"
          ? list(found.collections)
          : labelOf(copy.catalogue.scopes, found.scope);
  return (
    <RecordPage
      eyebrow={copy.catalogue.offer}
      title={found.name}
      lead={found.banner || undefined}
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
        audit: { target_type: "shop.offer", target_id: String(found.id) },
        note: { type: "shop.offer", id: String(found.id) },
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
          { label: copy.catalogue.columns.scope, value: labelOf(copy.catalogue.scopes, found.scope) },
          { label: copy.catalogue.covers, value: covers },
          { label: copy.catalogue.fields.min_quantity, value: formatNumber(found.min_quantity) },
          { label: copy.catalogue.fields.min_value, value: rupees(found.min_value) },
          { label: copy.catalogue.fields.valid_from, value: formatDateTime(found.valid_from) },
          {
            label: copy.catalogue.fields.valid_until,
            value: found.valid_until ? formatDateTime(found.valid_until) : copy.catalogue.noEnd,
          },
          { label: copy.catalogue.columns.uses, value: formatNumber(found.uses) },
          {
            label: copy.catalogue.rules,
            value: [
              found.combinable ? copy.catalogue.combines : copy.catalogue.alone,
              found.show_countdown ? copy.catalogue.countdownShown : null,
            ]
              .filter(Boolean)
              .join(" "),
          },
        ]}
      />
      {options ? (
        <Section id="change" title={copy.catalogue.changeOffer} lead={copy.catalogue.changeTermsLead}>
          {options instanceof ApiError ? <Problem error={options} /> : <OfferForm offer={found} options={options} />}
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
