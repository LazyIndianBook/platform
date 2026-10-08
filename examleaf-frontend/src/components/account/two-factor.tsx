"use client";

// Two-step log-in (Django's allauth mfa pages; required for staff): the authenticator app set up with its key and a
// first code, or turned off; the recovery codes shown, saved as a text file, or made again. allauth may first want
// the password again (src/lib/auth/account.ts sends the visitor to type it, then back here).
import { Download, KeyRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

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

export function AuthenticatorApp({ active }: { active: boolean }) {
  const router = useRouter();
  const [setup, setSetup] = useState<{ secret: string; url: string } | null>(null);
  const [code, setCode] = useState("");
  const { run, busy, error } = useAction();

  if (active) {
    return (
      <>
        <p>The authenticator app is on: after your password, Log in asks for the code it shows.</p>
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
      </>
    );
  }
  if (!setup) {
    return (
      <>
        <p>
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
            <KeyRound aria-hidden="true" />
            <span>Set up the authenticator app</span>
          </Button>
        </div>
      </>
    );
  }
  return (
    <>
      <ol className="m-0 flex flex-col gap-2 pl-5">
        <li>
          In your authenticator app, add an account with this key:{" "}
          <code className="rounded-sm bg-muted px-1.5 py-0.5 text-base break-all">
            {setup.secret.replace(/(.{4})/g, "$1 ").trim()}
          </code>
          . On this phone, <a href={setup.url}>open it in the app</a> instead.
        </li>
        <li>Type the 6-digit code the app shows for ExamLeaf.</li>
      </ol>
      <ErrorSummary error={error} labels={{ code: "Code" }} />
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const ok = await run(() => account.activateTotp(code));
          if (ok) {
            toast.success("The authenticator app is on. Keep your recovery codes somewhere safe.");
            router.refresh();
          }
        }}
      >
        <Field id="code" label="Code from the app" required error={fieldError(error, "code")}>
          <OtpInput value={code} onChange={setCode} autoFocus />
        </Field>
        <div>
          <Button type="submit" busy={busy} disabled={code.length < 6}>
            Turn it on
          </Button>
        </div>
      </form>
    </>
  );
}

export function RecoveryCodes({ summary }: { summary: Authenticator | null }) {
  const [codes, setCodes] = useState<Authenticator | null>(null);
  const { run, busy, error } = useAction();
  const unused = codes?.unused_codes ?? [];
  const counts = codes ?? summary;
  const file = `data:text/plain;charset=utf-8,${encodeURIComponent(`ExamLeaf recovery codes\n\n${unused.join("\n")}\n`)}`;
  return (
    <>
      <p>
        Each recovery code logs you in once when you do not have your phone.
        {counts?.total_code_count
          ? ` ${counts.unused_code_count} of ${counts.total_code_count} are unused.`
          : " You have none yet: they are made with your first second step."}
      </p>
      <ErrorSummary error={error} />
      {unused.length ? (
        <>
          <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-2 p-0 font-mono text-base">
            {unused.map((code) => (
              <li key={code} className="rounded-sm bg-muted px-2 py-1">
                {code}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-3">
            <a href={file} download="examleaf-recovery-codes.txt" className={buttonVariants({ variant: "secondary" })}>
              <Download aria-hidden="true" />
              <span>Save them as a file</span>
            </a>
            <Confirm
              trigger="Make new codes"
              title="Make new recovery codes?"
              action="Make new codes"
              onConfirm={async () => setCodes(await account.newRecoveryCodes())}
            >
              The codes you have now stop working.
            </Confirm>
          </div>
        </>
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
    </>
  );
}
