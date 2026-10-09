// /catalogue/shipping-rates/<id>/: a delivery rate (GET catalogue/shipping-rates/{id}/), changed behind the save bar
// with the reason its history keeps (PATCH, for whoever may change rates), and its versions (GET …/history/).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { Versions } from "@/components/modules/catalogue/history";
import { RateForm } from "@/components/modules/catalogue/rates";
import { rupees, statesOf } from "@/components/modules/catalogue/shared";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getCatalogueOptions, getShippingRate, rateHistory } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.ratesTitle };

export default async function RatePage({ params }: { params: Promise<{ id: string }> }) {
  const id = recordId((await params).id);
  const { manifest, transport, path } = await staffPage(`/catalogue/shipping-rates/${id}/`);
  const found = await attempt(getShippingRate(id, transport), path, "404");
  const back = { href: "/catalogue/shipping-rates/", label: copy.catalogue.ratesTitle };
  if (found instanceof ApiError) {
    return (
      <RecordPage title={String(id)} back={back}>
        <Problem error={found} />
      </RecordPage>
    );
  }
  const [options, history] = await Promise.all([
    attempt(getCatalogueOptions(transport), path),
    attempt(rateHistory(found.id, transport), path),
  ]);
  const states = options instanceof ApiError ? [] : options.states;
  const name = (code: string) => states.find((state) => state.value === code)?.label ?? code;
  return (
    <RecordPage
      eyebrow={copy.catalogue.rate}
      title={found.name}
      back={back}
      status={
        found.is_active ? (
          <StatusChip tone="good">{copy.states.active}</StatusChip>
        ) : (
          <StatusChip tone="stopped">{copy.states.inactive}</StatusChip>
        )
      }
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "shop.shippingrate", target_id: String(found.id) },
        note: { type: "shop.shippingrate", id: String(found.id) },
      })}
    >
      <Facts
        items={[
          {
            label: copy.catalogue.columns.states,
            value: statesOf(found).map(name).join(", ") || copy.catalogue.everyOtherState,
          },
          { label: copy.catalogue.columns.fee, value: rupees(found.fee) },
          {
            label: copy.catalogue.columns.freeAbove,
            value: found.free_above === null ? copy.catalogue.neverFree : rupees(found.free_above),
          },
        ]}
      />
      {has(manifest, P.ratesChange) && !(options instanceof ApiError) ? (
        <Section id="change" title={copy.catalogue.changeRate}>
          <RateForm rate={found} states={states} />
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
