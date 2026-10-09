"use client";

// Staff as a list (GET people/?q=): who, their roles (and until when), whether two-step sign-in is on, the last
// sign-in, how many devices are signed in, and their status. The invitation form sits under the list (#invite).
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { invitePerson, type SavedView, type StaffMember } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";

export function roleLabel(role: { name: string; expires_at: string | null }): string {
  const name = labelOf(copy.people.roleNames, role.name);
  return role.expires_at ? `${name} (${copy.account.roleUntil(formatDate(role.expires_at))})` : name;
}

export function PeopleTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: StaffMember[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const columns: Column<StaffMember>[] = [
    { key: "name", label: copy.people.columns.name, render: (person) => person.name || person.email },
    { key: "email", label: copy.users.columns.email, render: (person) => person.email },
    {
      key: "roles",
      label: copy.people.columns.roles,
      render: (person) => (person.roles.length ? person.roles.map(roleLabel).join(", ") : copy.people.noRoles),
    },
    {
      key: "mfa",
      label: copy.people.columns.mfa,
      render: (person) =>
        person.mfa ? copy.people.mfaOn : <span className="font-semibold text-destructive">{copy.people.mfaOff}</span>,
    },
    { key: "lastLogin", label: copy.people.columns.lastLogin, render: (person) => formatDateTime(person.last_login) },
    { key: "sessions", label: copy.people.columns.sessions, render: (person) => person.sessions, numeric: true },
    {
      key: "status",
      label: copy.people.columns.status,
      render: (person) => (
        <StatusChip tone={toneOf(person.status)}>{labelOf(copy.people.statuses, person.status)}</StatusChip>
      ),
    },
  ];
  return (
    <DataTable
      listKey="people"
      caption={copy.people.title}
      rows={rows}
      columns={columns}
      rowId={(person) => person.id}
      rowLabel={(person) => person.name || person.email}
      rowHref={(person) => `/people/${person.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[{ name: "q", label: copy.filters.searchList(copy.people.title.toLowerCase()), type: "search" }]}
      empty={{ title: copy.people.emptyTitle, text: copy.people.emptyText }}
    />
  );
}

/** The roles a person can be given: the plan's role templates (the API says no to any it does not have). */
export const ROLE_OPTIONS = Object.entries(copy.people.roleNames).map(([value, label]) => ({ value, label }));

export function InviteForm() {
  return (
    <ActionForm
      id="invite"
      submitLabel={copy.people.inviteSend}
      success={copy.people.invited}
      labels={{ email: copy.people.inviteEmail, role: copy.people.inviteRole }}
      onSubmit={(form) => invitePerson({ email: formText(form, "email"), role: formText(form, "role") })}
    >
      {(error) => (
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
      )}
    </ActionForm>
  );
}
