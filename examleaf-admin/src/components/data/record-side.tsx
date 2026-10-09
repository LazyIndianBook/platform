// Beside a record (a server component): its audit events (GET audit/ filtered to it: only for whoever reads the log,
// AUDITOR and OWNER, since every refused call is itself an audit event) and its notes (GET notes/, whoever may).
import { EventTimeline } from "@/components/data/event-timeline";
import { Notes, type NoteTarget } from "@/components/data/notes";
import { Problem } from "@/components/data/problem";
import { ApiError } from "@/lib/api/errors";
import { attempt } from "@/lib/api/page";
import { type AuditFilters, listAudit, listNotes, type Manifest, type Transport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, hasAny, P } from "@/lib/modules";

type RecordSideProps = {
  manifest: Manifest;
  transport: Transport;
  path: string;
  /** The audit log's filters for this record. */
  audit: AuditFilters;
  note: NoteTarget;
};

/** The side of a record page, or nothing for whoever may read neither the log nor the notes. */
export function recordSide(props: RecordSideProps) {
  return hasAny(props.manifest, [P.auditView, P.notesView]) ? <RecordSide {...props} /> : undefined;
}

async function RecordSide({ manifest, transport, path, audit, note }: RecordSideProps) {
  const [events, notes] = await Promise.all([
    has(manifest, P.auditView) ? attempt(listAudit(audit, transport), path) : null,
    has(manifest, P.notesView) ? attempt(listNotes(note, transport), path) : null,
  ]);
  if (!events && !notes) return null;
  return (
    <div className="flex flex-col gap-8">
      {notes ? (
        <section aria-labelledby="side-notes-title" className="flex flex-col gap-3">
          <h2 id="side-notes-title" className="m-0 font-head text-xl leading-tight">
            {copy.notes.title}
          </h2>
          <p className="m-0 text-sm text-muted-foreground">{copy.notes.lead}</p>
          {notes instanceof ApiError ? <Problem error={notes} /> : <Notes target={note} notes={notes} />}
        </section>
      ) : null}
      {events ? (
        <section aria-labelledby="side-trail-title" className="flex flex-col gap-3">
          <h2 id="side-trail-title" className="m-0 font-head text-xl leading-tight">
            {copy.audit.title}
          </h2>
          {events instanceof ApiError ? (
            <Problem error={events} />
          ) : (
            <EventTimeline events={events.results} label={copy.audit.title} />
          )}
        </section>
      ) : null}
    </div>
  );
}
