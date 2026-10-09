"use client";

// What granting or taking away a role would change, before anything is asked (POST people/<id>/roles/preview/): the
// permissions gained and lost, the limits and narrowing that change, the idle limit, the separation-of-duty conflicts
// that would refuse it, whether a second person approves it, a passkey to come, the ERPNext role profiles. Read again
// whenever the role changes; nothing changes until the grant itself is sent (and the API checks everything again).
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { previewRole, type RolePreview as Preview } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

import { limitText } from "./access";

const words = copy.management.preview;

type State = { key: string; preview: Preview | null; failed: ApiError | null };

export function RolePreview({ person, role, action }: { person: number; role: string; action: "grant" | "revoke" }) {
  const key = `${person}:${role}:${action}`;
  const [state, setState] = useState<State>({ key: "", preview: null, failed: null });
  useEffect(() => {
    if (!role) return;
    const controller = new AbortController();
    previewRole(person, { role: role as Preview["role"], action }, controller.signal).then(
      (preview) => setState({ key, preview, failed: null }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ key, preview: null, failed: error instanceof ApiError ? error : null });
      },
    );
    return () => controller.abort();
  }, [person, role, action, key]);

  if (!role) return null;
  const name = labelOf(copy.people.roleNames, role);
  const current = state.key === key ? state : { preview: null, failed: null };
  return (
    <section
      aria-live="polite"
      aria-label={action === "grant" ? words.title(name) : words.revokeTitle(name)}
      className="flex flex-col gap-2 border-l-2 border-border pl-4 text-[15px]"
    >
      <h4 className="m-0 font-semibold">{action === "grant" ? words.title(name) : words.revokeTitle(name)}</h4>
      {current.preview ? (
        <PreviewText preview={current.preview} />
      ) : current.failed || state.key === key ? (
        <p className="m-0 text-muted-foreground">{current.failed?.message ?? words.failed}</p>
      ) : (
        <p className="m-0 text-muted-foreground">{words.loading}</p>
      )}
    </section>
  );
}

function PreviewText({ preview }: { preview: Preview }) {
  const count = (areas: Preview["gains"]) =>
    areas.map((area) => words.areaCount(area.area, area.permissions.length)).join("; ");
  const changes = [
    ...preview.limits.map((row) =>
      words.limitChange(labelOf(copy.account.limitNames, row.name), limitText(row.before), limitText(row.after)),
    ),
    ...preview.scopes.map((row) =>
      row.added
        ? words.scopeAdded(labelOf(copy.people.roleNames, row.role))
        : words.scopeRemoved(labelOf(copy.people.roleNames, row.role)),
    ),
    ...(preview.idle_timeout_s.before !== preview.idle_timeout_s.after
      ? [
          words.idle(
            copy.management.minutes(preview.idle_timeout_s.before),
            copy.management.minutes(preview.idle_timeout_s.after),
          ),
        ]
      : []),
    ...(preview.erp_profiles.before.join() !== preview.erp_profiles.after.join()
      ? [
          words.erp(
            preview.erp_profiles.before.join(", ") || copy.management.erp.none,
            preview.erp_profiles.after.join(", ") || copy.management.erp.none,
          ),
        ]
      : []),
  ];
  return (
    <>
      {preview.blocked ? (
        <Alert variant="error" title={words.conflict}>
          {preview.conflicts.map((conflict) => (
            <p key={conflict.roles.join("-")}>{conflict.text}</p>
          ))}
        </Alert>
      ) : null}
      {preview.holds_already ? <p className="m-0">{words.holdsAlready}</p> : null}
      <p className="m-0">
        <strong>{words.gains}:</strong> {preview.gains.length ? count(preview.gains) : words.nothing}
      </p>
      <p className="m-0">
        <strong>{words.losses}:</strong> {preview.losses.length ? count(preview.losses) : words.nothing}
      </p>
      {changes.length ? (
        <ul className="m-0 flex list-disc flex-col gap-1 pl-5">
          {changes.map((change) => (
            <li key={change}>{change}</li>
          ))}
        </ul>
      ) : null}
      {preview.needs_approval ? (
        <p className="m-0">
          {words.approval} <span className="text-muted-foreground">{preview.rule}</span>
        </p>
      ) : null}
      {preview.passkey_needed ? <p className="m-0">{words.passkey}</p> : null}
    </>
  );
}
