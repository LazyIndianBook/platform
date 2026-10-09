// The contact page's disclosures (GET /api/v1/config/'s disclosures and dark_pattern_certificate; the E-Commerce
// Rules r.4, the DPDP Rules r.9): who sells (the legal name, the registered office, where it works from), where the
// return and refund terms are, the Grievance Officer and the nodal contact, how to make a request about one's personal
// data and whom to ask, the National Consumer Helpline, and the dark-pattern self-audit's certificate in force. Each
// shows once the panel or the environment sets it; nothing stands in for a value not set yet.
// Direction A ("Contact"): ruled lists under the serif's h2, as the page's own facts.
import Link from "next/link";

import { formatDate } from "@/lib/dates";
import { type Certificate, type Disclosures, grievanceOfficer, helplineLine, returnsPage } from "@/lib/disclosures";

const FACT = "grid grid-cols-[160px_minmax(0,1fr)] gap-x-4 border-b border-border py-3.5 max-nav:grid-cols-1";
const HEADING = "m-0 font-head text-2xl leading-tight tracking-normal";

function Facts({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="m-0 border-t-[1.5px] border-foreground">
      {rows.map(([term, value]) => (
        <div key={term} className={FACT}>
          <dt className="text-muted-foreground">{term}</dt>
          <dd className="m-0 break-words whitespace-pre-line">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function DisclosuresBlock({
  disclosures,
  certificate,
}: {
  disclosures: Disclosures | null | undefined;
  certificate: Certificate | null | undefined;
}) {
  const day = (iso: string) => formatDate(iso, "long");
  const returns = returnsPage(disclosures);
  const company: [string, React.ReactNode][] = [
    ...(disclosures?.legal_name ? [["Legal name", disclosures.legal_name] as [string, string]] : []),
    ...(disclosures?.registered_address
      ? [["Registered office", disclosures.registered_address] as [string, string]]
      : []),
    ...(disclosures?.operating_address ? [["Works from", disclosures.operating_address] as [string, string]] : []),
    ...(returns
      ? [
          [
            "Returns and refunds",
            <Link key="returns" href={returns.href}>
              {returns.name}
            </Link>,
          ] as [string, React.ReactNode],
        ]
      : []),
  ];
  const officer = grievanceOfficer(disclosures);
  const grievance: [string, React.ReactNode][] = [
    ...(officer ? [["Name", officer] as [string, string]] : []),
    ...(officer && disclosures?.grievance_contact
      ? [["Contact", disclosures.grievance_contact] as [string, string]]
      : []),
    ...(disclosures?.nodal_contact ? [["Nodal contact in India", disclosures.nodal_contact] as [string, string]] : []),
  ];
  const helpline = helplineLine(disclosures, day);
  const data = disclosures?.rights_text || disclosures?.dpdp_contact || helpline;
  if (!company.length && !grievance.length && !data && !certificate) return null;
  return (
    <div className="flex min-w-0 flex-col gap-8 [&>section]:flex [&>section]:flex-col [&>section]:gap-3.5">
      {company.length ? (
        <section aria-labelledby="who-we-are">
          <h2 id="who-we-are" className={HEADING}>
            Who we are
          </h2>
          <Facts rows={company} />
        </section>
      ) : null}
      {grievance.length ? (
        <section aria-labelledby="grievance-officer">
          <h2 id="grievance-officer" className={HEADING}>
            Grievance Officer
          </h2>
          <p className="m-0 max-w-[36em] leading-relaxed">
            For a complaint about an order, the website or your personal data. We acknowledge it within 48 hours and
            answer within a month.
          </p>
          <Facts rows={grievance} />
        </section>
      ) : null}
      {data ? (
        <section aria-labelledby="your-data">
          <h2 id="your-data" className={HEADING}>
            Your personal data
          </h2>
          {disclosures?.rights_text ? (
            <p className="m-0 max-w-[36em] leading-relaxed whitespace-pre-line">{disclosures.rights_text}</p>
          ) : null}
          {disclosures?.dpdp_contact ? (
            <Facts rows={[["Questions about your data", disclosures.dpdp_contact]]} />
          ) : null}
          {helpline ? <p className="m-0 max-w-[36em] leading-relaxed">{helpline}</p> : null}
        </section>
      ) : null}
      {certificate ? (
        <section aria-labelledby="dark-pattern-certificate">
          <h2 id="dark-pattern-certificate" className={HEADING}>
            Dark-pattern self-audit, {certificate.year}
          </h2>
          <p className="m-0 max-w-[36em] leading-relaxed whitespace-pre-line">{certificate.text}</p>
          <p className="m-0 text-sm text-muted-foreground">Certified from {day(certificate.effective_from)}.</p>
        </section>
      ) : null}
    </div>
  );
}
