"use client";

// A record's notes (GET/POST notes/?target_type=&target_id=): what colleagues said and promised, newest first, each
// with its author (by id: the API names no one) and time; adding one for whoever may. Notes are personal data too.
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { useCan, useManifest } from "@/components/shell/manifest";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { addNote, type Note } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

export type NoteTarget = { type: string; id: string };

export function Notes({ target, notes }: { target: NoteTarget; notes: Note[] }) {
  const manifest = useManifest();
  const can = useCan();
  const id = `note-${target.type.replace(/\W/g, "-")}-${target.id}`;
  return (
    <div className="flex flex-col gap-4">
      {notes.length ? (
        <ol className="m-0 flex list-none flex-col gap-3 p-0">
          {notes.map((note) => (
            <li key={note.id} className="flex flex-col gap-0.5 border-l-2 border-border pl-3 text-[15px]">
              <span className="whitespace-pre-wrap">{note.body}</span>
              <span className="text-sm text-muted-foreground">
                {copy.notes.by(staffLabel(note.author, manifest.user.id), formatDateTime(note.created))}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="m-0 text-[15px] text-muted-foreground">{copy.notes.none}</p>
      )}
      {can(P.notesAdd) ? (
        <ActionForm
          id={id}
          submitLabel={copy.notes.save}
          success={copy.notes.saved}
          variant="secondary"
          labels={{ body: copy.notes.body }}
          className="flex flex-col gap-3"
          onSubmit={(form) => addNote(target, formText(form, "body"))}
        >
          {(error) => (
            <Field id={`${id}-body`} label={copy.notes.add} error={fieldError(error, "body")}>
              <Textarea name="body" rows={3} aria-required="true" />
            </Field>
          )}
        </ActionForm>
      ) : null}
    </div>
  );
}
