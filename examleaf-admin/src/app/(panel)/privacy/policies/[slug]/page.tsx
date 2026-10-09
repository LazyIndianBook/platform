// /privacy/policies/<slug>/: one legal page (GET privacy/policies/{slug}/): the version in force and its day, a version
// waiting for its day (cancel it, with a reason), every version newest first, a version's changes against the one
// before (?diff=N: GET versions/{N}/diff/), and publishing a new one for whoever may change pages. Its notes and audit
// events (pages.page) beside.
import { cn } from "cn";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { CancelScheduled, PublishPolicy } from "@/components/modules/privacy/policies";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { getPolicy, type PolicyDiff, policyDiff, type PolicySlug } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatDate, formatDateTime, toLocalInput } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.legal.policiesTitle };

const SLUGS: readonly PolicySlug[] = ["privacy", "terms", "refunds", "shipping", "contact"];

function DiffLines({ diff }: { diff: PolicyDiff }) {
  if (!diff.lines.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.legal.noChanges}</p>;
  return (
    <div className="border border-border bg-card py-2 font-mono text-[13px] leading-relaxed">
      {diff.lines.map((line, index) => (
        <div
          key={index}
          className={cn(
            "flex gap-2 px-3 break-words whitespace-pre-wrap",
            line.kind === "added" && "bg-success-bg",
            line.kind === "removed" && "bg-error-bg",
            line.kind === "hunk" && "mt-2 bg-secondary text-muted-foreground first:mt-0",
          )}
        >
          <span aria-hidden="true" className="w-3 shrink-0 select-none">
            {line.kind === "added" ? "+" : line.kind === "removed" ? "−" : ""}
          </span>
          <span className="min-w-0">
            {line.kind === "added" || line.kind === "removed" ? (
              <span className="sr-only">{copy.legal[line.kind]} </span>
            ) : null}
            {line.text || " "}
          </span>
        </div>
      ))}
    </div>
  );
}

export default async function PolicyPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { slug: given } = await params;
  const search = await searchParams;
  const slug = SLUGS.find((each) => each === given) ?? notFound();
  const { manifest, transport, path } = await staffPage(pathOf(`/privacy/policies/${slug}/`, search));
  const number = /^\d+$/.test(param(search, "diff")) ? Number(param(search, "diff")) : null;
  const [policy, diff] = await Promise.all([
    attempt(getPolicy(slug, transport), path, "404"),
    number ? attempt(policyDiff(slug, number, transport), path) : null,
  ]);
  const back = { href: "/privacy/policies/", label: copy.legal.policiesTitle };
  if (policy instanceof ApiError)
    return (
      <RecordPage title={copy.legal.policiesTitle} back={back}>
        <Problem error={policy} />
      </RecordPage>
    );
  const me = manifest.user.id;
  return (
    <RecordPage
      eyebrow={copy.legal.policiesTitle}
      title={policy.title}
      back={back}
      status={<StatusChip tone="good">{copy.legal.policyVersion(policy.number)}</StatusChip>}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "pages.page", target_id: String(policy.id) },
        note: { type: "pages.page", id: String(policy.id) },
      })}
    >
      <Facts
        items={[
          {
            label: copy.legal.inForceFacts,
            value: copy.legal.policyFrom(policy.number, formatDate(policy.effective_from)),
          },
          { label: copy.legal.policyColumns.summary, value: policy.summary || copy.common.none },
          { label: copy.legal.updated, value: formatDateTime(policy.updated) },
          ...(policy.placeholders
            ? [{ label: copy.legal.policyColumns.fill, value: copy.legal.placeholders(policy.placeholders) }]
            : []),
        ]}
      />
      {policy.scheduled ? (
        <Section id="scheduled" title={copy.legal.policyColumns.scheduled}>
          <p className="m-0 text-[15px]">
            <strong>
              {copy.legal.scheduledLine(policy.scheduled.number, formatDate(policy.scheduled.effective_from))}
            </strong>{" "}
            {policy.scheduled.summary}
          </p>
          <div>
            <CancelScheduled slug={slug} />
          </div>
        </Section>
      ) : null}
      <Section id="versions" title={copy.legal.versions} lead={copy.legal.versionsLead}>
        <ol className="m-0 flex list-none flex-col gap-3 p-0">
          {policy.versions.map((version) => (
            <li key={version.number} className="flex flex-col gap-0.5 border-t border-border pt-3 text-[15px]">
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <strong>{copy.legal.policyVersion(version.number)}</strong>
                <span className="text-muted-foreground">
                  {version.upcoming
                    ? copy.legal.versionUpcoming(formatDate(version.effective_from))
                    : copy.legal.versionLine(formatDate(version.effective_from))}
                </span>
                {version.in_force ? <StatusChip tone="good">{copy.legal.inForce}</StatusChip> : null}
              </span>
              {version.summary ? <span>{version.summary}</span> : null}
              {version.published_at ? (
                <span className="text-sm text-muted-foreground">
                  {copy.legal.versionPublished(
                    formatDateTime(version.published_at),
                    staffLabel(version.published_by, me),
                  )}
                </span>
              ) : null}
              <Link
                href={`/privacy/policies/${slug}/?diff=${version.number}#changes`}
                className="inline-flex min-h-11 items-center self-start"
                aria-current={number === version.number ? "true" : undefined}
              >
                {copy.legal.showChanges}
                <span className="sr-only"> ({copy.legal.policyVersion(version.number)})</span>
              </Link>
            </li>
          ))}
        </ol>
      </Section>
      {diff ? (
        diff instanceof ApiError ? (
          <Section id="changes" title={copy.legal.showChanges}>
            <Problem error={diff} />
          </Section>
        ) : (
          <Section
            id="changes"
            title={copy.legal.changes(diff.number, diff.previous)}
            lead={`${copy.legal.changesCount(diff.added, diff.removed)}${diff.title_changed ? ` ${copy.legal.titleChanged}` : ""}`}
          >
            <DiffLines diff={diff} />
          </Section>
        )
      ) : null}
      {has(manifest, P.policiesPublish) ? (
        <Section id="publish" title={copy.legal.publish} lead={copy.legal.publishLead}>
          <PublishPolicy policy={policy} today={toLocalInput(requestTime()).slice(0, 10)} />
        </Section>
      ) : null}
    </RecordPage>
  );
}
