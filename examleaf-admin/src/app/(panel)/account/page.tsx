// /account/: the person's own account: who they are, their roles and limits (the manifest), their background jobs
// (GET jobs/?mine=1: exports and bulk actions, with progress, cancel and the file), every browser and app signed in to
// their account (allauth.usersessions, the website's sessions too: one account), Sign out everywhere, and the way to
// their two-step sign-in and passkeys, which live on the website's account page.
import type { Metadata } from "next";

import { JobProgress } from "@/components/data/job-progress";
import { Problem } from "@/components/data/problem";
import { Facts } from "@/components/data/record-page";
import { StatusChip } from "@/components/data/status-chip";
import { Sessions } from "@/components/modules/account/sessions";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { allauthGet } from "@/lib/api/server";
import { listJobs, rolesOf } from "@/lib/api/staff";
import type { Session } from "@/lib/auth/headless";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";
import { WEBSITE_URL } from "@/lib/site";

export const metadata: Metadata = { title: copy.account.title };

export default async function AccountPage() {
  const { manifest, transport, path } = await staffPage("/account/");
  const [sessions, jobs] = await Promise.all([
    allauthGet<Session[]>("/auth/sessions"),
    has(manifest, P.jobsView) ? attempt(listJobs({ mine: true }, transport), path) : null,
  ]);
  const roles = rolesOf(manifest);
  return (
    <>
      <PageHeader title={copy.account.title} lead={copy.account.lead} />
      <div className="flex max-w-[52rem] flex-col gap-10">
        <Section id="you" title={copy.account.you}>
          <Facts
            items={[
              { label: copy.auth.email, value: manifest.user.email },
              ...(manifest.user.full_name ? [{ label: copy.people.columns.name, value: manifest.user.full_name }] : []),
              {
                label: copy.account.roles,
                value:
                  roles
                    .map((role) =>
                      role.expires_at
                        ? `${labelOf(copy.people.roleNames, role.name)} (${copy.account.roleUntil(formatDate(role.expires_at))})`
                        : labelOf(copy.people.roleNames, role.name),
                    )
                    .join(", ") || copy.people.noRoles,
              },
            ]}
          />
        </Section>
        <Section id="limits" title={copy.account.limits} lead={copy.account.limitsLead}>
          <Facts
            items={Object.entries(manifest.limits).map(([name, value]) => ({
              label: labelOf(copy.account.limitNames, name),
              value: value === null ? copy.account.noLimit : value.toLocaleString("en-IN"),
            }))}
          />
        </Section>
        {jobs ? (
          <Section id="jobs" title={copy.jobs.title} lead={copy.jobs.lead}>
            {jobs instanceof ApiError ? (
              <Problem error={jobs} />
            ) : jobs.results.length ? (
              <ul className="m-0 flex list-none flex-col gap-6 p-0">
                {jobs.results.map((job) => (
                  <li key={job.id} className="flex flex-col gap-2 border-b border-border pb-5">
                    <p className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1 text-[15px]">
                      <strong>{labelOf(copy.jobs.kinds, job.kind)}</strong>
                      <StatusChip tone={job.state === "failed" ? "bad" : job.state === "done" ? "done" : "moving"}>
                        {labelOf(copy.jobs.states, job.state)}
                      </StatusChip>
                      <span className="text-sm text-muted-foreground">{formatDateTime(job.created)}</span>
                    </p>
                    <JobProgress job={job} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="m-0 text-[15px] text-muted-foreground">{copy.jobs.none}</p>
            )}
          </Section>
        ) : null}
        <Section id="sessions" title={copy.account.sessions} lead={copy.account.sessionsLead}>
          {sessions.data ? (
            <Sessions sessions={sessions.data} />
          ) : (
            <Problem error={new ApiError(sessions.status, "error", copy.account.sessionsFailed)} />
          )}
        </Section>
        <Section id="security" title={copy.account.security} lead={copy.account.securityText}>
          <p className="m-0">
            <a
              href={`${WEBSITE_URL}/account/security/`}
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold"
            >
              {copy.account.securityLink} <span className="sr-only">{copy.common.opensElsewhere}</span>
            </a>
          </p>
        </Section>
      </div>
    </>
  );
}
