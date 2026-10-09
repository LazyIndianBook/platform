"use client";

// Log-in and security (Account artboard "Security"): one ruled row per way in (email address, mobile number,
// password, Google, passkeys, two-step log-in), each with its value and one action that opens its form under it;
// then the devices logged in, each with Log out. Each change goes to allauth.headless (src/lib/auth/account.ts),
// which may first want the password again (the reauthenticate page, then back here). A new email address or mobile
// number takes the 6-digit code sent to it.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import { toast } from "@/components/ui/toaster";

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
import { account, type Authenticator, type ProviderAccount, type Session } from "@/lib/auth/account";
import { startProviderLogin } from "@/lib/auth/headless";
import { formatDate } from "@/lib/dates";

import { useAction } from "./use-action";

/** A row's action: bold, underlined, 44 px tall, in the action colour. */
const action =
  "inline-flex min-h-11 cursor-pointer items-center justify-self-end border-0 bg-transparent p-0 text-[15px] font-bold text-primary underline underline-offset-[3px] hover:text-red-ink disabled:cursor-not-allowed disabled:opacity-55";

const subscribeHash = (change: () => void) => {
  window.addEventListener("hashchange", change);
  return () => window.removeEventListener("hashchange", change);
};

function RowText({ id, title, value }: { id: string; title: string; value: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 [&>*]:m-0">
      <h2 id={`${id}-title`} className="font-body text-base leading-snug font-bold">
        {title}
      </h2>
      <p className="text-sm [overflow-wrap:anywhere] text-muted-foreground">{value}</p>
    </div>
  );
}

/** One way in: its title and value, and an action that opens its form under the row. A link to the row
 *  (#change-email, #passkeys …: the old addresses redirect there, next.config.ts) opens it too. */
export function Setting({
  id,
  title,
  value,
  action: label,
  open: opened = false,
  children,
}: {
  id: string;
  title: string;
  value: React.ReactNode;
  action: string;
  open?: boolean;
  children: React.ReactNode;
}) {
  const hash = useSyncExternalStore(
    subscribeHash,
    () => window.location.hash,
    () => "",
  );
  const [toggled, setToggled] = useState<boolean | null>(null);
  const open = toggled ?? (opened || hash === `#${id}`);
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-4 border-t border-border py-3">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4">
        <RowText id={id} title={title} value={value} />
        <button
          type="button"
          aria-expanded={open}
          aria-controls={`${id}-panel`}
          className={action}
          onClick={() => setToggled(!open)}
        >
          {open ? "Close" : label}
          <span className="sr-only">: {title}</span>
        </button>
      </div>
      <div id={`${id}-panel`} hidden={!open} className="flex flex-col gap-4 pt-3 pb-2">
        {children}
      </div>
    </section>
  );
}

/** A row whose action is a page of its own (two-step log-in). */
export function LinkSetting({
  id,
  title,
  value,
  href,
  action: label,
}: {
  id: string;
  title: string;
  value: React.ReactNode;
  href: string;
  action: string;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-4 border-t border-border py-3">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4">
        <RowText id={id} title={title} value={value} />
        <Link href={href} className={action}>
          {label}
          <span className="sr-only">: {title}</span>
        </Link>
      </div>
    </section>
  );
}

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
      <p className="m-0">We have sent a 6-digit code to {sentTo}. Type it here to confirm.</p>
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
            type="button"
            variant="ghost"
            busy={sending.busy}
            onClick={async () => {
              if (await sending.run(resend)) toast.success(`We have sent a new code to ${sentTo}.`);
            }}
          >
            Send a new code
          </Button>
          <Button type="button" variant="ghost" onClick={restart}>
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
        className="flex max-w-[30rem] flex-col gap-4"
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
        <p className="m-0 text-[15px] text-muted-foreground">
          {hasPassword
            ? "Changing it logs you out on your other phones and computers."
            : "Your account has no password yet: you log in with Google or a code. Set one to log in with it too."}
        </p>
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

/** The mobile number for log-in by SMS: a new one (or the first), then the code texted to it. */
export function PhoneForm({ current }: { current: string | null }) {
  const router = useRouter();
  const [sentTo, setSentTo] = useState<string | null>(null);
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
          router.refresh();
        }}
        resend={account.resendPhoneCode}
        restart={() => setSentTo(null)}
      />
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
        Order updates by SMS
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
        <ul className="m-0 flex list-none flex-col p-0">
          {passkeys.map((key) => (
            <li
              key={key.id}
              className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border py-2 first:border-t"
            >
              <span className="font-semibold">{key.name || "Passkey"}</span>
              <span className="text-sm text-muted-foreground">
                Added {formatDate(key.created_at)}
                {key.last_used_at ? ` · last used ${formatDate(key.last_used_at)}` : " · not used yet"}
              </span>
              <RemovePasskey id={key.id!} name={key.name || "Passkey"} />
            </li>
          ))}
        </ul>
      ) : null}
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
        <Button type="submit" variant="secondary" busy={busy}>
          Add a passkey
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
        <button type="button" className={`${action} ml-auto`}>
          Remove<span className="sr-only"> {name}</span>
        </button>
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

/** Google, as a row: the account it logs in with and Disconnect, or Connect (off to Google and back here). */
export function GoogleAccounts({ accounts }: { accounts: ProviderAccount[] }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const linked = accounts[0];
  return (
    <section id="google" aria-labelledby="google-title" className="scroll-mt-4 border-t border-border py-3">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4">
        <RowText
          id="google"
          title="Google"
          value={linked ? `Connected: ${accounts.map((item) => item.display).join(", ")}` : "Not connected"}
        />
        {linked ? (
          <button
            type="button"
            className={action}
            aria-busy={busy || undefined}
            disabled={busy}
            onClick={async () => {
              if (await run(() => account.disconnect(linked.provider.id, linked.uid))) {
                toast.success(`${linked.provider.name} no longer logs you in.`);
                router.refresh();
              }
            }}
          >
            Disconnect<span className="sr-only">: Google</span>
          </button>
        ) : (
          <button
            type="button"
            className={action}
            onClick={() => startProviderLogin("google", "/account/security/", "connect")}
          >
            Connect<span className="sr-only">: Google</span>
          </button>
        )}
      </div>
      {error ? <p className="m-0 font-semibold text-destructive">{error.message}</p> : null}
    </section>
  );
}

/** "Chrome on Android" from a browser's user agent: enough to recognise a device, never the whole string. */
export function deviceName(userAgent: string): string {
  const browser =
    [
      [/Edg\//, "Edge"],
      [/OPR\/|Opera/, "Opera"],
      [/SamsungBrowser/, "Samsung Internet"],
      [/Firefox\/|FxiOS/, "Firefox"],
      [/Chrome\/|CriOS/, "Chrome"],
      [/Safari\//, "Safari"],
    ].find(([pattern]) => (pattern as RegExp).test(userAgent))?.[1] ?? "A browser";
  const system =
    [
      [/Android/, "Android"],
      [/iPhone|iPad|iPod/, "iOS"],
      [/Windows/, "Windows"],
      [/Mac OS X|Macintosh/, "macOS"],
      [/CrOS/, "ChromeOS"],
      [/Linux/, "Linux"],
    ].find(([pattern]) => (pattern as RegExp).test(userAgent))?.[1] ?? null;
  return system ? `${browser} on ${system}` : String(browser);
}

/** An address shortened as the plan asks: 203.0.113.x, or an IPv6 address's first four groups. */
export function shortAddress(ip: string | null): string {
  if (!ip) return "address unknown";
  if (ip.includes(":")) return `${ip.split(":").slice(0, 4).join(":")}:…`;
  return ip.replace(/\.\d+$/, ".x");
}

/** Where the account is signed in (allauth.usersessions): each browser, this one marked; any other logged out at once,
 *  one by one or all together. */
export function Devices({ sessions }: { sessions: Session[] }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [ending, setEnding] = useState<number | null>(null);
  const others = sessions.filter((session) => !session.is_current).map((session) => session.id);
  const when = (seconds: number) => formatDate(new Date(seconds * 1000).toISOString());
  const end = async (ids: number[], one: number | null) => {
    if (busy) return; // one at a time: the other button's answer would land on this one's spinner
    setEnding(one);
    if (await run(() => account.endSessions(ids))) {
      toast.success(ids.length === 1 ? "That device is logged out." : "The other devices are logged out.");
      router.refresh();
    }
  };
  return (
    <>
      <ul className="m-0 flex list-none flex-col p-0">
        {[...sessions]
          .sort((a, b) => Number(b.is_current) - Number(a.is_current))
          .map((session) => (
            <li
              key={session.id}
              className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 border-b border-border py-2.5 text-[15px]"
            >
              <span className="flex min-w-0 flex-col">
                <span>
                  {deviceName(session.user_agent)} · {shortAddress(session.ip)}
                  {session.is_current ? (
                    <>
                      {" "}
                      · <strong>this device</strong>
                    </>
                  ) : null}
                </span>
                <span className="text-sm text-muted-foreground">
                  since {when(session.created_at)}
                  {session.last_seen_at ? ` · last seen ${when(session.last_seen_at)}` : ""}
                </span>
              </span>
              {session.is_current ? (
                <span className="text-muted-foreground">now</span>
              ) : (
                <button
                  type="button"
                  className={action}
                  aria-busy={(busy && ending === session.id) || undefined}
                  disabled={busy}
                  onClick={() => end([session.id], session.id)}
                >
                  Log out<span className="sr-only"> {deviceName(session.user_agent)}</span>
                </button>
              )}
            </li>
          ))}
      </ul>
      {error ? <p className="m-0 font-semibold text-destructive">{error.message}</p> : null}
      {others.length > 1 ? (
        <div className="pt-3">
          <Button variant="secondary" busy={busy && ending === null} onClick={() => end(others, null)}>
            Log out the other devices
          </Button>
        </div>
      ) : null}
    </>
  );
}
