"use client";

// My requests' form (POST /api/v1/me/tickets/): what it is about, a subject, the message and, if it is about one, the
// order. The API makes the ticket with its number and sends the acknowledgement to the account's email address; the
// page then lists it. A refusal (an email address not confirmed yet, too many requests) is said in the API's words.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { api, personal } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

import { useAction } from "./use-action";

type Category = components["schemas"]["TicketCategoryEnum"];

/** What a request can be about, in the customer's words (the API's categories). */
export const TOPICS: [Category, string][] = [
  ["order", "An order: where it is, what came"],
  ["payment", "A payment or a refund"],
  ["book_code", "A book code"],
  ["qr_solutions", "The QR solutions in a book"],
  ["content_error", "A mistake in a book or a solution"],
  ["school_order", "An order for a school"],
  ["privacy_request", "My personal data"],
  ["grievance", "A complaint about ExamLeaf"],
];

const LABELS = { category: "What it is about", subject: "Subject", message: "Your message", order: "Order number" };

export function RequestForm({ orders }: { orders: string[] }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [made, setMade] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-4">
      {made ? (
        <Alert variant="success" title={`We have your request ${made}.`}>
          <p>We have emailed you its number. You will see our answer here and in your email.</p>
        </Alert>
      ) : null}
      <ErrorSummary error={error} labels={LABELS} />
      <form
        className="flex flex-col gap-3.5"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const element = event.currentTarget;
          const form = new FormData(element);
          const text = (name: string) => String(form.get(name) ?? "").trim();
          let number = "";
          const ok = await run(async () => {
            const ticket = await personal(
              api.POST("/api/v1/me/tickets/", {
                body: {
                  category: text("category") as Category,
                  subject: text("subject"),
                  message: text("message"),
                  order: text("order"),
                },
              }),
            );
            number = ticket.number;
          });
          if (!ok) return;
          element.reset();
          setMade(number);
          router.refresh();
        }}
      >
        <Field id="category" label={LABELS.category} required error={fieldError(error, "category")}>
          <Select name="category" defaultValue="order">
            {TOPICS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        {orders.length ? (
          <Field id="order" label={LABELS.order} optional error={fieldError(error, "order")}>
            <Select name="order" defaultValue="">
              <option value="">Not about an order</option>
              {orders.map((number) => (
                <option key={number} value={number}>
                  {number}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
        <Field id="subject" label={LABELS.subject} required error={fieldError(error, "subject")}>
          <Input name="subject" maxLength={200} autoComplete="off" />
        </Field>
        <Field
          id="message"
          label={LABELS.message}
          required
          help="What happened, and what you would like us to do."
          error={fieldError(error, "message")}
        >
          <Textarea name="message" rows={6} maxLength={5000} />
        </Field>
        <div>
          <Button type="submit" busy={busy} className="max-nav:w-full">
            Send the request
          </Button>
        </div>
      </form>
    </div>
  );
}
