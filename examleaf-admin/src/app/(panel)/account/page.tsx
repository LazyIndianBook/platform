// /account/: the person's own account: who they are and their roles (the manifest), every browser and app signed in
// to their account (allauth.usersessions, the website's sessions too: one account), Sign out everywhere, and the way
// to their two-step sign-in and passkeys, which live on the website's account page.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts } from "@/components/data/record-page";
import { Sessions } from "@/components/modules/account/sessions";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { staffPage } from "@/lib/api/page";
import { allauthGet } from "@/lib/api/server";
import type { Session } from "@/lib/auth/headless";
import { copy, labelOf } from "@/lib/copy";
import { formatDate } from "@/lib/format";
import { WEBSITE_URL } from "@/lib/site";

export const metadata: Metadata = { title: copy.account.title };

export default async function AccountPage() {
  const { manifest } = await staffPage("/account/");
  const sessions = await allauthGet<Session[]>("/auth/sessions");
  return (
    <>
      <PageHeader title={copy.account.title} lead={copy.account.lead} />
      <div className="flex max-w-[52rem] flex-col gap-10">
        <Section id="you" title={copy.account.you}>
          <Facts
            items={[
              { label: copy.auth.email, value: manifest.user.email },
              ...(manifest.user.name ? [{ label: copy.people.columns.name, value: manifest.user.name }] : []),
              {
                label: copy.account.roles,
                value:
                  manifest.roles
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
