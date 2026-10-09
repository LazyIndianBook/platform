// The e-commerce disclosures as the website shows them (config's disclosures and dark_pattern_certificate): nothing
// for a value not set yet, the contact page's whole block once set, and the footer's legal name, Grievance Officer and
// certificate lines linking to it.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { type Disclosures, grievanceOfficer, helplineLine, returnsPage } from "@/lib/disclosures";

import { DisclosuresBlock } from "./disclosures";
import { SiteFooter } from "./site-footer";

const NONE: Disclosures = {
  legal_name: null,
  registered_address: null,
  operating_address: null,
  care_phone: null,
  care_email: null,
  care_hours: null,
  grievance_officer: null,
  grievance_designation: null,
  grievance_contact: null,
  nodal_contact: null,
  returns_page: null,
  dpdp_contact: null,
  rights_text: null,
  nch_status: null,
  nch_since: null,
};
const SET: Disclosures = {
  ...NONE,
  legal_name: "ExamLeaf Test Publishers",
  registered_address: "1 Test Lane, Guwahati, Assam 781001",
  grievance_officer: "Anita Baruah",
  grievance_designation: "Grievance Officer",
  grievance_contact: "grievance@example.com, +91 361 000 0000",
  returns_page: "refunds",
  dpdp_contact: "privacy@example.com",
  rights_text: "Write to us from the account's address.",
  nch_status: "member",
  nch_since: "2026-09-19",
};
const CERTIFICATE = { year: 2027, text: "No dark pattern found.", effective_from: "2027-01-01" };
const day = (iso: string) => `day ${iso}`;

describe("the disclosures' words", () => {
  it("are nothing until set", () => {
    expect(grievanceOfficer(NONE)).toBeNull();
    expect(returnsPage(NONE)).toBeNull();
    expect(helplineLine(NONE, day)).toBeNull();
    expect(helplineLine({ ...NONE, nch_status: "not_joined" }, day)).toBeNull();
  });

  it("name the officer, the returns page and the helpline", () => {
    expect(grievanceOfficer(SET)).toBe("Anita Baruah, Grievance Officer");
    expect(grievanceOfficer({ ...SET, grievance_designation: null })).toBe("Anita Baruah");
    expect(returnsPage(SET)).toEqual({ href: "/refunds/", name: "Refunds and cancellations" });
    expect(returnsPage({ ...SET, returns_page: "elsewhere" })).toBeNull();
    expect(helplineLine(SET, day)).toBe(
      "A member of the National Consumer Helpline's convergence programme since day 2026-09-19.",
    );
    expect(helplineLine({ ...SET, nch_status: "applied", nch_since: null }, day)).toBe(
      "Applied to join the National Consumer Helpline's convergence programme.",
    );
  });
});

describe("the contact page's block", () => {
  it("shows nothing while nothing is set", () => {
    const { container } = render(<DisclosuresBlock disclosures={NONE} certificate={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows who we are, the Grievance Officer, the data contacts and the certificate", () => {
    render(<DisclosuresBlock disclosures={SET} certificate={CERTIFICATE} />);
    const who = screen.getByRole("region", { name: "Who we are" });
    expect(within(who).getByText("ExamLeaf Test Publishers")).toBeInTheDocument();
    expect(within(who).getByRole("link", { name: "Refunds and cancellations" })).toHaveAttribute("href", "/refunds/");
    const officer = screen.getByRole("region", { name: "Grievance Officer" });
    expect(within(officer).getByText("Anita Baruah, Grievance Officer")).toBeInTheDocument();
    expect(within(officer).getByText("grievance@example.com, +91 361 000 0000")).toBeInTheDocument();
    const data = screen.getByRole("region", { name: "Your personal data" });
    expect(within(data).getByText("privacy@example.com")).toBeInTheDocument();
    expect(within(data).getByText(/since 19 September 2026/)).toBeInTheDocument();
    const certificate = screen.getByRole("region", { name: "Dark-pattern self-audit, 2027" });
    expect(within(certificate).getByText("Certified from 1 January 2027.")).toBeInTheDocument();
  });
});

describe("the footer", () => {
  it("keeps its line until the disclosures are set", () => {
    render(<SiteFooter books={[]} signedIn={false} legal={null} />);
    expect(screen.getByText("© ExamLeaf LLP")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Grievance Officer/ })).toBeNull();
  });

  it("names the legal name, the Grievance Officer and the certificate, linking to the contact page", () => {
    render(
      <SiteFooter books={[]} signedIn={false} legal={{ disclosures: SET, dark_pattern_certificate: CERTIFICATE }} />,
    );
    expect(screen.getByText("© ExamLeaf Test Publishers")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Grievance Officer: Anita Baruah, Grievance Officer" })).toHaveAttribute(
      "href",
      "/contact/#grievance-officer",
    );
    expect(screen.getByRole("link", { name: "Dark-pattern self-audit certificate, 2027" })).toHaveAttribute(
      "href",
      "/contact/#dark-pattern-certificate",
    );
  });
});
