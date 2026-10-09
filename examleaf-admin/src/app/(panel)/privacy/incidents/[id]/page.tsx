// /privacy/incidents/<id>/: one incident (GET incidents/{id}/): what is known, its two clocks, what was done, the form
// that keeps it up (PATCH incidents/{id}/) and closing it; its notes and audit events beside.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { CloseIncident, IncidentClock, IncidentUpdateForm } from "@/components/modules/privacy/incidents";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, requestTime, staffPage } from "@/lib/api/page";
import { getIncident } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { incidentState } from "@/lib/display";
import { formatDateTime, formatNumber } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.privacy.incidentsTitle };

export default async function IncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/privacy/incidents/${encodeURIComponent(id)}/`);
  const incident = await attempt(getIncident(recordId(id), transport), path, "404");
  const back = { href: "/privacy/incidents/", label: copy.privacy.incidentsTitle };
  if (incident instanceof ApiError) {
    return (
      <RecordPage title={copy.privacy.incidentsTitle} back={back}>
        <Problem error={incident} />
      </RecordPage>
    );
  }
  const now = requestTime();
  const managing = has(manifest, P.incidentsManage);
  const text = (value: string | undefined) => value || copy.common.none;
  return (
    <RecordPage
      eyebrow={`${labelOf(copy.privacy.incidentKinds, incident.kind)} · ${incident.id}`}
      title={incident.title}
      back={back}
      status={
        <StatusChip tone={incident.closed_at ? "stopped" : "waiting"}>
          {labelOf(copy.privacy.incidentStates, incidentState(incident))}
        </StatusChip>
      }
      actions={managing ? <CloseIncident incident={incident} /> : null}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "staff.incident", target_id: String(incident.id) },
        note: { type: "staff.incident", id: String(incident.id) },
      })}
    >
      <Facts
        items={[
          { label: copy.privacy.detectedAt, value: formatDateTime(incident.detected_at) },
          {
            label: copy.privacy.description,
            value: <span className="whitespace-pre-wrap">{text(incident.description)}</span>,
          },
          { label: copy.privacy.systems, value: text(incident.systems) },
          { label: copy.privacy.dataCategories, value: text(incident.data_categories) },
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
          { label: copy.privacy.noticesSent, value: formatNumber(incident.notices_sent ?? 0) },
          ...(incident.closed_at
            ? [{ label: copy.privacy.incidentClosed, value: formatDateTime(incident.closed_at) }]
            : []),
        ]}
      />
      <Section id="done" title={copy.privacy.incidentActions}>
        <p className="m-0 text-[15px] whitespace-pre-wrap">{text(incident.actions)}</p>
        {incident.root_cause ? (
          <p className="m-0 text-[15px]">
            <strong>{copy.privacy.rootCause}:</strong> {incident.root_cause}
          </p>
        ) : null}
      </Section>
      {managing && !incident.closed_at ? (
        <Section id="update" title={copy.privacy.saveIncident}>
          <IncidentUpdateForm incident={incident} />
        </Section>
      ) : null}
    </RecordPage>
  );
}
