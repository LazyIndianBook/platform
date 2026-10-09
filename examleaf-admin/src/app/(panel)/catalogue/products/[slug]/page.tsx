// /catalogue/products/<slug>/ (or its id, as the audit trail names it): a product by section (GET
// catalogue/products/{slug}/): the approvals waiting about it, its prices with the prior-price rule's effect before
// saving, the page's fields, the courier's data, the tax as the master gives it today and its next change, the stock,
// a bundle's books, pictures, the search engines' words, the EAN-13 barcode and its versions (GET …/history/). Each
// part's form for whoever holds that part's permission; its notes and audit events beside.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { Versions } from "@/components/modules/catalogue/history";
import { PriceForm } from "@/components/modules/catalogue/price-form";
import {
  BundleForm,
  IdentityForm,
  PhysicalForm,
  Pictures,
  SeoForm,
  SetStock,
  TaxForm,
} from "@/components/modules/catalogue/product-forms";
import { rupees, STOCK_TONES } from "@/components/modules/catalogue/shared";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import {
  barcodeHref,
  type CatalogueProduct,
  getCatalogueOptions,
  getCatalogueProduct,
  productHistory,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime, formatNumber } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.productsTitle };

const GOODS = new Set(["sample-papers", "solutions"]);

const rateWords = (rate: CatalogueProduct["tax"]["today"]) =>
  rate
    ? copy.catalogue.rateOn(
        String(Number(rate.rate)),
        labelOf(copy.tax.taxability, rate.taxability),
        formatDate(rate.effective_from),
      )
    : copy.catalogue.noRate;

export default async function ProductPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { slug } = await params;
  if (!/^[-a-zA-Z0-9_]+$/.test(slug)) notFound();
  const query = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf(`/catalogue/products/${slug}/`, query));
  const found = await attempt(getCatalogueProduct(slug, transport), path, "404");
  const back = { href: "/catalogue/products/", label: copy.catalogue.productsTitle };
  if (found instanceof ApiError) {
    return (
      <RecordPage title={slug} back={back}>
        <Problem error={found} />
      </RecordPage>
    );
  }
  const can = (permission: string) => has(manifest, permission);
  const editing = can(P.productsChange) || can(P.productTaxChange);
  const [options, history] = await Promise.all([
    editing ? attempt(getCatalogueOptions(transport), path) : null,
    attempt(productHistory(found.slug, param(query, "history"), transport), path),
  ]);
  const ready = options && !(options instanceof ApiError) ? options : null;
  const prices = found.prices;
  const stock = found.stock_info;
  return (
    <RecordPage
      eyebrow={labelOf(copy.catalogue.kinds, found.kind)}
      title={found.title}
      lead={<span className="font-mono">{found.slug}</span>}
      back={back}
      status={
        <span className="inline-flex flex-wrap gap-1.5">
          <StatusChip tone={found.is_active ? "good" : "stopped"}>
            {found.is_active ? copy.catalogue.onSale : copy.catalogue.offSale}
          </StatusChip>
          {found.tax.problem ? <StatusChip tone="bad">{copy.catalogue.chips.tax}</StatusChip> : null}
          {found.courier_problem ? <StatusChip tone="waiting">{copy.catalogue.chips.courier}</StatusChip> : null}
        </span>
      }
      actions={
        <a
          href={found.web_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-h-11 items-center font-semibold"
        >
          {copy.catalogue.onWebsite} <span className="sr-only">{copy.common.opensElsewhere}</span>
        </a>
      }
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "shop.product", target_id: String(found.id) },
        note: { type: "shop.product", id: String(found.id) },
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
      {options instanceof ApiError ? <Problem error={options} /> : null}

      <Section id="prices" title={copy.catalogue.sections.prices} lead={copy.catalogue.pricesLead}>
        <Facts
          items={[
            { label: copy.catalogue.fields.mrp, value: rupees(prices.mrp) },
            { label: copy.catalogue.fields.price, value: rupees(prices.price) },
            { label: copy.catalogue.saving, value: copy.catalogue.savingPercent(prices.saving_percent) },
            {
              label: copy.catalogue.priorPrice,
              value: prices.prior_price
                ? rupees(prices.prior_price)
                : prices.prior_price_applies
                  ? copy.catalogue.noPriorPrice
                  : copy.catalogue.priorRuleFrom(formatDate(prices.prior_price_from)),
            },
          ]}
        />
        {can(P.priceChange) ? <PriceForm product={found} /> : null}
      </Section>

      <Section id="page" title={copy.catalogue.sections.identity}>
        {ready && can(P.productsChange) ? (
          <IdentityForm product={found} options={ready} />
        ) : (
          <Facts
            items={[
              { label: copy.catalogue.fields.subject, value: found.subject?.label ?? copy.common.none },
              { label: copy.catalogue.fields.book, value: found.book?.name ?? copy.common.none },
              { label: copy.catalogue.fields.isbn, value: found.isbn || copy.common.none },
              { label: copy.catalogue.fields.pages, value: formatNumber(found.pages) },
              { label: copy.catalogue.fields.product_type, value: found.product_type?.name ?? copy.common.none },
              {
                label: copy.catalogue.fields.categories,
                value: found.categories.map((shelf) => shelf.name).join(", ") || copy.common.none,
              },
            ]}
          />
        )}
        {found.old_slugs.length ? (
          <p className="m-0 text-sm text-muted-foreground">{copy.catalogue.oldSlugs(found.old_slugs.join(", "))}</p>
        ) : null}
      </Section>

      {found.kind !== "digital" ? (
        <Section id="courier" title={copy.catalogue.sections.physical} lead={copy.catalogue.physicalLead}>
          {found.courier_problem ? (
            <Alert variant="warning" title={copy.catalogue.courierMissing}>
              <p>{found.courier_problem}</p>
            </Alert>
          ) : null}
          {ready && can(P.productsChange) ? (
            <PhysicalForm product={found} options={ready} />
          ) : (
            <Facts
              items={[
                { label: copy.catalogue.fields.weight_grams, value: copy.catalogue.grams(found.weight_grams) },
                {
                  label: copy.catalogue.fields.packaging,
                  value: labelOf(copy.catalogue.packaging, found.packaging || "none"),
                },
                {
                  label: copy.catalogue.dimensions,
                  value:
                    found.length_cm && found.width_cm && found.height_cm
                      ? copy.catalogue.size(found.length_cm, found.width_cm, found.height_cm)
                      : copy.common.none,
                },
              ]}
            />
          )}
        </Section>
      ) : null}

      <Section id="tax" title={copy.catalogue.sections.tax} lead={copy.catalogue.taxLead}>
        {found.tax.problem ? (
          <Alert variant="error" title={copy.catalogue.taxDisagrees}>
            <p>{found.tax.problem}</p>
          </Alert>
        ) : null}
        <Facts
          items={[
            {
              label: copy.catalogue.fields.hsn,
              value: found.hsn ? (
                can(P.taxHsnView) ? (
                  <Link href={`/tax/hsn/${encodeURIComponent(found.hsn)}/`} className="font-mono">
                    {found.hsn}
                  </Link>
                ) : (
                  <span className="font-mono">{found.hsn}</span>
                )
              ) : (
                copy.catalogue.notOnMaster(found.hsn_code)
              ),
            },
            { label: copy.catalogue.rateToday, value: rateWords(found.tax.today) },
            {
              label: copy.catalogue.nextChange,
              value: found.tax.next_change ? rateWords(found.tax.next_change) : copy.catalogue.noChange,
            },
            ...(found.kind === "bundle"
              ? [
                  {
                    label: copy.catalogue.fields.tax_treatment,
                    value: labelOf(copy.catalogue.treatments, found.tax_treatment),
                  },
                ]
              : []),
          ]}
        />
        {ready && can(P.productTaxChange) ? <TaxForm product={found} options={ready} /> : null}
      </Section>

      {found.kind !== "digital" ? (
        <Section
          id="stock"
          title={copy.catalogue.sections.stock}
          lead={found.kind === "bundle" ? copy.catalogue.bundleStockLead : undefined}
        >
          <Facts
            items={[
              {
                label: copy.catalogue.state,
                value: (
                  <StatusChip tone={STOCK_TONES[stock.state] ?? "stopped"}>
                    {labelOf(copy.catalogue.stockStates, stock.state)}
                  </StatusChip>
                ),
              },
              ...(GOODS.has(found.kind)
                ? [{ label: copy.catalogue.fields.stock, value: formatNumber(stock.stock) }]
                : []),
              { label: copy.catalogue.available, value: formatNumber(stock.available) },
              { label: copy.catalogue.columns.reserved, value: formatNumber(stock.reserved) },
              { label: copy.catalogue.columns.awaiting, value: formatNumber(stock.awaiting_payment) },
              { label: copy.catalogue.lowLine, value: formatNumber(stock.low_stock) },
              { label: copy.catalogue.columns.alerts, value: formatNumber(stock.alerts) },
            ]}
          />
          {GOODS.has(found.kind) && can(P.stockSet) ? (
            <div>
              <SetStock product={found} />
            </div>
          ) : null}
        </Section>
      ) : null}

      {found.kind === "bundle" ? (
        <Section id="bundle" title={copy.catalogue.sections.bundle}>
          {found.bundle_items.length ? (
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
              {found.bundle_items.map((item) => (
                <li key={item.product}>
                  <Link href={`/catalogue/products/${encodeURIComponent(item.product)}/`} className="font-semibold">
                    {item.title}
                  </Link>{" "}
                  {copy.catalogue.bundleLine(item.quantity, item.stock)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="m-0 text-muted-foreground">{copy.catalogue.emptyBundle}</p>
          )}
          {can(P.productsChange) ? <BundleForm product={found} /> : null}
        </Section>
      ) : null}

      <Section id="pictures" title={copy.catalogue.sections.pictures} lead={copy.catalogue.picturesLead}>
        {found.cover ? (
          <figure className="m-0 flex max-w-[12rem] flex-col gap-1.5">
            {/* eslint-disable-next-line @next/next/no-img-element -- the API's own file, from the media domain */}
            <img
              src={found.cover.src}
              alt={copy.catalogue.coverOf(found.title)}
              width={found.cover.width ?? undefined}
              height={found.cover.height ?? undefined}
              className="h-auto w-full rounded border border-border"
            />
            <figcaption className="text-sm text-muted-foreground">{copy.catalogue.cover}</figcaption>
          </figure>
        ) : (
          <p className="m-0 text-muted-foreground">{copy.catalogue.noCover}</p>
        )}
        <Pictures
          product={found}
          canAdd={can(P.picturesAdd)}
          canChange={can(P.picturesChange)}
          canRemove={can(P.picturesDelete)}
        />
      </Section>

      <Section id="seo" title={copy.catalogue.sections.seo} lead={copy.catalogue.seoLead}>
        {can(P.productsChange) ? (
          <SeoForm product={found} />
        ) : (
          <Facts
            items={[
              { label: copy.catalogue.fields.seo_title, value: found.seo_title || copy.common.none },
              { label: copy.catalogue.fields.seo_description, value: found.seo_description || copy.common.none },
            ]}
          />
        )}
      </Section>

      {found.barcode ? (
        <Section id="barcode" title={copy.catalogue.sections.barcode} lead={copy.catalogue.barcodeLead}>
          {/* eslint-disable-next-line @next/next/no-img-element -- an SVG the API draws */}
          <img
            src={barcodeHref(found.slug)}
            alt={copy.catalogue.barcodeOf(found.isbn)}
            className="h-auto w-56 bg-white p-2"
          />
          <p className="m-0">
            <a
              href={barcodeHref(found.slug)}
              download={`${found.slug}-ean13.svg`}
              className="inline-flex min-h-11 items-center font-semibold"
            >
              {copy.catalogue.downloadBarcode}
            </a>
          </p>
        </Section>
      ) : null}

      <Section id="history" title={copy.catalogue.sections.history} lead={copy.catalogue.historyLead}>
        {history instanceof ApiError ? (
          <Problem error={history} />
        ) : (
          <Versions
            versions={history.results}
            labels={copy.catalogue.fields}
            older={history.next ? `?history=${encodeURIComponent(history.next)}#history` : null}
          />
        )}
      </Section>
    </RecordPage>
  );
}
