"use client";

// The message templates' actions (ops/staff_api.py): add one (ops.add_messagetemplate), change one (what it is for,
// its channel and language stay: ops.change_messagetemplate), and send yourself a test, to your own confirmed number or
// address only (WhatsApp: not before Phase D). The variables are written one a line, "name, type, longest, about";
// the API checks them against DLT's types and the text's {#var#} placeholders, and says what is wrong beside each
// field.
import { useState } from "react";

import { fieldError } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import { ApiError } from "@/lib/api/errors";
import { createTemplate, type MessageTemplate, testTemplate, updateTemplate } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";

import { FormDialog, formValue } from "./form-dialog";

const words = copy.management.templates;
type Variable = NonNullable<MessageTemplate["variables"]>[number];

/** The variables as the form shows them: one a line. */
export const variablesText = (variables: MessageTemplate["variables"]) =>
  (variables ?? [])
    .map((row) => [row.name, row.type, row.max_length, row.about].filter((part) => part !== "").join(", "))
    .join("\n");

/** The form's lines as the API's variables ("var1, alphanumeric, 30, the order number"). */
export function parseVariables(text: string): Variable[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [name = "", type = "", max = "", ...about] = line.split(",").map((part) => part.trim());
      return { name, type: type as Variable["type"], max_length: Number(max) || 0, about: about.join(", ") };
    });
}

function TemplateFields({ template, error, id }: { template?: MessageTemplate; error: ApiError | null; id: string }) {
  const field = (name: string) => `${id}-${name}`;
  const select = (
    name: "channel" | "language" | "category" | "approval_state" | "header_suffix",
    table: Record<string, string>,
    blank = false,
  ) => (
    <Field id={field(name)} label={words.fields[name]} error={fieldError(error, name)} optional={blank}>
      <Select
        name={name}
        defaultValue={String(template?.[name] ?? (blank ? "" : Object.keys(table)[0]))}
        disabled={Boolean(template) && (name === "channel" || name === "language")}
      >
        {blank ? <option value="">{copy.common.none}</option> : null}
        {Object.entries(table).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </Select>
    </Field>
  );
  return (
    <>
      <FormGrid>
        <Field
          id={field("event")}
          label={words.fields.event}
          help={words.help.event}
          error={fieldError(error, "event")}
        >
          <Input
            name="event"
            defaultValue={template?.event ?? ""}
            autoComplete="off"
            readOnly={Boolean(template)}
            aria-required="true"
          />
        </Field>
        {select("channel", words.channels)}
        {select("language", words.languages)}
        {select("category", words.categories)}
        {select("approval_state", words.states)}
      </FormGrid>
      <Field
        id={field("text")}
        label={words.fields.text}
        optional
        help={words.help.text}
        error={fieldError(error, "text")}
      >
        <Textarea name="text" rows={3} defaultValue={template?.text ?? ""} />
      </Field>
      <Field
        id={field("variables")}
        label={words.fields.variables}
        optional
        help={words.help.variables}
        error={fieldError(error, "variables")}
      >
        <Textarea name="variables" rows={3} defaultValue={variablesText(template?.variables)} className="font-mono" />
      </Field>
      <FormGrid>
        <Field id={field("subject")} label={words.fields.subject} optional error={fieldError(error, "subject")}>
          <Input name="subject" defaultValue={template?.subject ?? ""} autoComplete="off" />
        </Field>
        <Field
          id={field("dlt_template_id")}
          label={words.fields.dlt_template_id}
          optional
          error={fieldError(error, "dlt_template_id")}
        >
          <Input
            name="dlt_template_id"
            defaultValue={template?.dlt_template_id ?? ""}
            inputMode="numeric"
            autoComplete="off"
          />
        </Field>
        <Field id={field("pe_id")} label={words.fields.pe_id} optional error={fieldError(error, "pe_id")}>
          <Input name="pe_id" defaultValue={template?.pe_id ?? ""} inputMode="numeric" autoComplete="off" />
        </Field>
        <Field
          id={field("header")}
          label={words.fields.header}
          optional
          help={words.help.header}
          error={fieldError(error, "header")}
        >
          <Input name="header" defaultValue={template?.header ?? ""} autoComplete="off" maxLength={11} />
        </Field>
        {select("header_suffix", words.suffixes, true)}
        <Field
          id={field("msg91_id")}
          label={words.fields.msg91_id}
          optional
          help={words.help.msg91_id}
          error={fieldError(error, "msg91_id")}
        >
          <Input name="msg91_id" defaultValue={template?.msg91_id ?? ""} autoComplete="off" />
        </Field>
        <Field
          id={field("whatsapp_name")}
          label={words.fields.whatsapp_name}
          optional
          error={fieldError(error, "whatsapp_name")}
        >
          <Input name="whatsapp_name" defaultValue={template?.whatsapp_name ?? ""} autoComplete="off" />
        </Field>
        <Field
          id={field("self_certified_on")}
          label={words.fields.self_certified_on}
          optional
          error={fieldError(error, "self_certified_on")}
        >
          <Input name="self_certified_on" type="date" defaultValue={template?.self_certified_on ?? ""} />
        </Field>
      </FormGrid>
      <Field id={field("notes")} label={words.fields.notes} optional error={fieldError(error, "notes")}>
        <Textarea name="notes" rows={2} defaultValue={template?.notes ?? ""} />
      </Field>
    </>
  );
}

/** The form's values as the API's fields; what a template is for (its event, channel and language) is the form's when
 *  it is new, the template's own when it is changed (they stay). */
function bodyOf(form: FormData, template?: MessageTemplate) {
  const value = (name: string) => formValue(form, name);
  return {
    event: template?.event ?? value("event"),
    channel: template?.channel ?? (value("channel") as MessageTemplate["channel"]),
    language: template?.language ?? (value("language") as MessageTemplate["language"]),
    category: value("category") as MessageTemplate["category"],
    approval_state: value("approval_state") as NonNullable<MessageTemplate["approval_state"]>,
    text: value("text"),
    subject: value("subject"),
    variables: parseVariables(value("variables")),
    dlt_template_id: value("dlt_template_id"),
    pe_id: value("pe_id"),
    header: value("header"),
    header_suffix: value("header_suffix") as NonNullable<MessageTemplate["header_suffix"]>,
    msg91_id: value("msg91_id"),
    whatsapp_name: value("whatsapp_name"),
    self_certified_on: value("self_certified_on") || null,
    notes: value("notes"),
  };
}

const LABELS = { ...words.fields } as Record<string, string>;

export function AddTemplate() {
  const can = useCan();
  if (!can(P.templatesAdd)) return null;
  return (
    <FormDialog
      triggerLabel={words.add}
      triggerVariant="primary"
      title={words.add}
      submitLabel={words.addButton}
      success={words.added}
      labels={LABELS}
      onSubmit={(form) => createTemplate(bodyOf(form))}
    >
      {(error, id) => <TemplateFields error={error} id={id} />}
    </FormDialog>
  );
}

export function EditTemplate({ template }: { template: MessageTemplate }) {
  const can = useCan();
  if (!can(P.templatesChange)) return null;
  return (
    <FormDialog
      triggerLabel={
        <>
          {words.edit} <span className="sr-only">{words.editName(template.event)}</span>
        </>
      }
      title={words.editTitle(template.event)}
      submitLabel={words.save}
      success={words.saved}
      labels={LABELS}
      onSubmit={(form) => updateTemplate(template.id, bodyOf(form, template))}
    >
      {(error, id) => <TemplateFields template={template} error={error} id={id} />}
    </FormDialog>
  );
}

export function TestTemplate({ template }: { template: MessageTemplate }) {
  const can = useCan();
  const [said, setSaid] = useState("");
  if (!can(P.templatesChange) || template.channel === "whatsapp") return null;
  const variables = template.variables ?? [];
  return (
    <span className="flex flex-col gap-1">
      <FormDialog
        triggerLabel={
          <>
            {words.test} <span className="sr-only">{words.testName(template.event)}</span>
          </>
        }
        title={words.testTitle}
        text={words.testText}
        submitLabel={words.send}
        labels={Object.fromEntries(variables.map((row) => [`variables.${row.name}`, row.name]))}
        onSubmit={(form) =>
          testTemplate(
            template.id,
            Object.fromEntries(
              variables.map((row) => [row.name, formValue(form, row.name)]).filter(([, value]) => value),
            ),
          )
        }
        onDone={(result) => {
          const answer = result as { sent: boolean; to: string; detail: string };
          setSaid(`${answer.detail} (${answer.to})`);
          if (answer.sent) toast.success(words.send);
        }}
      >
        {(error, id) =>
          variables.map((row) => (
            <Field
              key={row.name}
              id={`${id}-${row.name}`}
              label={row.name}
              optional
              help={[row.type, row.about].filter(Boolean).join(": ")}
              error={fieldError(error, `variables.${row.name}`)}
            >
              <Input name={row.name} maxLength={row.max_length || 30} autoComplete="off" />
            </Field>
          ))
        }
      </FormDialog>
      <span role="status" className="text-sm">
        {said}
      </span>
    </span>
  );
}
