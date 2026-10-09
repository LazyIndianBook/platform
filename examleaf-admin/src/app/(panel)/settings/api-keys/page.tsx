// /settings/api-keys/: keys for integrations (GET api-keys/): who answers for each, its permissions, when it ends and
// when it was last used, from where; making one (its whole key shown once) and revoking one (OWNER's).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { NewKey, RevokeKey } from "@/components/modules/settings/api-keys";
import { PageHeader, Section } from "@/components/shell/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { type ApiKey, listApiKeys } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatDate, formatDateTime, toLocalInput } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.apiKeys.title };

function statusOf(key: ApiKey, now: number): "active" | "revoked" | "expired" {
  if (key.revoked_at) return "revoked";
  if (key.expires_at && Date.parse(key.expires_at) <= now) return "expired";
  return "active";
}

const scopesOf = (key: ApiKey) => (Array.isArray(key.scopes) ? key.scopes.map(String) : []);

export default async function ApiKeysPage() {
  const { manifest, transport, path } = await staffPage("/settings/api-keys/");
  const keys = await attempt(listApiKeys(transport), path);
  const now = requestTime();
  const managing = has(manifest, P.apiKeysManage);
  return (
    <>
      <PageHeader
        title={copy.apiKeys.title}
        lead={copy.apiKeys.lead}
        back={{ href: "/settings/", label: copy.settings.title }}
      />
      <div className="flex flex-col gap-10">
        {keys instanceof ApiError ? (
          <Problem error={keys} />
        ) : keys.results.length === 0 ? (
          <EmptyState title={copy.apiKeys.emptyTitle}>
            <p>{copy.apiKeys.emptyText}</p>
          </EmptyState>
        ) : (
          <Table caption={copy.apiKeys.title}>
            <thead>
              <tr>
                <TableHead>{copy.apiKeys.columns.name}</TableHead>
                <TableHead>{copy.apiKeys.columns.prefix}</TableHead>
                <TableHead>{copy.apiKeys.columns.scopes}</TableHead>
                <TableHead>{copy.apiKeys.columns.expires}</TableHead>
                <TableHead>{copy.apiKeys.columns.lastUsed}</TableHead>
                <TableHead>{copy.apiKeys.columns.sponsor}</TableHead>
                <TableHead>{copy.apiKeys.columns.status}</TableHead>
                {managing ? <TableHead>{copy.common.actions}</TableHead> : null}
              </tr>
            </thead>
            <tbody>
              {keys.results.map((key) => {
                const status = statusOf(key, now);
                return (
                  <tr key={key.id}>
                    <TableCell className="font-semibold">{key.name}</TableCell>
                    <TableCell>
                      <code>{key.prefix}…</code>
                    </TableCell>
                    <TableCell>
                      <code className="text-[13px] break-all">{scopesOf(key).join(", ")}</code>
                    </TableCell>
                    <TableCell>{key.expires_at ? formatDate(key.expires_at) : copy.common.none}</TableCell>
                    <TableCell>
                      {formatDateTime(key.last_used_at)}
                      {key.last_used_ip ? (
                        <span className="block font-mono text-xs text-muted-foreground">
                          {copy.apiKeys.lastUsedFrom(key.last_used_ip)}
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell>{staffLabel(key.sponsor, manifest.user.id)}</TableCell>
                    <TableCell>
                      <StatusChip tone={status === "active" ? "good" : "stopped"}>
                        {labelOf(copy.apiKeys.statuses, status)}
                      </StatusChip>
                    </TableCell>
                    {managing ? <TableCell>{status === "active" ? <RevokeKey apiKey={key} /> : null}</TableCell> : null}
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
        {managing ? (
          <Section id="new" title={copy.apiKeys.createTitle} lead={copy.apiKeys.createText}>
            <NewKey latest={toLocalInput(now + 365 * 86_400_000).slice(0, 10)} />
          </Section>
        ) : null}
      </div>
    </>
  );
}
