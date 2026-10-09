"use client";

// A staff member's access: their roles (who granted each, until when; grant one with an end date and a reason, or
// revoke one), their scopes (add or remove), their signed-in devices (end them all), and offboarding, which asks for
// their email address to be typed. Each call may ask to confirm it's you, or make a change request instead.
import { ConfirmDialog, ConfirmTyped } from "@/components/data/confirm-typed";
import { DangerRow } from "@/components/data/record-page";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import {
  addScope,
  endPersonSessions,
  grantRole,
  offboardPerson,
  removeScope,
  revokeRole,
  type StaffMember,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate } from "@/lib/format";
import { P } from "@/lib/modules";

import { ROLE_OPTIONS } from "./people-table";

const row = "flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border py-2.5 text-[15px]";

export function PersonRoles({ person }: { person: StaffMember }) {
  const can = useCan();
  const changing = can(P.peopleRoles);
  return (
    <div className="flex flex-col gap-5">
      {person.roles.length ? (
        <ul className="m-0 flex list-none flex-col p-0">
          {person.roles.map((role) => {
            const name = labelOf(copy.people.roleNames, role.name);
            return (
              <li key={role.name} className={row}>
                <span className="flex flex-col">
                  <strong>{name}</strong>
                  <span className="text-sm text-muted-foreground">
                    {role.expires_at ? copy.account.roleUntil(formatDate(role.expires_at)) : copy.people.noExpiry}
                    {role.granted_by
                      ? ` · ${copy.people.grantedBy(role.granted_by.name || role.granted_by.email)}`
                      : ""}
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
                    success={copy.people.revoked}
                    onConfirm={() => revokeRole(person.id, role.name)}
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
              role: formText(form, "role"),
              reason: formText(form, "reason"),
              ...(formText(form, "expires_at") ? { expires_at: formText(form, "expires_at") } : {}),
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

export function PersonScopes({ person }: { person: StaffMember }) {
  const can = useCan();
  const changing = can(P.peopleScopes);
  return (
    <div className="flex flex-col gap-5">
      {person.scopes.length ? (
        <ul className="m-0 flex list-none flex-col p-0">
          {person.scopes.map((scope) => {
            const words = `${labelOf(copy.people.scopeKinds, scope.kind)}: ${scope.value}`;
            return (
              <li key={scope.id} className={row}>
                <span>{words}</span>
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
          labels={{ kind: copy.people.scopeKind, value: copy.people.scopeValue, reason: copy.common.reason }}
          onSubmit={(form) =>
            addScope(person.id, {
              kind: formText(form, "kind"),
              value: formText(form, "value"),
              reason: formText(form, "reason"),
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
              </FormGrid>
              <Field
                id={`scope-${person.id}-reason`}
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

export function PersonSessions({ person }: { person: StaffMember }) {
  const can = useCan();
  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <p className="m-0 text-[15px]">{copy.people.sessionsCount(person.sessions)}</p>
      {can(P.peopleSessions) && person.sessions > 0 ? (
        <ConfirmDialog
          triggerLabel={copy.people.endSessions}
          title={copy.people.endSessionsTitle}
          text={copy.people.endSessionsText}
          confirmLabel={copy.people.endSessions}
          success={copy.people.sessionsEnded}
          onConfirm={() => endPersonSessions(person.id)}
        />
      ) : null}
    </div>
  );
}

export function Offboard({ person }: { person: StaffMember }) {
  return (
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
  );
}
