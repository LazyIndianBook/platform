"use client";

// The breach register (GET incidents/?kind=&open=): each incident with its two clocks from detection, CERT-In within
// 6 hours (cert_in_due) and the Data Protection Board's detailed report within 72 (board_due), as time left in words
// and by urgency, stopped once reported (cert_in_reported_at, board_report_at). Recording one (POST incidents/) takes
// only what is known at first and tells the owners; on its page the reports' times and references, the notices, what
// was done and the root cause are kept up (PATCH incidents/{id}/), and it is closed (POST incidents/{id}/close/).
import { Clock } from "@/components/data/clock";
import { ConfirmDialog } from "@/components/data/confirm-typed";
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Checkbox } from "@/components/ui/choice";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { closeIncident, createIncident, type Incident, type SavedView, updateIncident } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { incidentState } from "@/lib/display";
import { formatDateTime, formatNumber, fromLocalInput, toLocalInput } from "@/lib/format";

/** One of an incident's two clocks: CERT-In's (6 hours) or the Board's (72 hours), stopped once reported. */
export function IncidentClock({
  incident,
  which,
  now,
  compact = false,
}: {
  incident: Incident;
  which: "certin" | "board";
  now: number;
  compact?: boolean;
}) {
  const certin = which === "certin";
  return (
    <Clock
      label={certin ? copy.privacy.certinClock : copy.privacy.boardClock}
      start={incident.detected_at ?? null}
      due={certin ? incident.cert_in_due : incident.board_due}
      doneAt={certin ? incident.cert_in_reported_at : incident.board_report_at}
      now={now}
      compact={compact}
    />
  );
}

export function IncidentsTable({
  rows,
  next,
  previous,
  views,
  now,
}: {
  rows: Incident[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
  now: number;
}) {
  const columns: Column<Incident>[] = [
    { key: "title", label: copy.privacy.incidentColumns.title, render: (incident) => incident.title },
    {
      key: "detected",
      label: copy.privacy.incidentColumns.detected,
      render: (incident) => formatDateTime(incident.detected_at),
    },
    {
      key: "kind",
      label: copy.privacy.incidentColumns.kind,
      render: (incident) => labelOf(copy.privacy.incidentKinds, incident.kind),
    },
    {
      key: "people",
      label: copy.privacy.incidentColumns.people,
      render: (incident) => (
        <span>
          {formatNumber(incident.people_affected)}
          {incident.children_affected ? (
            <StatusChip tone="moving" className="ml-2">
              {copy.privacy.children}
            </StatusChip>
          ) : null}
        </span>
      ),
    },
    {
      key: "certin",
      label: copy.privacy.incidentColumns.certin,
      render: (incident) => <IncidentClock incident={incident} which="certin" now={now} compact />,
    },
    {
      key: "board",
      label: copy.privacy.incidentColumns.board,
      render: (incident) => <IncidentClock incident={incident} which="board" now={now} compact />,
    },
    {
      key: "state",
      label: copy.privacy.incidentColumns.state,
      render: (incident) => (
        <StatusChip tone={incident.closed_at ? "stopped" : "waiting"}>
          {labelOf(copy.privacy.incidentStates, incidentState(incident))}
        </StatusChip>
      ),
    },
  ];
  return (
    <DataTable
      listKey="incidents"
      caption={copy.privacy.incidentsTitle}
      rows={rows}
      columns={columns}
      rowId={(incident) => String(incident.id)}
      rowHref={(incident) => `/privacy/incidents/${incident.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        {
          name: "open",
          label: copy.privacy.openFilter,
          type: "select",
          options: [
            { value: "true", label: copy.privacy.incidentStates.open },
            { value: "false", label: copy.privacy.incidentStates.closed },
          ],
        },
        {
          name: "kind",
          label: copy.privacy.incidentKind,
          type: "select",
          options: Object.entries(copy.privacy.incidentKinds).map(([value, label]) => ({ value, label })),
        },
      ]}
      empty={{ title: copy.privacy.emptyIncidentsTitle, text: copy.privacy.emptyIncidentsText }}
    />
  );
}

export function NewIncidentForm({ now }: { now: number }) {
  return (
    <ActionForm
      id="new-incident"
      submitLabel={copy.privacy.recordIncident}
      success={copy.privacy.incidentRecorded}
      labels={{
        title: copy.privacy.title,
        detected_at: copy.privacy.detectedAt,
        kind: copy.privacy.incidentKind,
        people_affected: copy.privacy.peopleAffected,
      }}
      onSubmit={(form) => {
        const people = formText(form, "people_affected");
        return createIncident({
          title: formText(form, "title"),
          detected_at: fromLocalInput(formText(form, "detected_at")),
          kind: formText(form, "kind") as Incident["kind"],
          description: formText(form, "description"),
          systems: formText(form, "systems"),
          data_categories: formText(form, "data_categories"),
          people_affected: people ? Number(people) : null,
          children_affected: form.get("children_affected") === "on",
        });
      }}
    >
      {(error) => (
        <>
          <Field id="new-incident-title" label={copy.privacy.title} error={fieldError(error, "title")}>
            <Input name="title" autoComplete="off" aria-required="true" maxLength={200} />
          </Field>
          <FormGrid>
            <Field
              id="new-incident-detected_at"
              label={copy.privacy.detectedAt}
              error={fieldError(error, "detected_at")}
            >
              <Input name="detected_at" type="datetime-local" defaultValue={toLocalInput(now)} aria-required="true" />
            </Field>
            <Field id="new-incident-kind" label={copy.privacy.incidentKind} error={fieldError(error, "kind")}>
              <Select name="kind" defaultValue="" aria-required="true">
                <option value="">{copy.privacy.incidentKind}</option>
                {Object.entries(copy.privacy.incidentKinds).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              id="new-incident-people_affected"
              label={copy.privacy.peopleAffected}
              optional
              error={fieldError(error, "people_affected")}
            >
              <Input name="people_affected" type="number" min={0} inputMode="numeric" />
            </Field>
          </FormGrid>
          <Field id="new-incident-description" label={copy.privacy.description} optional>
            <Textarea name="description" rows={3} />
          </Field>
          <FormGrid>
            <Field id="new-incident-systems" label={copy.privacy.systems} optional help={copy.privacy.systemsHelp}>
              <Input name="systems" autoComplete="off" />
            </Field>
            <Field
              id="new-incident-data_categories"
              label={copy.privacy.dataCategories}
              optional
              help={copy.privacy.dataCategoriesHelp}
            >
              <Input name="data_categories" autoComplete="off" />
            </Field>
          </FormGrid>
          <Checkbox name="children_affected">{copy.privacy.childrenAffected}</Checkbox>
        </>
      )}
    </ActionForm>
  );
}

/** A datetime-local value of the API's time (empty for none). */
const local = (value: string | null | undefined) => (value ? toLocalInput(value) : "");
/** The API's time from a datetime-local value (null for none). */
const moment = (value: string) => (value ? fromLocalInput(value) : null);

export function IncidentUpdateForm({ incident }: { incident: Incident }) {
  const id = `incident-${incident.id}`;
  const field = (name: string, label: string, value: string | null | undefined, type = "datetime-local") => (
    <Field id={`${id}-${name}`} label={label} optional>
      <Input name={name} type={type} defaultValue={type === "datetime-local" ? local(value) : (value ?? "")} />
    </Field>
  );
  return (
    <ActionForm
      id={id}
      submitLabel={copy.privacy.saveIncident}
      success={copy.privacy.incidentSaved}
      labels={{
        cert_in_reported_at: copy.privacy.certinReportedAt,
        board_notified_at: copy.privacy.boardNotifiedAt,
        board_report_at: copy.privacy.boardReportAt,
        notices_sent: copy.privacy.noticesSent,
      }}
      onSubmit={(form) =>
        updateIncident(incident.id, {
          cert_in_reported_at: moment(formText(form, "cert_in_reported_at")),
          cert_in_reference: formText(form, "cert_in_reference"),
          board_notified_at: moment(formText(form, "board_notified_at")),
          board_report_at: moment(formText(form, "board_report_at")),
          board_reference: formText(form, "board_reference"),
          notices_sent: Number(formText(form, "notices_sent") || 0),
          notices_sent_at: moment(formText(form, "notices_sent_at")),
          actions: formText(form, "actions"),
          root_cause: formText(form, "root_cause"),
        })
      }
    >
      {() => (
        <>
          <FormGrid>
            {field("cert_in_reported_at", copy.privacy.certinReportedAt, incident.cert_in_reported_at)}
            {field("cert_in_reference", copy.privacy.certinReference, incident.cert_in_reference, "text")}
          </FormGrid>
          <FormGrid>
            {field("board_notified_at", copy.privacy.boardNotifiedAt, incident.board_notified_at)}
            {field("board_report_at", copy.privacy.boardReportAt, incident.board_report_at)}
            {field("board_reference", copy.privacy.boardReference, incident.board_reference, "text")}
          </FormGrid>
          <FormGrid>
            <Field id={`${id}-notices_sent`} label={copy.privacy.noticesSent}>
              <Input
                name="notices_sent"
                type="number"
                min={0}
                inputMode="numeric"
                defaultValue={incident.notices_sent ?? 0}
              />
            </Field>
            {field("notices_sent_at", copy.privacy.noticesSentAt, incident.notices_sent_at)}
          </FormGrid>
          <Field id={`${id}-actions`} label={copy.privacy.incidentActions} optional>
            <Textarea name="actions" rows={4} defaultValue={incident.actions ?? ""} />
          </Field>
          <Field id={`${id}-root_cause`} label={copy.privacy.rootCause} optional>
            <Textarea name="root_cause" rows={2} defaultValue={incident.root_cause ?? ""} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

export function CloseIncident({ incident }: { incident: Incident }) {
  if (incident.closed_at) return null;
  return (
    <ConfirmDialog
      triggerLabel={copy.privacy.closeIncident}
      title={copy.privacy.closeIncident}
      text={copy.privacy.closeIncidentText}
      confirmLabel={copy.privacy.closeIncident}
      confirmVariant="primary"
      success={copy.privacy.incidentClosed}
      onConfirm={() => closeIncident(incident.id)}
    />
  );
}
