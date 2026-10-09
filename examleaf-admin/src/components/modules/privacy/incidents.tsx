"use client";

// The breach register (GET incidents/): each incident with its two clocks from detection, CERT-In within 6 hours and
// the Data Protection Board within 72 (the API's certin_due_at and board_due_at), as time left in words and by
// urgency, stopped once reported. Recording one (POST incidents/) takes only what is known at first; on its page the
// report times, the notices sent, what was done and its state are kept up (PATCH incidents/{id}/, with the version
// read).
import { Clock } from "@/components/data/clock";
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Checkbox } from "@/components/ui/choice";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { createIncident, type Incident, type SavedView, updateIncident } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, formatNumber, fromLocalInput, toLocalInput } from "@/lib/format";

const list = (text: string) =>
  text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

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
      start={incident.detected_at}
      due={certin ? incident.certin_due_at : incident.board_due_at}
      doneAt={certin ? incident.certin_reported_at : incident.board_reported_at}
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
    {
      key: "detected",
      label: copy.privacy.incidentColumns.detected,
      render: (incident) => formatDateTime(incident.detected_at),
    },
    {
      key: "type",
      label: copy.privacy.incidentColumns.type,
      render: (incident) => labelOf(copy.privacy.incidentTypes, incident.type),
    },
    {
      key: "systems",
      label: copy.privacy.incidentColumns.systems,
      render: (incident) => incident.systems.join(", "),
      wrap: true,
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
        <StatusChip tone={toneOf(incident.state)}>{labelOf(copy.privacy.states, incident.state)}</StatusChip>
      ),
    },
  ];
  return (
    <DataTable
      listKey="incidents"
      caption={copy.privacy.incidentsTitle}
      rows={rows}
      columns={columns}
      rowId={(incident) => incident.id}
      rowLabel={(incident) => `${labelOf(copy.privacy.incidentTypes, incident.type)} ${incident.id}`}
      rowHref={(incident) => `/privacy/incidents/${incident.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        {
          name: "state",
          label: copy.privacy.incidentColumns.state,
          type: "select",
          options: ["open", "contained", "closed"].map((state) => ({
            value: state,
            label: copy.privacy.states[state],
          })),
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
      labels={{ detected_at: copy.privacy.detectedAt, type: copy.privacy.incidentType }}
      onSubmit={(form) => {
        const people = formText(form, "people_affected");
        return createIncident({
          detected_at: fromLocalInput(formText(form, "detected_at")),
          type: formText(form, "type"),
          systems: list(formText(form, "systems")),
          data_categories: list(formText(form, "data_categories")),
          people_affected: people ? Number(people) : null,
          children_affected: form.get("children_affected") === "on",
        });
      }}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field
              id="new-incident-detected_at"
              label={copy.privacy.detectedAt}
              error={fieldError(error, "detected_at")}
            >
              <Input name="detected_at" type="datetime-local" defaultValue={toLocalInput(now)} aria-required="true" />
            </Field>
            <Field id="new-incident-type" label={copy.privacy.incidentType} error={fieldError(error, "type")}>
              <Select name="type" defaultValue="" aria-required="true">
                <option value="">{copy.privacy.incidentType}</option>
                {Object.entries(copy.privacy.incidentTypes).map(([value, label]) => (
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

export function IncidentUpdateForm({ incident }: { incident: Incident }) {
  return (
    <ActionForm
      id={`incident-${incident.id}`}
      submitLabel={copy.privacy.saveIncident}
      success={copy.privacy.incidentSaved}
      labels={{
        certin_reported_at: copy.privacy.markCertin,
        board_reported_at: copy.privacy.markBoard,
        notices_sent: copy.privacy.noticesSent,
        state: copy.privacy.incidentState,
      }}
      onSubmit={(form) => {
        const certin = formText(form, "certin_reported_at");
        const board = formText(form, "board_reported_at");
        const action = formText(form, "action");
        return updateIncident(
          incident.id,
          {
            certin_reported_at: certin ? fromLocalInput(certin) : null,
            board_reported_at: board ? fromLocalInput(board) : null,
            notices_sent: Number(formText(form, "notices_sent") || 0),
            state: formText(form, "state"),
            ...(action ? { action } : {}),
          },
          incident.version,
        );
      }}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field
              id={`incident-${incident.id}-certin_reported_at`}
              label={copy.privacy.markCertin}
              optional
              error={fieldError(error, "certin_reported_at")}
            >
              <Input
                name="certin_reported_at"
                type="datetime-local"
                defaultValue={incident.certin_reported_at ? toLocalInput(incident.certin_reported_at) : ""}
              />
            </Field>
            <Field
              id={`incident-${incident.id}-board_reported_at`}
              label={copy.privacy.markBoard}
              optional
              error={fieldError(error, "board_reported_at")}
            >
              <Input
                name="board_reported_at"
                type="datetime-local"
                defaultValue={incident.board_reported_at ? toLocalInput(incident.board_reported_at) : ""}
              />
            </Field>
            <Field
              id={`incident-${incident.id}-notices_sent`}
              label={copy.privacy.noticesSent}
              error={fieldError(error, "notices_sent")}
            >
              <Input
                name="notices_sent"
                type="number"
                min={0}
                inputMode="numeric"
                defaultValue={incident.notices_sent}
              />
            </Field>
            <Field
              id={`incident-${incident.id}-state`}
              label={copy.privacy.incidentState}
              error={fieldError(error, "state")}
            >
              <Select name="state" defaultValue={incident.state}>
                {["open", "contained", "closed"].map((state) => (
                  <option key={state} value={state}>
                    {copy.privacy.states[state]}
                  </option>
                ))}
              </Select>
            </Field>
          </FormGrid>
          <Field id={`incident-${incident.id}-action`} label={copy.privacy.incidentActions} optional>
            <Textarea name="action" rows={3} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}
