"use client";

// A customer's record, the parts that act: the contact details (masked; Reveal with a reason, POST users/{id}/reveal/
// {show: [...]}), the everyday actions (the parent's consent link again while it waits, a password reset link, unlock,
// sign them out everywhere), and the Danger section (suspend or lift it with a reason, reset two-step sign-in, which a
// second person approves, and signing in to the website as them for 15 minutes, with a ticket, a reason and the name
// typed). Each is drawn when the manifest allows it; the API decides, may ask to confirm it's you, and records it.
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
  type CustomerDetail,
  endImpersonation,
  type Impersonation,
  impersonate,
  resetUserMfa,
  revealUser,
  suspendUser,
  userAction,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatTime } from "@/lib/format";
import { P } from "@/lib/modules";
import { WEBSITE_URL } from "@/lib/site";

export function CustomerContact({ user }: { user: CustomerDetail }) {
  const can = useCan();
  const revealing = can(P.usersReveal);
  return (
    <Facts
      items={[
        {
          label: copy.users.email,
          value: (
            <MaskedValue
              masked={user.email}
              what={copy.masked.email}
              reveal={revealing ? (reason) => revealUser(user.id, ["email"], reason) : undefined}
            />
          ),
        },
        {
          label: copy.users.phone,
          value: (
            <MaskedValue
              masked={user.phone}
              what={copy.masked.phone}
              reveal={revealing ? (reason) => revealUser(user.id, ["login_phone", "phone"], reason) : undefined}
            />
          ),
        },
        ...(user.parent_contact
          ? [
              {
                label: copy.users.parentContact,
                value: (
                  <MaskedValue
                    masked={user.parent_contact}
                    what={copy.users.parentContact.toLowerCase()}
                    reveal={revealing ? (reason) => revealUser(user.id, ["parent_contact"], reason) : undefined}
                  />
                ),
              },
            ]
          : []),
      ]}
    />
  );
}

type Simple = { action: CustomerAction; label: string; done: string; permission: string; when?: boolean };

export function CustomerActions({ user }: { user: CustomerDetail }) {
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
      when: user.consent === "pending",
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
      when: user.locked,
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
            onConfirm={() => userAction(user.id, "end-sessions")}
            onDone={(result) => {
              toast.success(copy.people.sessionsEnded((result as { sessions: number }).sessions));
              router.refresh();
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

function Impersonating({ user, opened, onEnd }: { user: CustomerDetail; opened: Impersonation; onEnd: () => void }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <Alert variant="success" title={copy.users.impersonateUntil(formatTime(opened.until))}>
      <p>
        <a href={opened.url} target="_blank" rel="noopener noreferrer" className="font-semibold">
          {copy.users.impersonateOpen} <span className="sr-only">{copy.common.opensElsewhere}</span>
        </a>
      </p>
      {error ? <p className="font-semibold text-destructive">{error.message}</p> : null}
      <p>
        <Button
          size="sm"
          variant="secondary"
          busy={busy}
          onClick={() =>
            run(async () => {
              await endImpersonation(user.id, opened.token);
              toast.success(copy.users.impersonateEnded);
              onEnd();
              router.refresh();
            })
          }
        >
          {copy.users.impersonateEnd}
        </Button>
      </p>
    </Alert>
  );
}

export function CustomerDanger({ user }: { user: CustomerDetail }) {
  const can = useCan();
  const router = useRouter();
  // started here: its link and End (after a reload, the shell's banner keeps End for this tab)
  const [opened, setOpened] = useState<Impersonation | null>(null);
  const suspended = user.status === "suspended";
  const label = user.full_name || user.email;
  return (
    <div className="flex flex-col gap-4">
      {can(P.usersSuspend) && user.status !== "erased" ? (
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
            reason
            success={suspended ? copy.users.done.unsuspend : copy.users.done.suspend}
            onConfirm={({ reason }) => suspendUser(user.id, !suspended, reason)}
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
            reason
            onConfirm={({ reason }) => resetUserMfa(user.id, reason)}
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
            fields={[{ name: "ticket", label: copy.users.impersonateTicket, help: copy.users.impersonateTicketHelp }]}
            reason
            reasonHelp={copy.users.impersonateReasonHelp}
            onConfirm={({ reason, values }) =>
              impersonate(user.id, { reason, ticket: values.ticket ?? "" }, WEBSITE_URL)
            }
            onDone={(result) => {
              setOpened(result as Impersonation);
              router.refresh();
            }}
          />
        </DangerRow>
      ) : null}
      {opened ? <Impersonating user={user} opened={opened} onEnd={() => setOpened(null)} /> : null}
    </div>
  );
}
