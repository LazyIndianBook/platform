"use client";

// A staff member's access: their roles (who granted each, why, until when; grant one with an end date and a reason,
// which waits for a second person when it is privileged or for yourself, or revoke one with a reason), their scopes
// (add or remove), ending their sessions, a second-factor reset (always a second person's approval), and offboarding,
// which asks for their email address to be typed. Each call may ask to confirm it's you, or make a change request
// instead (202); separation of duties is the API's (400 with its words).
import { useRouter } from "next/navigation";

import { ConfirmDialog, ConfirmTyped } from "@/components/data/confirm-typed";
import { DangerRow } from "@/components/data/record-page";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { useCan, useManifest } from "@/components/shell/manifest";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import {
  addScope,
  endPersonSessions,
  grantRole,
  offboardPerson,
  type Person,
  removeScope,
  resetPersonMfa,
  type Role,
  revokeRole,
  type ScopeKind,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatDate } from "@/lib/format";
import { P } from "@/lib/modules";

import { ROLE_OPTIONS } from "./people-table";

const row = "flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border py-2.5 text-[15px]";

/** The end of a date input's day in India, as the API's date-time. */
const endOfDay = (day: string) => (day ? `${day}T23:59:59+05:30` : null);

export function PersonRoles({ person }: { person: Person }) {
  const can = useCan();
  const manifest = useManifest();
  const changing = can(P.peopleAssign);
  return (
    <div className="flex flex-col gap-5">
      {person.roles.length ? (
        <ul className="m-0 flex list-none flex-col p-0">
          {person.roles.map((role) => {
            const name = labelOf(copy.people.roleNames, role);
            const grant = person.grants.find((entry) => entry.role === role);
            const until = typeof grant?.expires_at === "string" ? grant.expires_at : null;
            const by = typeof grant?.granted_by === "number" ? grant.granted_by : null;
            return (
              <li key={role} className={row}>
                <span className="flex flex-col">
                  <strong>{name}</strong>
                  <span className="text-sm text-muted-foreground">
                    {until ? copy.account.roleUntil(formatDate(until)) : copy.people.noExpiry}
                    {by ? ` · ${copy.people.grantedBy(staffLabel(by, manifest.user.id))}` : ""}
                    {typeof grant?.reason === "string" && grant.reason ? ` · “${grant.reason}”` : ""}
                  </span>
                </span>
                {changing ? (
                  <ConfirmDialog
                    triggerLabel={
                      <>
                        {copy.people.revoke} <span className="sr-only">{name}</span>
                      </>
                    }
                    title={copy.people.revokeTitle(name)}
                    text={copy.people.revokeText}
                    confirmLabel={copy.people.revoke}
                    reason
                    success={copy.people.revoked}
                    onConfirm={({ reason }) => revokeRole(person.id, role as Role, reason)}
                  />
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="m-0 text-[15px] text-muted-foreground">{copy.people.noRoles}</p>
      )}
      {changing ? (
        <ActionForm
          id={`grant-${person.id}`}
          submitLabel={copy.people.grantButton}
          success={copy.people.granted}
          labels={{ role: copy.people.role, expires_at: copy.people.expires, reason: copy.common.reason }}
          onSubmit={(form) =>
            grantRole(person.id, {
              role: formText(form, "role") as Role,
              reason: formText(form, "reason"),
              expires_at: endOfDay(formText(form, "expires_at")),
            })
          }
        >
          {(error) => (
            <>
              <h3 className="m-0 font-head text-lg">{copy.people.grant}</h3>
              <FormGrid>
                <Field id={`grant-${person.id}-role`} label={copy.people.role} error={fieldError(error, "role")}>
                  <Select name="role" defaultValue="" aria-required="true">
                    <option value="">{copy.people.role}</option>
                    {ROLE_OPTIONS.map((role) => (
                      <option key={role.value} value={role.value}>
                        {role.label}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field
                  id={`grant-${person.id}-expires_at`}
                  label={copy.people.expires}
                  optional
                  help={copy.people.expiresHelp}
                  error={fieldError(error, "expires_at")}
                >
                  <Input name="expires_at" type="date" />
                </Field>
              </FormGrid>
              <Field
                id={`grant-${person.id}-reason`}
                label={copy.common.reason}
                help={copy.common.reasonHelp}
                error={fieldError(error, "reason")}
              >
                <Textarea name="reason" rows={2} aria-required="true" />
              </Field>
            </>
          )}
        </ActionForm>
      ) : null}
    </div>
  );
}

export function PersonScopes({ person }: { person: Person }) {
  const can = useCan();
  const changing = can(P.peopleAssign);
  return (
    <div className="flex flex-col gap-5">
      {person.scopes.length ? (
        <ul className="m-0 flex list-none flex-col p-0">
          {person.scopes.map((scope) => {
            const words = `${labelOf(copy.people.scopeKinds, scope.kind)}: ${scope.value}`;
            return (
              <li key={scope.id} className={row}>
                <span>
                  {words}
                  {scope.expires_at ? (
                    <span className="text-sm text-muted-foreground">
                      {" "}
                      ({copy.account.roleUntil(formatDate(scope.expires_at))})
                    </span>
                  ) : null}
                </span>
                {changing ? (
                  <ConfirmDialog
                    triggerLabel={
                      <>
                        {copy.common.remove} <span className="sr-only">{words}</span>
                      </>
                    }
                    title={copy.people.removeScope(words)}
                    text={copy.people.scopesLead}
                    confirmLabel={copy.common.remove}
                    success={copy.people.scopeRemoved}
                    onConfirm={() => removeScope(person.id, scope.id)}
                  />
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="m-0 text-[15px] text-muted-foreground">{copy.people.noScopes}</p>
      )}
      {changing ? (
        <ActionForm
          id={`scope-${person.id}`}
          submitLabel={copy.people.addScopeButton}
          success={copy.people.scopeAdded}
          labels={{ kind: copy.people.scopeKind, value: copy.people.scopeValue, expires_at: copy.people.expires }}
          onSubmit={(form) =>
            addScope(person.id, {
              kind: formText(form, "kind") as ScopeKind,
              value: formText(form, "value"),
              expires_at: endOfDay(formText(form, "expires_at")),
            })
          }
        >
          {(error) => (
            <>
              <h3 className="m-0 font-head text-lg">{copy.people.addScope}</h3>
              <FormGrid>
                <Field id={`scope-${person.id}-kind`} label={copy.people.scopeKind} error={fieldError(error, "kind")}>
                  <Select name="kind" defaultValue="" aria-required="true">
                    <option value="">{copy.people.scopeKind}</option>
                    {Object.entries(copy.people.scopeKinds).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field
                  id={`scope-${person.id}-value`}
                  label={copy.people.scopeValue}
                  error={fieldError(error, "value")}
                >
                  <Input name="value" autoComplete="off" aria-required="true" />
                </Field>
                <Field
                  id={`scope-${person.id}-expires_at`}
                  label={copy.people.expires}
                  optional
                  error={fieldError(error, "expires_at")}
                >
                  <Input name="expires_at" type="date" />
                </Field>
              </FormGrid>
            </>
          )}
        </ActionForm>
      ) : null}
    </div>
  );
}

export function PersonSessions({ person }: { person: Person }) {
  const can = useCan();
  const router = useRouter();
  if (!can(P.peopleAssign)) return null;
  return (
    <ConfirmDialog
      triggerLabel={copy.people.endSessions}
      title={copy.people.endSessionsTitle}
      text={copy.people.endSessionsText}
      confirmLabel={copy.people.endSessions}
      onConfirm={() => endPersonSessions(person.id)}
      onDone={(result) => {
        toast.success(copy.people.sessionsEnded((result as { sessions: number }).sessions));
        router.refresh();
      }}
    />
  );
}

export function PersonDanger({ person }: { person: Person }) {
  const can = useCan();
  return (
    <div className="flex flex-col gap-4">
      {can(P.usersResetMfa) ? (
        <DangerRow title={copy.people.resetMfa} text={copy.people.resetMfaText}>
          <ConfirmDialog
            triggerLabel={copy.people.resetMfa}
            triggerVariant="destructive"
            title={copy.people.resetMfa}
            text={copy.people.resetMfaText}
            confirmLabel={copy.people.resetMfa}
            reason
            onConfirm={({ reason }) => resetPersonMfa(person.id, reason)}
          />
        </DangerRow>
      ) : null}
      {can(P.peopleAssign) && person.is_active !== false ? (
        <DangerRow title={copy.people.offboardTitle} text={copy.people.offboardText}>
          <ConfirmTyped
            label={person.email}
            triggerLabel={copy.people.offboard}
            triggerVariant="destructive"
            title={copy.people.offboardTitle}
            text={copy.people.offboardText}
            confirmLabel={copy.people.offboardButton}
            reason
            success={copy.people.offboarded}
            onConfirm={({ reason }) => offboardPerson(person.id, reason)}
          />
        </DangerRow>
      ) : null}
    </div>
  );
}
