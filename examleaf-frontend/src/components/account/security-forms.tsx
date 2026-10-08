"use client";

// Log-in and security (Django's allauth pages for the email address, password, mobile number and passkeys): each
// change goes to allauth.headless (src/lib/auth/account.ts), which may first want the password again (the
// reauthenticate page, then back here). A new email address or mobile number takes the 6-digit code sent to it.
import { KeyRound, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/choice";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, InputPrefix } from "@/components/ui/input";
import { OtpInput } from "@/components/ui/input-otp";
import { api, personal } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { account, type Authenticator, type ProviderAccount } from "@/lib/auth/account";
import { startProviderLogin } from "@/lib/auth/headless";
import { formatDate } from "@/lib/dates";

import { useAction } from "./use-action";

/** The 6-digit code step of a new email address or mobile number: the code, Confirm, a new code, or start again. */
export function CodeStep({
  sentTo,
  name,
  confirm,
  resend,
  restart,
}: {
  sentTo: string;
  name: "code" | "key";
  confirm: (code: string) => Promise<unknown>;
  resend: () => Promise<unknown>;
  restart: () => void;
}) {
  const [code, setCode] = useState("");
  const { run, busy, error } = useAction();
  const sending = useAction();
  return (
    <>
      <p>We have sent a 6-digit code to {sentTo}. Type it here to confirm.</p>
      <ErrorSummary error={error ?? sending.error} labels={{ [name]: "Code" }} />
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          await run(() => confirm(code));
        }}
      >
        <Field id={name} label="Code" required error={fieldError(error, name)}>
          <OtpInput name={name} value={code} onChange={setCode} autoFocus />
        </Field>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" busy={busy} disabled={code.length < 6}>
            Confirm
          </Button>
          <Button
            variant="ghost"
            busy={sending.busy}
            onClick={async () => {
              if (await sending.run(resend)) toast.success(`We have sent a new code to ${sentTo}.`);
            }}
          >
            Send a new code
          </Button>
          <Button variant="ghost" onClick={restart}>
            Use another
          </Button>
        </div>
      </form>
    </>
  );
}

export function EmailForm({ pending }: { pending: string | null }) {
  const router = useRouter();
  const [sentTo, setSentTo] = useState(pending);
  const { run, busy, error } = useAction();
  if (sentTo) {
    return (
      <CodeStep
        sentTo={sentTo}
        name="key"
        confirm={async (code) => {
          await account.verifyEmail(code);
          toast.success(`Your email address is now ${sentTo}.`);
          setSentTo(null);
          router.refresh();
        }}
        resend={() => account.resendEmailCode(sentTo)}
        restart={() => setSentTo(null)}
      />
    );
  }
  return (
    <>
      <ErrorSummary error={error} labels={{ email: "New email address" }} />
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const email = String(new FormData(event.currentTarget).get("email") ?? "").trim();
          if (await run(() => account.changeEmail(email))) setSentTo(email);
        }}
      >
        <Field
          id="email"
          label="New email address"
          required
          help="It replaces the one above once you have typed the code we email to it."
          error={fieldError(error, "email")}
        >
          <Input name="email" type="email" autoComplete="email" inputMode="email" />
        </Field>
        <div>
          <Button type="submit" variant="secondary" busy={busy}>
            Email me a code
          </Button>
        </div>
      </form>
    </>
  );
}

export function PasswordForm({ hasPassword }: { hasPassword: boolean }) {
  const { run, busy, error, setError } = useAction();
  const [form, setForm] = useState(0);
  return (
    <>
      <ErrorSummary
        error={error}
        labels={{
          current_password: "Current password",
          new_password: "New password",
          new_password2: "New password again",
        }}
      />
      <form
        key={form}
        className="flex max-w-[30rem] flex-col gap-4"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          const value = (name: string) => String(data.get(name) ?? "");
          if (value("new_password") !== value("new_password2")) {
            const message = "The two passwords differ.";
            setError(new ApiError(400, "invalid", message, { new_password2: [message] }));
            return;
          }
          const current = hasPassword ? value("current_password") : undefined;
          if (await run(() => account.changePassword(value("new_password"), current))) {
            toast.success(hasPassword ? "Your password is changed." : "Your password is set.");
            setForm((count) => count + 1);
          }
        }}
      >
        {hasPassword ? (
          <Field id="current_password" label="Current password" required error={fieldError(error, "current_password")}>
            <Input name="current_password" type="password" autoComplete="current-password" />
          </Field>
        ) : null}
        <Field
          id="new_password"
          label="New password"
          required
          help="At least 10 characters: not only numbers, not a common password, not like your name or email."
          error={fieldError(error, "new_password")}
        >
          <Input name="new_password" type="password" autoComplete="new-password" />
        </Field>
        <Field id="new_password2" label="New password again" required error={fieldError(error, "new_password2")}>
          <Input name="new_password2" type="password" autoComplete="new-password" />
        </Field>
        <div>
          <Button type="submit" variant="secondary" busy={busy}>
            {hasPassword ? "Change my password" : "Set my password"}
          </Button>
        </div>
      </form>
    </>
  );
}

export function PhoneForm({ current }: { current: string | null }) {
  const router = useRouter();
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [changing, setChanging] = useState(!current);
  const { run, busy, error } = useAction();
  if (sentTo) {
    return (
      <CodeStep
        sentTo={sentTo}
        name="code"
        confirm={async (code) => {
          await account.verifyPhone(code);
          toast.success(`Your mobile number ${sentTo} is confirmed: log in with a code by SMS.`);
          setSentTo(null);
          setChanging(false);
          router.refresh();
        }}
        resend={account.resendPhoneCode}
        restart={() => setSentTo(null)}
      />
    );
  }
  if (!changing) {
    return (
      <div>
        <Button variant="secondary" onClick={() => setChanging(true)}>
          Change the number
        </Button>
      </div>
    );
  }
  return (
    <>
      <ErrorSummary error={error} labels={{ phone: "Mobile number" }} />
      <form
        className="flex max-w-[30rem] flex-col gap-4"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const phone = String(new FormData(event.currentTarget).get("phone") ?? "").trim();
          if (await run(() => account.changePhone(phone))) setSentTo(phone.startsWith("+") ? phone : `+91 ${phone}`);
        }}
      >
        <Field
          id="phone"
          label={current ? "New mobile number" : "Mobile number"}
          required
          help="We text it a 6-digit code. One account per number."
          error={fieldError(error, "phone")}
        >
          <InputPrefix prefix="+91" name="phone" type="tel" inputMode="tel" autoComplete="tel-national" />
        </Field>
        <div>
          <Button type="submit" variant="secondary" busy={busy}>
            Text me a code
          </Button>
        </div>
      </form>
    </>
  );
}

export function SmsUpdatesSwitch({ on }: { on: boolean }) {
  const router = useRouter();
  const [checked, setChecked] = useState(on);
  const { run, busy, error } = useAction();
  return (
    <>
      <Switch
        checked={checked}
        disabled={busy}
        onChange={async (event) => {
          const next = event.currentTarget.checked;
          setChecked(next);
          const ok = await run(() => personal(api.PATCH("/api/v1/me/", { body: { sms_updates: next } })));
          if (ok) {
            toast.success(next ? "We will text you about your orders." : "No more texts about your orders.");
            router.refresh();
          } else setChecked(!next);
        }}
      >
        Text me when an order is placed, shipped and delivered
      </Switch>
      {error ? <p className="m-0 font-semibold text-destructive">{error.message}</p> : null}
    </>
  );
}

export function Passkeys({ passkeys }: { passkeys: Authenticator[] }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [made, setMade] = useState(0);
  return (
    <>
      {passkeys.length ? (
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {passkeys.map((key) => (
            <li
              key={key.id}
              className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-lg border border-border px-4 py-3"
            >
              <KeyRound aria-hidden="true" className="size-5 text-primary" />
              <span className="font-semibold">{key.name || "Passkey"}</span>
              <span className="text-[15px] text-muted-foreground">
                Added {formatDate(key.created_at)}
                {key.last_used_at ? ` · last used ${formatDate(key.last_used_at)}` : " · not used yet"}
              </span>
              <RemovePasskey id={key.id!} name={key.name || "Passkey"} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground">No passkey yet.</p>
      )}
      <ErrorSummary error={error} labels={{ name: "Name" }} />
      <form
        key={made}
        className="flex flex-wrap items-end gap-3"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const name = String(new FormData(event.currentTarget).get("name") ?? "").trim() || "Passkey";
          let codes = false;
          const ok = await run(async () => {
            codes = (await account.addPasskey(name)).recoveryCodesMade;
          });
          if (!ok) return;
          toast.success(
            codes
              ? "Your passkey is added. We have also made recovery codes: see Two-step log-in."
              : "Your passkey is added: use it at Log in.",
          );
          setMade((count) => count + 1);
          router.refresh();
        }}
      >
        <Field id="name" label="Name it" optional className="flex-[1_1_220px]" error={fieldError(error, "name")}>
          <Input name="name" maxLength={40} placeholder="My phone" />
        </Field>
        <Button type="submit" variant="secondary" busy={busy} className="min-h-12">
          <Plus aria-hidden="true" />
          <span>Add a passkey</span>
        </Button>
      </form>
    </>
  );
}

function RemovePasskey({ id, name }: { id: number; name: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { run, busy, error } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="ml-auto">
          <Trash2 aria-hidden="true" />
          <span>Remove</span>
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>Remove this passkey?</DialogHeader>
        <DialogBody>
          <DialogDescription>
            {name} will no longer log you in. You can add it again later from this page.
          </DialogDescription>
          {error ? <p className="font-semibold text-destructive">{error.message}</p> : null}
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary" autoFocus>
              Keep it
            </Button>
          </DialogClose>
          <Button
            variant="destructive"
            busy={busy}
            onClick={async () => {
              if (await run(() => account.removePasskey(id))) {
                setOpen(false);
                toast.success("The passkey is removed.");
                router.refresh();
              }
            }}
          >
            Remove
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function GoogleAccounts({ accounts }: { accounts: ProviderAccount[] }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <>
      {accounts.map((item) => (
        <div key={item.uid} className="flex flex-wrap items-center gap-3 rounded-lg border border-border px-4 py-3">
          <span>
            {item.provider.name}: <strong>{item.display}</strong>
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            busy={busy}
            onClick={async () => {
              if (await run(() => account.disconnect(item.provider.id, item.uid))) {
                toast.success(`${item.provider.name} no longer logs you in.`);
                router.refresh();
              }
            }}
          >
            Disconnect
          </Button>
        </div>
      ))}
      {error ? <p className="font-semibold text-destructive">{error.message}</p> : null}
      {accounts.length ? null : (
        <div>
          <Button variant="secondary" onClick={() => startProviderLogin("google", "/account/security/", "connect")}>
            Connect Google
          </Button>
        </div>
      )}
    </>
  );
}
