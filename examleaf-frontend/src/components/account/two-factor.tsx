"use client";

// Two-step log-in (Account artboard "2FA setup", States "Recovery codes"; allauth mfa): the authenticator app set up
// with its QR code and a first code, then its recovery codes shown as the board; or turned off. The recovery codes
// shown, saved as a text file, copied, or made again. allauth may first want the password again
// (src/lib/auth/account.ts sends the visitor to type it, then back here). The QR code is drawn here from the
// otpauth:// link (lean-qr: the link holds the secret, so it never goes to an image service).
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "@/components/ui/toaster";

import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { Button, buttonVariants } from "@/components/ui/button";
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
import { OtpInput } from "@/components/ui/input-otp";
import { account, type Authenticator } from "@/lib/auth/account";

import { QrCode } from "./qr-code";
import { useAction } from "./use-action";

/** A dangerous action behind a dialog that opens on its safe button. */
function Confirm({
  trigger,
  title,
  children,
  action,
  onConfirm,
}: {
  trigger: string;
  title: string;
  children: React.ReactNode;
  action: string;
  onConfirm: () => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const { run, busy, error } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="secondary">{trigger}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>{title}</DialogHeader>
        <DialogBody>
          <DialogDescription>{children}</DialogDescription>
          {error ? <p className="font-semibold text-destructive">{error.message}</p> : null}
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary" autoFocus>
              Cancel
            </Button>
          </DialogClose>
          <Button variant="destructive" busy={busy} onClick={async () => (await run(onConfirm)) && setOpen(false)}>
            {action}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The setup's sheet: white, an ink border, the title in the serif. */
function SetupCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      aria-labelledby="totp-title"
      className="flex max-w-[30rem] flex-col gap-3.5 border-[1.5px] border-foreground bg-card p-7 max-nav:p-5 [&_p]:m-0"
    >
      <h2 id="totp-title" className="m-0 text-[26px] leading-tight max-nav:text-[22px]">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** The recovery codes as the board: two columns of mono codes in a dashed box, then Download and Copy. */
export function RecoveryBoard({ codes, children }: { codes: string[]; children?: React.ReactNode }) {
  const [copied, setCopied] = useState<string | null>(null);
  const text = `ExamLeaf recovery codes\n\n${codes.join("\n")}\n`;
  return (
    <div className="flex flex-col gap-3.5">
      <ul
        aria-label="Your recovery codes"
        className="m-0 grid list-none grid-cols-2 gap-x-6 gap-y-2 border-[1.5px] border-dashed border-input bg-card p-4 font-mono text-base leading-snug font-medium max-[359px]:grid-cols-1"
      >
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-3">
        <a
          href={`data:text/plain;charset=utf-8,${encodeURIComponent(text)}`}
          download="examleaf-recovery-codes.txt"
          className={buttonVariants({ variant: "secondary" })}
        >
          Download
        </a>
        <Button
          variant="secondary"
          onClick={() =>
            navigator.clipboard
              ?.writeText(codes.join("\n"))
              .then(() => setCopied("Copied: paste them somewhere safe."))
              .catch(() => setCopied("This browser would not copy them: download them instead."))
          }
        >
          Copy
        </Button>
        {children}
      </div>
      <p role="status" className="m-0 text-sm text-muted-foreground">
        {copied}
      </p>
    </div>
  );
}

export function AuthenticatorApp({ active }: { active: boolean }) {
  const router = useRouter();
  const [setup, setSetup] = useState<{ secret: string; url: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const { run, busy, error } = useAction();

  if (codes) {
    return (
      <SetupCard title="Two-step log-in is on">
        <p className="text-base leading-relaxed text-ink/85">
          If you lose your phone, each of these codes lets you in once. Keep them somewhere safe.
        </p>
        <RecoveryBoard codes={codes}>
          <Button onClick={() => setCodes(null)}>I&apos;ve saved them</Button>
        </RecoveryBoard>
      </SetupCard>
    );
  }
  if (active) {
    return (
      <SetupCard title="Two-step log-in is on">
        <p className="text-[15px] leading-relaxed text-ink/85">
          After your password, Log in asks for the 6-digit code your authenticator app shows.
        </p>
        <div>
          <Confirm
            trigger="Turn it off"
            title="Turn off the authenticator app?"
            action="Turn it off"
            onConfirm={async () => {
              await account.deactivateTotp();
              toast.success("The authenticator app is off.");
              router.refresh();
            }}
          >
            Log in will no longer ask for its code. Staff accounts must set one up again before they can use the admin.
          </Confirm>
        </div>
      </SetupCard>
    );
  }
  if (!setup) {
    return (
      <SetupCard title="Turn on two-step log-in">
        <p className="text-[15px] leading-relaxed text-ink/85">
          An app on your phone (Google Authenticator, Microsoft Authenticator, Aegis) shows a new 6-digit code every 30
          seconds; Log in asks for it after your password.
        </p>
        <ErrorSummary error={error} />
        <div>
          <Button
            busy={busy}
            onClick={() =>
              run(async () => {
                const state = await account.totp();
                if (state.active) router.refresh();
                else setSetup(state);
              })
            }
          >
            Set up the authenticator app
          </Button>
        </div>
      </SetupCard>
    );
  }
  return (
    <SetupCard title="Turn on two-step log-in">
      <p className="text-[15px] leading-relaxed text-ink/85">
        Scan this with an authenticator app, then enter the 6-digit code it shows.
      </p>
      <div className="flex flex-wrap items-center gap-[18px]">
        <QrCode text={setup.url} label="QR code of the key, for the authenticator app" size={140} />
        <p className="font-mono text-[13px] leading-relaxed font-medium break-all text-ink/85">
          Can&apos;t scan?
          <br />
          <span className="text-foreground">{setup.secret.replace(/(.{4})/g, "$1 ").trim()}</span>
          <br />
          <a href={setup.url} className="font-body text-sm font-bold">
            Open it in the app on this phone
          </a>
        </p>
      </div>
      <ErrorSummary error={error} labels={{ code: "Code from the app" }} />
      <form
        className="flex flex-col gap-3.5"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          let made: string[] = [];
          const ok = await run(async () => {
            await account.activateTotp(code);
            // the first second step makes the recovery codes: shown now, as the board (Turn on busy until then)
            made = (await account.recoveryCodes().catch(() => null))?.unused_codes ?? [];
          });
          if (!ok) return;
          if (made.length) setCodes(made);
          else toast.success("The authenticator app is on. Keep your recovery codes somewhere safe.");
          router.refresh(); // the page behind the board (its recovery codes' count) reads it as on
        }}
      >
        <Field id="code" label="Code from the app" required error={fieldError(error, "code")}>
          <OtpInput value={code} onChange={setCode} autoFocus />
        </Field>
        <Button type="submit" size="lg" block busy={busy} disabled={code.length < 6}>
          Turn on
        </Button>
      </form>
      <p className="text-sm text-muted-foreground">Next, we show your recovery codes. Keep them somewhere safe.</p>
    </SetupCard>
  );
}

export function RecoveryCodes({ summary }: { summary: Authenticator | null }) {
  const [codes, setCodes] = useState<Authenticator | null>(null);
  const { run, busy, error } = useAction();
  const unused = codes?.unused_codes ?? [];
  const counts = codes ?? summary;
  return (
    <section aria-labelledby="codes-title" className="flex max-w-[30rem] flex-col gap-3.5 [&_p]:m-0">
      <h2 id="codes-title" className="m-0 border-t-[1.5px] border-foreground pt-[18px] text-2xl leading-[1.2]">
        Recovery codes
      </h2>
      <p className="text-[15px] leading-relaxed text-ink/85">
        Each recovery code logs you in once when you do not have your phone.
        {counts?.total_code_count
          ? ` ${counts.unused_code_count} of ${counts.total_code_count} are unused.`
          : " You have none yet: they are made with your first second step."}
      </p>
      <ErrorSummary error={error} />
      {unused.length ? (
        <RecoveryBoard codes={unused}>
          <Confirm
            trigger="Make new codes"
            title="Make new recovery codes?"
            action="Make new codes"
            onConfirm={async () => setCodes(await account.newRecoveryCodes())}
          >
            The codes you have now stop working.
          </Confirm>
        </RecoveryBoard>
      ) : summary ? (
        <div>
          <Button
            variant="secondary"
            busy={busy}
            onClick={() => run(async () => setCodes(await account.recoveryCodes()))}
          >
            Show my recovery codes
          </Button>
        </div>
      ) : null}
    </section>
  );
}
