// The legal and policy pages (/privacy/ /terms/ /refunds/ /shipping/ /contact/) from GET /api/v1/pages/<slug>/: the
// website's HTML of the Markdown (raw HTML is off on the server; a [placeholder] still to fill in comes marked
// <mark class="placeholder">), the version and the date of the last change.
// Direction A (ExamLeaf A - Public.dc.html, "Legal" and "Contact"; Phone legal, Phone contact; Gaps, "Shipping
// rates"): a Sheet, the copy in the reading serif with "§" in the margin at each section; "On this page" lists the
// page's sections (a rail from 1100 px, a disclosure below), built from the HTML's h2s, which get ids for it.
// /shipping/ adds the rates of GET shipping/ above the policy. /contact/ gives the support contacts of the config as
// a ruled list and the message form (POST contact/) once config gives the address; until then the API refuses
// messages, so no form is offered.
import "./legal.css";

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { stateName } from "@/components/shop/shop";
import { ContactForm } from "@/components/site/contact-form";
import { Unavailable } from "@/components/site/unavailable";
import { Sheet } from "@/components/ui/band";
import { getLegalPage, type LegalPage } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { ApiError, unwrap } from "@/lib/api/errors";
import { publicFetch, serverApi } from "@/lib/api/server";
import { inrShort } from "@/lib/format";
import { breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";

import { sectioned } from "./sections";

const SLUGS = ["privacy", "terms", "refunds", "shipping", "contact"] as const;
type Slug = (typeof SLUGS)[number];
/** The reading pages and their short names, for "Other pages" and the phone's row of links (About is not a CMS page). */
const PAGES = [
  ["/about/", "About"],
  ["/privacy/", "Privacy"],
  ["/terms/", "Terms"],
  ["/refunds/", "Refunds"],
  ["/shipping/", "Shipping"],
] as const;

export const dynamicParams = false;
export function generateStaticParams() {
  return SLUGS.map((page) => ({ page }));
}

type Props = { params: Promise<{ page: string }> };

async function load(slug: string): Promise<LegalPage | null | "unavailable"> {
  try {
    return await getLegalPage(slug as Slug);
  } catch (error) {
    return error instanceof ApiError && error.status === 404 ? null : "unavailable";
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { page: slug } = await params;
  const page = await load(slug);
  const title = page && page !== "unavailable" ? page.title : "ExamLeaf";
  return pageMetadata({
    title,
    path: `/${slug}/`,
    description: `ExamLeaf LLP, publisher of the ExamLeaf books and website: ${title}.`,
  });
}

const date = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "Asia/Kolkata",
});

async function shippingRates() {
  try {
    return (await unwrap(serverApi.GET("/api/v1/shipping/", publicFetch("shipping")))).rates;
  } catch {
    return null; // the policy still shows; the rates come back with the server
  }
}

export default async function LegalPageView({ params }: Props) {
  const { page: slug } = await params;
  const page = await load(slug);
  if (page === null) notFound();
  if (page === "unavailable") return <Unavailable what="This page" retry={`/${slug}/`} />;
  const [config, rates] = await Promise.all([
    slug === "contact" ? getConfig() : null,
    slug === "shipping" ? shippingRates() : null,
  ]);
  const { html, sections } = sectioned(page.html);
  const updated = date.format(new Date(page.updated));
  const crumbs = (
    <JsonLd
      data={breadcrumbJsonLd([
        { name: "Home", path: "/" },
        { name: page.title, path: `/${slug}/` },
      ])}
    />
  );
  const text = (
    <>
      <div className="prose legal-prose" dangerouslySetInnerHTML={{ __html: html }} />
      <p className="mt-8 mb-0 text-sm text-muted-foreground">
        Version {page.version} · last changed {updated}
      </p>
    </>
  );

  if (slug === "contact") {
    const support = config?.support;
    const facts = [
      ...(support?.email
        ? [
            [
              "Email",
              <a key="email" href={`mailto:${support.email}`}>
                {support.email}
              </a>,
            ] as const,
          ]
        : []),
      ...(support?.phone
        ? [
            [
              "Phone",
              <a key="phone" href={`tel:${support.phone.replace(/[^\d+]/g, "")}`}>
                {support.phone}
              </a>,
            ] as const,
          ]
        : []),
    ];
    return (
      <Sheet
        margin="@"
        className="max-nav:[&>.sheet-margin]:hidden"
        bodyClassName={`legal-body max-nav:pt-6 ${support?.email ? "contact-grid" : ""}`}
      >
        {crumbs}
        <div className="flex min-w-0 flex-col gap-5 [&>*]:m-0">
          <h1 className="text-[clamp(38px,5vw,60px)] leading-none">{page.title}</h1>
          <p className="max-w-[32em] text-lg leading-relaxed text-ink/85 max-nav:text-[15px]">
            For an order, have its number ready (EL-2026-…). It&apos;s in your confirmation email and on the
            order&apos;s page.
          </p>
          <dl className="m-0 border-t-[1.5px] border-foreground">
            {facts.map(([term, value]) => (
              <div key={term} className="grid grid-cols-[120px_minmax(0,1fr)] border-b border-border py-3.5">
                <dt className="text-muted-foreground">{term}</dt>
                <dd className="m-0 font-mono break-words">{value}</dd>
              </div>
            ))}
            <div className="grid grid-cols-[120px_minmax(0,1fr)] items-center border-b border-border py-1.5">
              <dt className="text-muted-foreground">Orders</dt>
              <dd className="m-0">
                <Link href="/orders/lookup/" className="inline-flex min-h-11 items-center font-bold">
                  Find your order
                </Link>
              </dd>
            </div>
          </dl>
        </div>
        {support?.email ? (
          <section aria-labelledby="message-title" className="contact-form-card">
            <h2 id="message-title" className="m-0 mb-[18px] font-head text-2xl leading-tight tracking-normal">
              Send us a message
            </h2>
            <ContactForm />
          </section>
        ) : null}
        <div className="contact-text min-w-0">{text}</div>
      </Sheet>
    );
  }

  return (
    <Sheet className="legal-sheet max-nav:[&>.sheet-margin]:hidden" bodyClassName="legal-body max-nav:pt-6">
      {crumbs}
      <div className="legal-grid">
        <div className="legal-main">
          <p className="label-mono uppercase max-[1100px]:hidden">
            Last updated {updated} · version {page.version}
          </p>
          <nav aria-label="Pages to read" className="legal-pages">
            {PAGES.map(([href, name]) =>
              href === `/${slug}/` ? (
                <span key={href} aria-current="page">
                  {name}
                </span>
              ) : (
                <Link key={href} href={href}>
                  {name}
                </Link>
              ),
            )}
          </nav>
          <h1 className="text-[clamp(38px,5vw,60px)] leading-none">{page.title}</h1>
          {sections.length ? (
            <details className="legal-toc">
              <summary>
                On this page · {sections.length} section{sections.length === 1 ? "" : "s"}
              </summary>
              <ul>
                {sections.map((section) => (
                  <li key={section.id}>
                    <a href={`#${section.id}`}>{section.title}</a>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          {rates?.length ? (
            <div className="table-wrap mb-10 max-w-[44rem]">
              <table>
                <caption className="sr-only">Delivery fees by state</caption>
                <thead>
                  <tr>
                    <th scope="col">State</th>
                    <th scope="col" className="num">
                      Fee
                    </th>
                    <th scope="col" className="num">
                      Free above
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rates.map((rate) => {
                    const states = rate.states.length ? rate.states.map(stateName).join(", ") : "Every other state";
                    return (
                      <tr key={rate.name}>
                        <td>
                          {rate.name}
                          {states !== rate.name ? (
                            <span className="block text-sm text-muted-foreground">{states}</span>
                          ) : null}
                        </td>
                        <td className="num">{inrShort(rate.fee)}</td>
                        <td className="num">{rate.free_above ? inrShort(rate.free_above) : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
          {text}
        </div>
        <aside className="legal-rail" aria-label="On this page">
          <div className="legal-rail-inner">
            {sections.length ? (
              <>
                <h2 className="label-mono text-xs tracking-[0.06em] uppercase">On this page</h2>
                <ul>
                  {sections.map((section) => (
                    <li key={section.id}>
                      <a href={`#${section.id}`}>{section.title}</a>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            <h2 className="label-mono text-xs tracking-[0.06em] uppercase">Other pages</h2>
            <ul className="legal-others">
              {PAGES.filter(([href]) => href !== `/${slug}/`).map(([href, name]) => (
                <li key={href}>
                  <Link href={href}>{name}</Link>
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </Sheet>
  );
}
