"use client";

// "Confirm it's you": when a staff call answers 403 reauth_required (a role change, a reveal, an approval, a key),
// the transport waits on this dialog (lib/api/client.ts `reauth`), which runs allauth's reauthenticate flows: the
// authenticator app's code first, the password or a passkey instead. Confirmed, the call is sent once more; closed,
// it fails with reauth_required and the form says nothing changed.
import { useId, useState, useSyncExternalStore } from "react";

import { CodeField } from "@/components/auth/code-field";
import { PasswordInput } from "@/components/auth/password-input";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { reauth } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { type AuthResult, auth, type Flow } from "@/lib/auth/headless";
import { copy } from "@/lib/copy";

type Method = "code" | "password";

/** What the flows offer: the app's code first, the password, a passkey when listed. */
export function reauthOptions(flows: Flow[]) {
  const mfa = flows.find((flow) => flow.id === "mfa_reauthenticate");
  const password = flows.some((flow) => flow.id === "reauthenticate");
  return {
    first: (mfa || !password ? "code" : "password") as Method,
    password: password || !flows.length,
    code: Boolean(mfa) || !flows.length,
    passkey: Boolean(mfa?.types?.includes("webauthn")),
  };
}

export function ReauthDialog() {
  const id = useId();
  const flows = useSyncExternalStore(reauth.subscribe, reauth.current, () => null);
  const options = reauthOptions(flows ?? []);
  const [choice, setChoice] = useState<Method | null>(null);
  const method = choice ?? options.first;
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const finish = (confirmed: boolean) => {
    setChoice(null);
    setCode("");
    setError(null);
    reauth.settle(confirmed);
  };

  async function confirm(call: () => Promise<AuthResult>) {
    setBusy(true);
    setError(null);
    try {
      const result = await call();
      if (result.status === 200) finish(true);
      else setError(new ApiError(result.status, "reauth_failed", copy.errors.reauthRequired));
    } catch (caught) {
      if (caught instanceof ApiError) setError(caught);
      else if (!(caught instanceof DOMException && caught.name === "NotAllowedError"))
        setError(new ApiError(0, "unavailable", copy.errors.unavailable));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={flows !== null} onOpenChange={(open) => !open && finish(false)}>
      <DialogContent>
        <DialogHeader>{copy.auth.confirmTitle}</DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-3.5"
          onSubmit={(event) => {
            event.preventDefault();
            const password = String(new FormData(event.currentTarget).get("password") ?? "");
            confirm(() => (method === "code" ? auth.mfaReauthenticate(code) : auth.reauthenticate(password)));
          }}
        >
          <DialogBody>
            <DialogDescription>
              {copy.auth.confirmLead} {method === "code" ? copy.auth.confirmCode : null}
            </DialogDescription>
          </DialogBody>
          <ErrorSummary error={error} idPrefix={`${id}-`} />
          {method === "code" ? (
            <CodeField id={`${id}-code`} value={code} onChange={setCode} error={fieldError(error, "code")} />
          ) : (
            <Field id={`${id}-password`} label={copy.auth.password} error={fieldError(error, "password")}>
              <PasswordInput name="password" autoComplete="current-password" aria-required="true" />
            </Field>
          )}
          <p className="m-0 flex flex-wrap gap-x-4 text-[15px]">
            {method === "code" && options.password ? (
              <button
                type="button"
                className="min-h-11 cursor-pointer font-semibold text-primary underline"
                onClick={() => setChoice("password")}
              >
                {copy.auth.confirmPassword}
              </button>
            ) : null}
            {method === "password" && options.code ? (
              <button
                type="button"
                className="min-h-11 cursor-pointer font-semibold text-primary underline"
                onClick={() => setChoice("code")}
              >
                {copy.auth.confirmUseCode}
              </button>
            ) : null}
            {options.passkey ? (
              <button
                type="button"
                className="min-h-11 cursor-pointer font-semibold text-primary underline"
                disabled={busy}
                onClick={() => confirm(() => auth.passkeyReauthenticate())}
              >
                {copy.auth.confirmPasskey}
              </button>
            ) : null}
          </p>
          <DialogFooter>
            {/* a plain button, not the dialog's safe one: the dialog opens on the code's boxes */}
            <Button variant="secondary" onClick={() => finish(false)}>
              {copy.common.cancel}
            </Button>
            <Button type="submit" busy={busy} disabled={method === "code" && code.length < 6}>
              {copy.auth.confirm}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
