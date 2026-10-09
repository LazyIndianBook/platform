// The e-commerce disclosures of GET /api/v1/config/ (the E-Commerce Rules r.4; the DPDP Rules r.9) as the website
// words them: each value is null until the panel or the environment sets it, and nothing is shown for it then.
import type { components } from "./api/schema";

export type Disclosures = components["schemas"]["DisclosuresConfig"];
export type Certificate = components["schemas"]["DarkPatternCertificate"];

/** The page that holds the return and refund terms, by its slug, and its name. */
const RETURNS_PAGES: Record<string, string> = {
  refunds: "Refunds and cancellations",
  shipping: "Shipping and delivery",
  terms: "Terms and conditions",
};

/** "Anita Baruah, Grievance Officer": the officer's name and designation, or null until named. */
export function grievanceOfficer(disclosures: Disclosures | null | undefined): string | null {
  if (!disclosures?.grievance_officer) return null;
  return [disclosures.grievance_officer, disclosures.grievance_designation].filter(Boolean).join(", ");
}

/** The return and refund terms' page: its path and name, or null while not set. */
export function returnsPage(disclosures: Disclosures | null | undefined): { href: string; name: string } | null {
  const slug = disclosures?.returns_page;
  return slug && RETURNS_PAGES[slug] ? { href: `/${slug}/`, name: RETURNS_PAGES[slug] } : null;
}

/** The National Consumer Helpline's convergence programme: a member since a day, or applied on one; null otherwise. */
export function helplineLine(disclosures: Disclosures | null | undefined, day: (iso: string) => string): string | null {
  const since = disclosures?.nch_since ? ` ${day(disclosures.nch_since)}` : "";
  if (disclosures?.nch_status === "member")
    return `A member of the National Consumer Helpline's convergence programme${since ? ` since${since}` : ""}.`;
  if (disclosures?.nch_status === "applied")
    return `Applied to join the National Consumer Helpline's convergence programme${since ? ` on${since}` : ""}.`;
  return null;
}
