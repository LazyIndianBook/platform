// The badges of an account are the API's facts in words and nothing more: the age band, a student under 18's parent
// consent and how it was given, a lock-out, email and mobile confirmed or not (a mobile that is not on the account is
// not "not verified"), two-step sign-in, teacher access. No score, no group.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { customerWith } from "@/test/customers";

import { ageWords, badgesOf, consentWords, CustomerBadges, verifiedWords } from "./badges";

const texts = (user = customerWith()) => badgesOf(user).map((badge) => badge.text);

describe("badgesOf", () => {
  it("gives an adult with everything confirmed two plain facts", () => {
    expect(texts()).toEqual(["Email verified", "Mobile verified"]);
  });

  it("says a mobile number is not confirmed only when the account has one", () => {
    expect(texts(customerWith({ login_phone_verified: false }))).toEqual(["Email verified", "Mobile not verified"]);
    expect(texts(customerWith({ phone: "", login_phone_verified: false }))).toEqual(["Email verified"]);
    expect(texts(customerWith({ email_verified: false, phone: "" }))).toEqual(["Email not verified"]);
  });

  it("gives a child's age band and the parent consent as it stands", () => {
    const child = { under_18: true, age_band: "13_17", phone: "" };
    expect(texts(customerWith({ ...child, consent: "pending" }))).toEqual([
      "13 to 17",
      "Parent's consent: waiting",
      "Email verified",
    ]);
    expect(
      texts(customerWith({ ...child, age_band: "under_13", consent: "declared", consent_method: "declared" })),
    ).toEqual(["Under 13", "Parent's consent: declared by the student", "Email verified"]);
  });

  it("says how a confirmed consent was given", () => {
    const confirmed = customerWith({
      under_18: true,
      age_band: "13_17",
      consent: "verified",
      consent_method: "staff_manual",
    });
    expect(consentWords(confirmed)).toBe("Parent's consent: confirmed, recorded by hand");
    expect(consentWords({ ...confirmed, consent_method: "email_link" })).toBe(
      "Parent's consent: confirmed, link by email",
    );
    expect(consentWords(customerWith())).toBeNull();
  });

  it("names an age not known, a lock-out, two-step sign-in and teacher access", () => {
    expect(texts(customerWith({ age_band: "unknown", locked: true, mfa_on: true, teacher: "verified" }))).toEqual([
      "Age not known",
      "Locked",
      "Email verified",
      "Mobile verified",
      "Two-step on",
      "Teacher verified",
    ]);
    expect(texts(customerWith({ teacher: "requested" }))).toContain("Teacher access asked for");
  });
});

describe("the words of a list's columns", () => {
  it("reads the age band and what is verified", () => {
    expect(ageWords("13_17")).toBe("13 to 17");
    expect(ageWords("unknown")).toBe("Not known");
    expect(verifiedWords(customerWith())).toBe("Email and mobile");
    expect(verifiedWords(customerWith({ login_phone_verified: false }))).toBe("Email");
    expect(verifiedWords(customerWith({ email_verified: false }))).toBe("Mobile");
    expect(verifiedWords(customerWith({ email_verified: false, login_phone_verified: false }))).toBe("Not verified");
    expect(verifiedWords(customerWith({ phone: "", login_phone_verified: true }))).toBe("Email");
  });
});

describe("CustomerBadges", () => {
  it("draws each badge as a list item, in words", () => {
    render(<CustomerBadges user={customerWith({ mfa_on: true })} />);
    const list = screen.getByRole("list", { name: "About the account" });
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["Email verified", "Mobile verified", "Two-step on"]);
  });
});
