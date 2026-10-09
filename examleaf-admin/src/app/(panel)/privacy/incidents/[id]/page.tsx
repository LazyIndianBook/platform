// /privacy/incidents/<id>/: one incident (GET incidents/{id}/): what is known, its two clocks, what was done, and the
// form that keeps it up (PATCH incidents/{id}/); its audit events beside.
import type { Metadata } from "next";

import { EventTimeline } from "@/components/data/event-timeline";
import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { IncidentClock, IncidentUpdateForm } from "@/components/modules/privacy/incidents";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { getIncident, listAudit } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, formatNumber } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.privacy.incidentsTitle };

export default async function IncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/privacy/incidents/${encodeURIComponent(id)}/`);
  const [incident, events] = await Promise.all([
    attempt(getIncident(id, transport), path, "404"),
    attempt(listAudit({ target_type: "incident", target_id: id }, transport), path),
  ]);
  const back = { href: "/privacy/incidents/", label: copy.privacy.incidentsTitle };
  if (incident instanceof ApiError) {
    return (
      <RecordPage title={copy.privacy.incidentsTitle} back={back}>
        <Problem error={incident} />
      </RecordPage>
    );
  }
  const now = requestTime();
  return (
    <RecordPage
      eyebrow={copy.privacy.incidentsTitle}
      title={`${labelOf(copy.privacy.incidentTypes, incident.type)} · ${incident.id}`}
      back={back}
      status={<StatusChip tone={toneOf(incident.state)}>{labelOf(copy.privacy.states, incident.state)}</StatusChip>}
      timelineLabel={copy.audit.title}
      timeline={
        events instanceof ApiError ? (
          <Problem error={events} />
        ) : (
          <EventTimeline events={events.results} label={copy.audit.title} />
        )
      }
    >
      <Facts
        items={[
          { label: copy.privacy.detectedAt, value: formatDateTime(incident.detected_at) },
          { label: copy.privacy.systems, value: incident.systems.join(", ") || copy.common.none },
          { label: copy.privacy.dataCategories, value: incident.data_categories.join(", ") || copy.common.none },
          { label: copy.privacy.peopleAffected, value: formatNumber(incident.people_affected) },
          {
            label: copy.privacy.childrenAffected,
            value: incident.children_affected ? copy.common.yes : copy.common.no,
          },
          {
            label: copy.privacy.incidentColumns.certin,
            value: <IncidentClock incident={incident} which="certin" now={now} />,
          },
          {
            label: copy.privacy.incidentColumns.board,
            value: <IncidentClock incident={incident} which="board" now={now} />,
          },
          { label: copy.privacy.noticesSent, value: formatNumber(incident.notices_sent) },
        ]}
      />
      <Section id="done" title={copy.privacy.incidentActions}>
        {incident.actions.length ? (
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
            {incident.actions.map((action, index) => (
              <li key={`${action.at}-${index}`}>
                {action.at ? (
                  <span className="font-mono text-sm text-muted-foreground">{formatDateTime(action.at)} · </span>
                ) : null}
                {action.text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.privacy.noActions}</p>
        )}
      </Section>
      {has(manifest, P.incidentsChange) ? (
        <Section id="update" title={copy.privacy.saveIncident}>
          <IncidentUpdateForm incident={incident} />
        </Section>
      ) : null}
    </RecordPage>
  );
}
