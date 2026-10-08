// allauth.headless's account endpoints for the signed-in visitor (Log-in and security, Two-step log-in): the mobile
// number with its texted code, the email address with its emailed code, the password, passkeys, the authenticator app
// and recovery codes, Google. A 401 means either that the session ended (log in, then back here) or that allauth wants
// the password again before this change (reauthenticate, then back here): the visitor is sent there and the call
// throws an ApiError with status 401, which the forms do not show (the page is already leaving).
import { ApiError } from "@/lib/api/errors";

import { type AuthResult, auth, call } from "./headless";
import { withNext } from "./next-url";
import { createCredential } from "./webauthn";

export type Authenticator = {
  type: "totp" | "recovery_codes" | "webauthn";
  id?: number;
  name?: string;
  created_at: number;
  last_used_at: number | null;
  is_passwordless?: boolean;
  total_code_count?: number;
  unused_code_count?: number;
  unused_codes?: string[];
};
export type PhoneNumber = { phone: string; verified: boolean };
export type EmailAddress = { email: string; primary: boolean; verified: boolean };
export type ProviderAccount = { uid: string; display: string; provider: { id: string; name: string } };
/** A browser signed in to the account (allauth.usersessions): times in seconds since 1970. */
export type Session = {
  id: number;
  user_agent: string;
  ip: string | null;
  created_at: number;
  last_seen_at?: number;
  is_current: boolean;
};

/** The answer of a signed-in call, or off to log in / reauthenticate with this page as the destination. */
export async function signedIn(answer: Promise<AuthResult>): Promise<AuthResult> {
  const result = await answer;
  if (result.status !== 401) return result;
  const here = window.location.pathname + window.location.search;
  // signed in but not recently enough: allauth lists reauthenticate (and mfa_reauthenticate) as the way on
  const again = result.authenticated;
  window.location.assign(withNext(again ? "/account/reauthenticate/" : "/account/login/", here));
  throw new ApiError(401, again ? "reauthentication_required" : "unauthenticated", "Please log in again.");
}

const data = <T>(result: AuthResult) => result.data as unknown as T;

export const account = {
  /** The mobile number for log-in by SMS: a new one gets a code (202), confirmed with verifyPhone. */
  changePhone: (phone: string) => signedIn(call("POST", "/account/phone", { phone })),
  verifyPhone: (code: string) => signedIn(call("POST", "/auth/phone/verify", { code })),
  resendPhoneCode: () => signedIn(call("POST", "/auth/phone/verify/resend")),

  /** A new email address replaces the old one once its emailed code is confirmed (ACCOUNT_CHANGE_EMAIL). */
  emails: async () => data<EmailAddress[]>(await signedIn(call("GET", "/account/email"))),
  changeEmail: (email: string) => signedIn(call("POST", "/account/email", { email })),
  verifyEmail: (code: string) => signedIn(auth.verifyEmail(code)),
  resendEmailCode: (email: string) => signedIn(call("PUT", "/account/email", { email })),

  /** Without a usable password (signed up with Google) the current one is not asked. */
  changePassword: (newPassword: string, currentPassword?: string) =>
    signedIn(
      call("POST", "/account/password/change", {
        new_password: newPassword,
        ...(currentPassword === undefined ? {} : { current_password: currentPassword }),
      }),
    ),

  authenticators: async () => data<Authenticator[]>(await signedIn(call("GET", "/account/authenticators"))),

  /** A passkey to log in with (passwordless): the browser's prompt between the options and the answer. Says whether
   *  allauth made recovery codes with it (the account's first second factor). */
  async addPasskey(name: string): Promise<{ recoveryCodesMade: boolean }> {
    const options = await signedIn(call("GET", "/account/authenticators/webauthn?passwordless"));
    const credential = await createCredential(options.data.creation_options);
    const result = await signedIn(call("POST", "/account/authenticators/webauthn", { name, credential }));
    return { recoveryCodesMade: Boolean(result.meta?.recovery_codes_generated) };
  },
  removePasskey: (id: number) => signedIn(call("DELETE", "/account/authenticators/webauthn", { authenticators: [id] })),

  /** The authenticator app: null with a fresh secret to set it up (allauth answers 404 then), or the active one. */
  async totp(): Promise<{ active: true } | { active: false; secret: string; url: string }> {
    try {
      await signedIn(call("GET", "/account/authenticators/totp"));
      return { active: true };
    } catch (error) {
      const meta = error instanceof ApiError && error.status === 404 && (error.body as { meta?: TotpMeta })?.meta;
      if (meta) return { active: false, secret: meta.secret, url: meta.totp_url };
      throw error;
    }
  },
  activateTotp: (code: string) => signedIn(call("POST", "/account/authenticators/totp", { code })),
  deactivateTotp: () => signedIn(call("DELETE", "/account/authenticators/totp")),
  recoveryCodes: async () => data<Authenticator>(await signedIn(call("GET", "/account/authenticators/recovery-codes"))),
  newRecoveryCodes: async () =>
    data<Authenticator>(await signedIn(call("POST", "/account/authenticators/recovery-codes"))),

  providers: async () => data<ProviderAccount[]>(await signedIn(call("GET", "/account/providers"))),
  /** Log these browsers out (their sessions end at once). */
  endSessions: (ids: number[]) => signedIn(call("DELETE", "/auth/sessions", { sessions: ids })),
  disconnect: (provider: string, uid: string) =>
    signedIn(call("DELETE", "/account/providers", { provider, account: uid })),
};

type TotpMeta = { secret: string; totp_url: string };
