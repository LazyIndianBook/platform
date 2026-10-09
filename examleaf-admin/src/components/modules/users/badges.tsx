// The badges of an account (the plan's 5.4), from the fields the API sends with every customer: the age band, a
// student under 18's parent consent and how it was given, a lock-out, the email address and the mobile number
// confirmed or not, two-step sign-in, teacher access. The words come from here, the facts from the API: the console
// works out nothing the API did not say (no score, no group). The account's own status is drawn apart, by its chip.
import { StatusChip, type Tone } from "@/components/data/status-chip";
import type { Customer } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

export type Badge = { key: string; tone: Tone; text: string };

type Fields = Pick<
  Customer,
  | "under_18"
  | "age_band"
  | "consent"
  | "consent_method"
  | "locked"
  | "email_verified"
  | "login_phone_verified"
  | "phone"
  | "mfa_on"
  | "teacher"
>;

/** The age band in words: "Under 13", "13 to 17", "Adult", "Not known". */
export const ageWords = (band: string) => labelOf(copy.customers.ageBands, band);

/** How a student under 18's consent stands, in one phrase ("confirmed, link by email"); null for an adult. */
export function consentWords(user: Pick<Fields, "under_18" | "consent" | "consent_method">): string | null {
  if (!user.under_18 || user.consent === "adult") return null;
  const state = labelOf(copy.customers.badges.consentStates, user.consent);
  return user.consent === "verified" && user.consent_method
    ? copy.customers.badges.consentVia(state, labelOf(copy.customers.methods, user.consent_method))
    : copy.customers.badges.consent(state);
}

/** Email and mobile as "Email and mobile", "Email", "Mobile" or "Not verified" (a mobile that is not on the account
 *  does not count against it). */
export function verifiedWords(user: Pick<Fields, "email_verified" | "login_phone_verified" | "phone">): string {
  const email = user.email_verified;
  const phone = Boolean(user.phone) && Boolean(user.login_phone_verified);
  const words = copy.customers.verified;
  return email && phone ? words.both : email ? words.email : phone ? words.phone : words.neither;
}

/** The badges, in the order the record reads them. */
export function badgesOf(user: Fields): Badge[] {
  const words = copy.customers.badges;
  const badges: Badge[] = [];
  if (user.age_band === "under_13") badges.push({ key: "age", tone: "moving", text: words.under13 });
  else if (user.age_band === "13_17") badges.push({ key: "age", tone: "moving", text: words.teen });
  else if (user.age_band === "unknown") badges.push({ key: "age", tone: "stopped", text: words.ageUnknown });
  const consent = consentWords(user);
  if (consent) {
    const tone: Tone = user.consent === "verified" ? "done" : user.consent === "pending" ? "waiting" : "moving";
    badges.push({ key: "consent", tone, text: consent });
  }
  if (user.locked) badges.push({ key: "locked", tone: "bad", text: words.locked });
  badges.push(
    user.email_verified
      ? { key: "email", tone: "done", text: words.emailYes }
      : { key: "email", tone: "waiting", text: words.emailNo },
  );
  if (user.phone)
    badges.push(
      user.login_phone_verified
        ? { key: "phone", tone: "done", text: words.phoneYes }
        : { key: "phone", tone: "waiting", text: words.phoneNo },
    );
  if (user.mfa_on) badges.push({ key: "twoStep", tone: "done", text: words.twoStep });
  if (user.teacher === "verified") badges.push({ key: "teacher", tone: "done", text: words.teacherVerified });
  else if (user.teacher === "requested") badges.push({ key: "teacher", tone: "waiting", text: words.teacherRequested });
  return badges;
}

export function CustomerBadges({ user }: { user: Fields }) {
  return (
    <ul aria-label={copy.customers.badges.label} className="m-0 inline-flex list-none flex-wrap gap-1.5 p-0">
      {badgesOf(user).map((badge) => (
        <li key={badge.key} className="max-w-full">
          {/* a long phrase ("Parent's consent: confirmed, the parent's own account") wraps rather than widening a phone */}
          <StatusChip tone={badge.tone} className="max-w-full text-left leading-snug whitespace-normal">
            {badge.text}
          </StatusChip>
        </li>
      ))}
    </ul>
  );
}
