"use client";

// A legal deposit recorded (POST content/legal-deposits/, content.add_legaldeposit; multipart when a scan goes with
// it): the book, the edition (the book's when left empty), the library, the day it went (not a day to come), the
// proof of dispatch and, optionally, its scan and ERPNext's delivery note. One library at a time; the API refuses a
// library that has the edition already, in its words.
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { recordDeposit } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const words = copy.content.deposits;

export function DepositForm({ books, today }: { books: { id: number; title: string }[]; today: string }) {
  const labels = Object.fromEntries(Object.entries(words.fields).filter(([key]) => !key.endsWith("Help")));
  return (
    <ActionForm
      id="deposit"
      submitLabel={words.record}
      success={words.recorded}
      labels={{ ...labels, sent_on: words.fields.sentOn, proof_file: words.fields.file, erp_delivery_note: words.fields.erp }}
      onSubmit={(form) => {
        const sent = new FormData();
        for (const name of ["book", "edition", "library", "sent_on", "proof", "erp_delivery_note"]) {
          const value = formText(form, name);
          if (value) sent.append(name, value);
        }
        const file = form.get("proof_file");
        if (file instanceof File && file.size) sent.append("proof_file", file);
        return recordDeposit(sent);
      }}
    >
      {(error) => (
        <div className="grid gap-4 min-[720px]:grid-cols-2">
          <Field id="deposit-book" label={words.fields.book} required error={fieldError(error, "book")} className="min-[720px]:col-span-2">
            <Select name="book" defaultValue={books[0] ? String(books[0].id) : ""}>
              {books.map((book) => (
                <option key={book.id} value={book.id}>
                  {book.title}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="deposit-library" label={words.fields.library} required error={fieldError(error, "library")}>
            <Select name="library" defaultValue="national_library">
              {Object.entries(words.libraries).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="deposit-edition" label={words.fields.edition} optional help={words.fields.editionHelp} error={fieldError(error, "edition")}>
            <Input name="edition" autoComplete="off" />
          </Field>
          <Field id="deposit-sent_on" label={words.fields.sentOn} required error={fieldError(error, "sent_on")}>
            <Input name="sent_on" type="date" max={today} defaultValue={today} />
          </Field>
          <Field id="deposit-proof" label={words.fields.proof} required help={words.fields.proofHelp} error={fieldError(error, "proof")}>
            <Input name="proof" autoComplete="off" />
          </Field>
          <Field id="deposit-proof_file" label={words.fields.file} optional help={words.fields.fileHelp} error={fieldError(error, "proof_file")}>
            <Input name="proof_file" type="file" accept="application/pdf,image/jpeg,image/png,image/webp" className="py-2.5" />
          </Field>
          <Field id="deposit-erp_delivery_note" label={words.fields.erp} optional help={words.fields.erpHelp} error={fieldError(error, "erp_delivery_note")}>
            <Input name="erp_delivery_note" autoComplete="off" className="font-mono" />
          </Field>
        </div>
      )}
    </ActionForm>
  );
}
