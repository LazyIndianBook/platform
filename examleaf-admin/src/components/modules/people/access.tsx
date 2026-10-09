// What a role and a person may do (the backend's research 1.8), drawn from the staff API as it answers: the role
// catalogue (people/roles/: what each role is for and can't do, its capabilities by area with their risk, its limits,
// scopes, conflicts and ERPNext profiles, its members), a person's Access tab (people/<id>/access/: where each role
// comes from and until when, scopes and limits, their second factors, the open requests about them or by them, every
// permission by area with the last use of the risky ones) and the ERPNext user they should have (people/<id>/erp/).
// Server components: nothing here acts, the actions are on the Overview tab.
import Link from "next/link";

import { Facts } from "@/components/data/record-page";
import { StatusChip, type Tone } from "@/components/data/status-chip";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import type { Access, CapabilityArea, ErpMirror, RoleCatalogueRow } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatAgo, formatDate, formatDateTime } from "@/lib/format";

const words = copy.management;
const RISK_TONE: Record<string, Tone> = { low: "stopped", medium: "waiting", high: "moving", critical: "bad" };

export function RiskChip({ risk }: { risk: string }) {
  return <StatusChip tone={RISK_TONE[risk] ?? "stopped"}>{labelOf(words.risks, risk)}</StatusChip>;
}

/** A limit in words: no limit, or its number. */
export const limitText = (value: number | null | undefined) =>
  value === null || value === undefined ? copy.account.noLimit : value.toLocaleString("en-IN");

/** Each area's permissions, folded: its label, its risk, what the risk triggers, and (the Access tab) when it was
 *  last used. */
export function CapabilityList({
  areas,
  now,
  lastUsed = false,
}: {
  areas: CapabilityArea[];
  now: number;
  lastUsed?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      {areas.map((area) => (
        <details key={area.area} className="border-b border-border pb-2">
          <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-3 font-semibold [&::-webkit-details-marker]:hidden">
            <span>{area.area}</span>
            <span className="text-sm font-normal text-muted-foreground">
              {words.roles.permissions(area.permissions.length)}
            </span>
          </summary>
          <ul className="m-0 flex list-none flex-col gap-2 p-0 pt-1">
            {area.permissions.map((row) => (
              <li key={row.perm} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-[15px]">
                <span className="flex min-w-0 flex-col">
                  <span>{row.label}</span>
                  <span className="text-sm text-muted-foreground">
                    <code className="break-all">{row.perm}</code>
                    {[row.reauth ? words.reauth : "", row.approval ? words.approval : "", row.alert ? words.alert : ""]
                      .filter(Boolean)
                      .map((text) => ` · ${text}`)
                      .join("")}
                    {lastUsed && row.reauth
                      ? ` · ${row.last_used ? words.access.lastUsed(formatAgo(row.last_used, now)) : words.access.notUsed}`
                      : ""}
                  </span>
                </span>
                <RiskChip risk={row.risk} />
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}

export function RoleCatalogueCard({ row, now }: { row: RoleCatalogueRow; now: number }) {
  const name = labelOf(copy.people.roleNames, row.name);
  const scopes = Object.entries(row.scopes ?? {});
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {name}
          <span className="text-sm font-normal text-muted-foreground">{words.roles.members(row.members)}</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-[15px]">
          <strong>{words.roles.for}</strong> {row.card.for}.
        </p>
        <p className="text-[15px]">
          <strong>{words.roles.cannot}</strong> {row.card.cannot}.
        </p>
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
          {row.privileged ? (
            <li>
              <StatusChip tone="waiting">{words.roles.privileged}</StatusChip>
            </li>
          ) : null}
          {row.passkey ? (
            <li>
              <StatusChip tone="moving">{words.roles.passkey}</StatusChip>
            </li>
          ) : null}
          {row.admin_site ? (
            <li>
              <StatusChip tone="stopped">{words.roles.adminSite}</StatusChip>
            </li>
          ) : null}
        </ul>
        <Facts
          items={[
            { label: words.access.idle, value: words.minutes(row.idle_timeout_s) },
            {
              label: words.roles.limits,
              value: Object.entries(row.limits)
                .map(([limit, value]) => `${labelOf(copy.account.limitNames, limit)}: ${limitText(value)}`)
                .join("; "),
            },
            {
              label: words.roles.scopes,
              value: scopes.length
                ? scopes
                    .map(([kind, values]) => `${labelOf(copy.people.scopeKinds, kind)}: ${values.join(", ")}`)
                    .join("; ")
                : words.roles.noScopes,
            },
            {
              label: words.roles.conflicts,
              value: row.conflicts.length
                ? row.conflicts.map((role) => labelOf(copy.people.roleNames, role)).join(", ")
                : words.roles.noConflicts,
            },
            {
              label: words.roles.erpProfiles,
              value: row.erp_profiles.length ? row.erp_profiles.join(", ") : words.roles.noErp,
            },
          ]}
        />
        <CapabilityList areas={row.capabilities} now={now} />
      </CardContent>
    </Card>
  );
}

export function AccessView({ access, me, now }: { access: Access; me: number; now: number }) {
  const scopes = Object.entries(access.role_scopes ?? {});
  return (
    <div className="flex flex-col gap-8">
      {access.passkey_required ? <Alert variant="warning" title={words.access.passkeyDue} /> : null}
      <section aria-labelledby="access-roles" className="flex flex-col gap-3">
        <h2 id="access-roles" className="m-0 font-head text-xl">
          {words.access.roles}
        </h2>
        {access.roles.length ? (
          <Table caption={copy.table.region(words.access.roles)}>
            <thead>
              <tr>
                <TableHead>{copy.people.role}</TableHead>
                <TableHead>{copy.common.details}</TableHead>
                <TableHead>{copy.common.reason}</TableHead>
              </tr>
            </thead>
            <tbody>
              {access.roles.map((role) => (
                <tr key={role.name}>
                  <TableCell>
                    <strong>{labelOf(copy.people.roleNames, role.name)}</strong>
                  </TableCell>
                  <TableCell>
                    {[
                      labelOf(words.access.source, role.source),
                      role.granted_by ? words.access.grantedBy(staffLabel(role.granted_by, me)) : "",
                      role.granted_at ? words.access.since(formatDate(role.granted_at)) : "",
                      role.expires_at ? words.access.until(formatDateTime(role.expires_at)) : words.access.noEnd,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </TableCell>
                  <TableCell>{role.reason || "—"}</TableCell>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.people.noRoles}</p>
        )}
      </section>
      <section aria-labelledby="access-limits" className="flex flex-col gap-3">
        <h2 id="access-limits" className="m-0 font-head text-xl">
          {words.access.limits}
        </h2>
        <Facts
          items={[
            ...Object.entries(access.limits).map(([limit, value]) => ({
              label: labelOf(copy.account.limitNames, limit),
              value: limitText(value),
            })),
            { label: words.access.idle, value: words.minutes(access.idle_timeout_s) },
            {
              label: copy.people.scopes,
              value: access.scopes.length
                ? access.scopes
                    .map((scope) => `${labelOf(copy.people.scopeKinds, scope.kind)}: ${scope.value}`)
                    .join("; ")
                : copy.people.noScopes,
            },
            ...(scopes.length
              ? [
                  {
                    label: words.access.roleScopes,
                    value: scopes
                      .map(([role, kinds]) => `${labelOf(copy.people.roleNames, role)}: ${JSON.stringify(kinds)}`)
                      .join("; "),
                  },
                ]
              : []),
            {
              label: words.access.secondFactors,
              value: [
                `${words.access.app}: ${access.second_factors.authenticator_app ? copy.common.yes : copy.common.no}`,
                `${words.access.passkey}: ${access.second_factors.passkey ? copy.common.yes : copy.common.no}`,
                `${words.access.recovery}: ${access.second_factors.recovery_codes ? copy.common.yes : copy.common.no}`,
              ].join(" · "),
            },
            {
              label: words.access.erpProfiles,
              value: access.erp_profiles.length ? access.erp_profiles.join(", ") : words.erp.none,
            },
          ]}
        />
      </section>
      <section aria-labelledby="access-pending" className="flex flex-col gap-3">
        <h2 id="access-pending" className="m-0 font-head text-xl">
          {words.access.pending}
        </h2>
        {access.pending.length ? (
          <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
            {access.pending.map((row) => (
              <li key={row.id}>
                <Link href={`/approvals/${row.id}/`} className="font-semibold">
                  #{row.id} {row.target_label || row.action}
                </Link>{" "}
                <span className="text-sm text-muted-foreground">
                  {[row.about_them ? words.access.pendingAbout : "", row.by_them ? words.access.pendingBy : ""]
                    .filter(Boolean)
                    .join(", ")}{" "}
                  · {labelOf(copy.approvals.states, row.status)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{words.access.noPending}</p>
        )}
      </section>
      <section aria-labelledby="access-capabilities" className="flex flex-col gap-3">
        <h2 id="access-capabilities" className="m-0 font-head text-xl">
          {words.access.capabilities}{" "}
          <span className="text-base font-normal text-muted-foreground">
            ({words.roles.permissions(access.permissions)})
          </span>
        </h2>
        <CapabilityList areas={access.capabilities} now={now} lastUsed />
      </section>
    </div>
  );
}

export function ErpMirrorView({ mirror }: { mirror: ErpMirror }) {
  return (
    <div className="flex flex-col gap-4">
      {!mirror.erp_in_use ? <Alert variant="info" title={words.erp.notInUse} /> : null}
      <Facts
        items={[
          { label: words.erp.email, value: mirror.email },
          { label: words.erp.enabled, value: mirror.enabled ? words.erp.on : words.erp.off },
          {
            label: words.erp.profiles,
            value: mirror.role_profiles.length ? mirror.role_profiles.join(", ") : words.erp.none,
          },
        ]}
      />
      {mirror.by_role.length ? (
        <Table caption={words.erp.byRole}>
          <thead>
            <tr>
              <TableHead>{copy.people.role}</TableHead>
              <TableHead>{words.erp.profiles}</TableHead>
            </tr>
          </thead>
          <tbody>
            {mirror.by_role.map((row) => (
              <tr key={row.role}>
                <TableCell>{labelOf(copy.people.roleNames, row.role)}</TableCell>
                <TableCell>{row.profiles.length ? row.profiles.join(", ") : words.erp.none}</TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : null}
    </div>
  );
}
