"use client";

// Logging a complaint that came another way (POST support/tickets/): a phone call, a WhatsApp message, a complaint the
// National Consumer Helpline forwarded (its docket number) or an email to a personal address. What the source needs is
// asked for (the number they called from, the docket, the address it came from); the API checks it all again. Its
// deadlines run from when it was received; the acknowledgement goes to the address or number given. Once logged, the
// ticket opens.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { logTicket, type Schemas } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { fromLocalInput, toLocalInput } from "@/lib/format";

type Source = Schemas["TicketLoggedSourceEnum"];
const SOURCES = Object.keys(copy.support.loggedSources) as Source[];

/** The body the API takes from the form (empty optional fields left as the API's defaults). */
export function logBody(form: FormData): Schemas["TicketCreateRequest"] {
  const text = (name: string) => formText(form, name);
  const received = text("received_at");
  return {
    source: text("source") as Source,
    nch_docket: text("nch_docket"),
    name: text("name"),
    email: text("email"),
    phone: text("phone"),
    category: text("category") as Schemas["TicketCreateRequest"]["category"],
    priority: (text("priority") || "medium") as Schemas["TicketPriorityEnum"],
    subject: text("subject"),
    message: text("message"),
    ...(received ? { received_at: fromLocalInput(received) } : {}),
    order: text("order"),
  };
}

export function LogTicketForm({ now }: { now: number }) {
  const router = useRouter();
  const [source, setSource] = useState<Source>("phone");
  const id = "new-ticket";
  const field = (name: string) => `${id}-${name}`;
  return (
    <ActionForm
      id={id}
      submitLabel={copy.support.logButton}
      success={copy.support.logged}
      className="flex max-w-[48rem] flex-col gap-4"
      labels={{
        source: copy.support.cameBy,
        nch_docket: copy.support.docket,
        name: copy.support.name,
        email: copy.support.email,
        phone: copy.support.phone,
        category: copy.support.category,
        priority: copy.support.priority,
        subject: copy.support.subject,
        message: copy.support.message,
        received_at: copy.support.receivedAt,
        order: copy.support.orderNumber,
      }}
      onSubmit={(form) => logTicket(logBody(form))}
      onDone={(made) => router.push(`/support/tickets/${encodeURIComponent((made as { number: string }).number)}/`)}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id={field("source")} label={copy.support.cameBy} error={fieldError(error, "source")}>
              <Select
                name="source"
                value={source}
                data-no-draft=""
                onChange={(event) => setSource(event.currentTarget.value as Source)}
              >
                {SOURCES.map((value) => (
                  <option key={value} value={value}>
                    {copy.support.loggedSources[value]}
                  </option>
                ))}
              </Select>
            </Field>
            {source === "nch" ? (
              <Field
                id={field("nch_docket")}
                label={copy.support.docket}
                help={copy.support.docketHelp}
                error={fieldError(error, "nch_docket")}
              >
                <Input name="nch_docket" autoComplete="off" className="font-mono" aria-required="true" maxLength={40} />
              </Field>
            ) : null}
            <Field
              id={field("received_at")}
              label={copy.support.receivedAt}
              help={copy.support.receivedAtHelp}
              error={fieldError(error, "received_at")}
            >
              <Input name="received_at" type="datetime-local" defaultValue={toLocalInput(now)} aria-required="true" />
            </Field>
          </FormGrid>
          <FormGrid>
            <Field id={field("name")} label={copy.support.name} optional error={fieldError(error, "name")}>
              <Input name="name" autoComplete="off" maxLength={120} />
            </Field>
            <Field
              id={field("phone")}
              label={copy.support.phone}
              optional={source === "email" || source === "nch"}
              help={copy.support.phoneHelp}
              error={fieldError(error, "phone")}
            >
              <Input name="phone" type="tel" autoComplete="off" />
            </Field>
            <Field
              id={field("email")}
              label={copy.support.email}
              optional={source !== "email"}
              help={copy.support.emailHelp}
              error={fieldError(error, "email")}
            >
              <Input name="email" type="email" autoComplete="off" />
            </Field>
          </FormGrid>
          <FormGrid>
            <Field id={field("category")} label={copy.support.category} optional error={fieldError(error, "category")}>
              <Select name="category" defaultValue="">
                <option value="">{copy.support.sortLater}</option>
                {Object.entries(copy.support.categories).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id={field("priority")} label={copy.support.priority} error={fieldError(error, "priority")}>
              <Select name="priority" defaultValue="medium">
                {Object.entries(copy.support.priorities).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              id={field("order")}
              label={copy.support.orderNumber}
              optional
              help={copy.support.orderHelp}
              error={fieldError(error, "order")}
            >
              <Input name="order" autoComplete="off" className="font-mono" />
            </Field>
          </FormGrid>
          <Field id={field("subject")} label={copy.support.subject} error={fieldError(error, "subject")}>
            <Input name="subject" autoComplete="off" maxLength={200} aria-required="true" />
          </Field>
          <Field
            id={field("message")}
            label={copy.support.message}
            help={copy.support.messageHelp}
            error={fieldError(error, "message")}
          >
            <Textarea name="message" rows={6} aria-required="true" maxLength={20000} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}
