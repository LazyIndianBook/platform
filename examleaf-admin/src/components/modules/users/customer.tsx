"use client";

// A customer's record, the parts that act: the contact details (masked; Reveal with a reason, POST users/{id}/reveal/),
// the everyday actions (send the email confirmation or a password reset again, unlock, sign them out everywhere), and
// the Danger section (suspend or lift it, reset two-step sign-in, which a second person approves, and signing in to
// the website as them for 15 minutes, with a reason and the name typed). Each is drawn when the manifest allows it;
// the API decides, may ask to confirm it's you, and records it.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog, ConfirmTyped } from "@/components/data/confirm-typed";
import { MaskedValue } from "@/components/data/masked-value";
import { DangerRow, Facts } from "@/components/data/record-page";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import {
  type CustomerAction,
  type CustomerRecord,
  impersonate,
  resetUserMfa,
  revealUser,
  userAction,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatTime } from "@/lib/format";
import { P } from "@/lib/modules";

export function CustomerContact({ user }: { user: CustomerRecord }) {
  const can = useCan();
  const revealing = can(P.usersReveal);
  return (
    <Facts
      items={[
        {
          label: copy.users.email,
          value: (
            <MaskedValue
              masked={user.masked_email}
              what={copy.masked.email}
              reveal={revealing ? (reason) => revealUser(user.id, "email", reason) : undefined}
            />
          ),
        },
        {
          label: copy.users.phone,
          value: (
            <MaskedValue
              masked={user.masked_phone}
              what={copy.masked.phone}
              reveal={revealing ? (reason) => revealUser(user.id, "phone", reason) : undefined}
            />
          ),
        },
      ]}
    />
  );
}

type Simple = { action: CustomerAction; label: string; done: string; permission: string; when?: boolean };

export function CustomerActions({ user }: { user: CustomerRecord }) {
  const router = useRouter();
  const can = useCan();
  const { run, busy, error } = useAction();
  const [pressed, setPressed] = useState<CustomerAction | null>(null);
  const simple: Simple[] = [
    {
      action: "resend-verification",
      label: copy.users.action.resendVerification,
      done: copy.users.done.resendVerification,
      permission: P.usersResendVerification,
      when: user.email_verified !== true,
    },
    {
      action: "password-reset",
      label: copy.users.action.passwordReset,
      done: copy.users.done.passwordReset,
      permission: P.usersPasswordReset,
    },
    {
      action: "unlock",
      label: copy.users.action.unlock,
      done: copy.users.done.unlock,
      permission: P.usersUnlock,
      when: user.flags.locked,
    },
  ];
  const shown = simple.filter((item) => can(item.permission) && item.when !== false);
  const ending = can(P.usersEndSessions);
  if (!shown.length && !ending) return null;
  return (
    <div className="flex flex-col gap-3">
      <ErrorSummary error={error} />
      <div className="flex flex-wrap gap-2.5">
        {shown.map((item) => (
          <Button
            key={item.action}
            variant="secondary"
            size="sm"
            busy={busy && pressed === item.action}
            onClick={() => {
              setPressed(item.action);
              run(async () => {
                await userAction(user.id, item.action);
                toast.success(item.done);
                router.refresh();
              });
            }}
          >
            {item.label}
          </Button>
        ))}
        {ending ? (
          <ConfirmDialog
            triggerLabel={copy.users.action.endSessions}
            title={copy.users.action.endSessions}
            text={copy.people.endSessionsText}
            confirmLabel={copy.users.action.endSessions}
            success={copy.users.done.endSessions}
            onConfirm={() => userAction(user.id, "end-sessions")}
          />
        ) : null}
      </div>
    </div>
  );
}

export function CustomerDanger({ user }: { user: CustomerRecord }) {
  const can = useCan();
  const router = useRouter();
  const [opened, setOpened] = useState<{ url: string; until: string } | null>(null);
  const suspended = user.status === "suspended" || user.flags.suspended;
  const label = user.name || user.masked_email || user.id;
  return (
    <div className="flex flex-col gap-4">
      {can(P.usersSuspend) ? (
        <DangerRow
          title={suspended ? copy.users.action.unsuspend : copy.users.action.suspend}
          text={copy.users.suspendText}
        >
          <ConfirmDialog
            triggerLabel={suspended ? copy.users.action.unsuspend : copy.users.action.suspend}
            triggerVariant={suspended ? "secondary" : "destructive"}
            title={suspended ? copy.users.action.unsuspend : copy.users.suspendTitle}
            text={copy.users.suspendText}
            confirmLabel={suspended ? copy.users.action.unsuspend : copy.users.action.suspend}
            confirmVariant={suspended ? "primary" : "destructive"}
            success={suspended ? copy.users.done.unsuspend : copy.users.done.suspend}
            onConfirm={() => userAction(user.id, suspended ? "unsuspend" : "suspend")}
          />
        </DangerRow>
      ) : null}
      {can(P.usersResetMfa) ? (
        <DangerRow title={copy.users.action.resetMfa} text={copy.users.resetMfaText}>
          <ConfirmDialog
            triggerLabel={copy.users.action.resetMfa}
            triggerVariant="destructive"
            title={copy.users.resetMfaTitle}
            text={copy.users.resetMfaText}
            confirmLabel={copy.users.action.resetMfa}
            onConfirm={() => resetUserMfa(user.id)}
          />
        </DangerRow>
      ) : null}
      {can(P.usersImpersonate) ? (
        <DangerRow title={copy.users.action.impersonate} text={copy.users.impersonateText}>
          <ConfirmTyped
            label={label}
            triggerLabel={copy.users.action.impersonate}
            triggerVariant="destructive"
            title={copy.users.impersonateTitle}
            text={copy.users.impersonateText}
            confirmLabel={copy.users.impersonateButton}
            reason
            reasonHelp={copy.users.impersonateReasonHelp}
            onConfirm={({ reason }) => impersonate(user.id, reason)}
            onDone={(result) => {
              setOpened(result as { url: string; until: string });
              router.refresh();
            }}
          />
        </DangerRow>
      ) : null}
      {opened ? (
        <Alert variant="success" title={copy.users.impersonateUntil(formatTime(opened.until))}>
          <p>
            <a href={opened.url} target="_blank" rel="noopener noreferrer" className="font-semibold">
              {copy.users.impersonateOpen} <span className="sr-only">{copy.common.opensElsewhere}</span>
            </a>
          </p>
        </Alert>
      ) : null}
    </div>
  );
}
