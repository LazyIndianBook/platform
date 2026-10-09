"use client";

// Staff as a list (GET people/): who, their roles (and until when), whether two-step sign-in is on, the last sign-in
// and whether the account is on. The invitation form and the invitations (GET people/invites/, revoked with DELETE
// people/invites/{id}/) sit under the list (#invite).
import { ConfirmDialog } from "@/components/data/confirm-typed";
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { invitePerson, type Person, type Role, revokeInvite, type SavedView, type StaffInvite } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

/** A person's role in words, with its end date when its grant has one. */
export function roleLabel(role: string, person: Pick<Person, "grants">): string {
  const name = labelOf(copy.people.roleNames, role);
  const until = person.grants.find((grant) => grant.role === role)?.expires_at;
  return typeof until === "string" ? `${name} (${copy.account.roleUntil(formatDate(until))})` : name;
}

export function PersonStatus({ person }: { person: Pick<Person, "is_active" | "is_superuser"> }) {
  if (person.is_superuser) return <StatusChip tone="waiting">{copy.people.statuses.breakGlass}</StatusChip>;
  return person.is_active === false ? (
    <StatusChip tone="stopped">{copy.people.statuses.inactive}</StatusChip>
  ) : (
    <StatusChip tone="good">{copy.people.statuses.active}</StatusChip>
  );
}

export function PeopleTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: Person[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const columns: Column<Person>[] = [
    { key: "name", label: copy.people.columns.name, render: (person) => person.full_name || person.email },
    { key: "email", label: copy.users.columns.email, render: (person) => person.email },
    {
      key: "roles",
      label: copy.people.columns.roles,
      render: (person) =>
        person.roles.length ? person.roles.map((role) => roleLabel(role, person)).join(", ") : copy.people.noRoles,
    },
    {
      key: "mfa",
      label: copy.people.columns.mfa,
      render: (person) =>
        person.mfa ? copy.people.mfaOn : <span className="font-semibold text-destructive">{copy.people.mfaOff}</span>,
    },
    { key: "lastLogin", label: copy.people.columns.lastLogin, render: (person) => formatDateTime(person.last_login) },
    { key: "status", label: copy.people.columns.status, render: (person) => <PersonStatus person={person} /> },
  ];
  return (
    <DataTable
      listKey="people"
      caption={copy.people.title}
      rows={rows}
      columns={columns}
      rowId={(person) => String(person.id)}
      rowHref={(person) => `/people/${person.id}/`}
      next={next}
      previous={previous}
      views={views}
      empty={{ title: copy.people.emptyTitle, text: copy.people.emptyText }}
    />
  );
}

/** The roles a person can be given: the backend's role names (the API says no to any it does not have). */
export const ROLE_OPTIONS = Object.entries(copy.people.roleNames).map(([value, label]) => ({
  value: value as Role,
  label,
}));

export function InviteForm() {
  return (
    <ActionForm
      id="invite"
      submitLabel={copy.people.inviteSend}
      success={copy.people.invited}
      labels={{ email: copy.people.inviteEmail, role: copy.people.inviteRole, reason: copy.common.reason }}
      onSubmit={(form) =>
        invitePerson({
          email: formText(form, "email"),
          role: formText(form, "role") as Role,
          reason: formText(form, "reason"),
        })
      }
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="invite-email" label={copy.people.inviteEmail} error={fieldError(error, "email")}>
              <Input name="email" type="email" autoComplete="off" aria-required="true" />
            </Field>
            <Field id="invite-role" label={copy.people.inviteRole} error={fieldError(error, "role")}>
              <Select name="role" defaultValue="" aria-required="true">
                <option value="">{copy.people.role}</option>
                {ROLE_OPTIONS.map((role) => (
                  <option key={role.value} value={role.value}>
                    {role.label}
                  </option>
                ))}
              </Select>
            </Field>
          </FormGrid>
          <Field
            id="invite-reason"
            label={copy.common.reason}
            help={copy.common.reasonHelp}
            error={fieldError(error, "reason")}
          >
            <Textarea name="reason" rows={2} aria-required="true" />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

function inviteState(invite: StaffInvite, now: number): string {
  if (invite.accepted_at) return "accepted";
  if (invite.revoked_at) return "revoked";
  return Date.parse(invite.expires_at) <= now ? "expired" : "waiting";
}

export function Invites({ invites, now }: { invites: StaffInvite[]; now: number }) {
  const can = useCan();
  if (!invites.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.people.noInvites}</p>;
  const revoking = can(P.peopleAssign);
  return (
    <Table caption={copy.people.invites}>
      <thead>
        <tr>
          <TableHead>{copy.people.inviteColumns.email}</TableHead>
          <TableHead>{copy.people.inviteColumns.role}</TableHead>
          <TableHead>{copy.people.inviteColumns.sent}</TableHead>
          <TableHead>{copy.people.inviteColumns.expires}</TableHead>
          <TableHead>{copy.people.inviteColumns.state}</TableHead>
          {revoking ? <TableHead>{copy.common.actions}</TableHead> : null}
        </tr>
      </thead>
      <tbody>
        {invites.map((invite) => {
          const state = inviteState(invite, now);
          return (
            <tr key={invite.id}>
              <TableCell className="font-mono text-[14px]">{invite.email}</TableCell>
              <TableCell>{labelOf(copy.people.roleNames, invite.role)}</TableCell>
              <TableCell>{formatDateTime(invite.created)}</TableCell>
              <TableCell>{formatDateTime(invite.expires_at)}</TableCell>
              <TableCell>
                <StatusChip tone={state === "waiting" ? "waiting" : state === "accepted" ? "done" : "stopped"}>
                  {labelOf(copy.people.inviteStates, state)}
                </StatusChip>
              </TableCell>
              {revoking ? (
                <TableCell>
                  {state === "waiting" ? (
                    <ConfirmDialog
                      triggerLabel={
                        <>
                          {copy.people.revokeInvite} <span className="sr-only">{invite.email}</span>
                        </>
                      }
                      title={copy.people.revokeInviteTitle}
                      text={copy.people.revokeInviteText}
                      confirmLabel={copy.people.revokeInvite}
                      success={copy.people.inviteRevoked}
                      onConfirm={() => revokeInvite(invite.id)}
                    />
                  ) : null}
                </TableCell>
              ) : null}
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}
