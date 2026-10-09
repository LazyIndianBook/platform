"use client";

// A book made (POST content/books/) or changed (PATCH content/books/{id}/): its title, edition, address name, cover,
// format, ISBN (the API checks its check digit when it is set or changed, and that no other book has it) and the day
// it was published (the legal deposit's clock). The API's words go beside each field.
import { useRouter } from "next/navigation";

import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { type ContentBookDetail, createBook, updateBook } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

const words = copy.content.books;

export function BookForm({
  book,
  subjects = [],
}: {
  book?: ContentBookDetail;
  /** The subjects a new book may be of (those of the books already there): id and code. */
  subjects?: { id: number; code: string }[];
}) {
  const router = useRouter();
  const id = book ? `book-${book.id}` : "book-new";
  const labels = Object.fromEntries(Object.entries(words.fields).filter(([key]) => !key.endsWith("Help")));
  return (
    <ActionForm
      id={id}
      submitLabel={book ? words.save : words.add}
      success={book ? words.saved : words.added}
      labels={{ ...labels, published_on: words.fields.publishedOn }}
      onSubmit={async (form) => {
        const body = {
          title: formText(form, "title"),
          edition: formText(form, "edition"),
          slug: formText(form, "slug"),
          cover: formText(form, "cover"),
          isbn: formText(form, "isbn"),
          format: (formText(form, "format") || "print") as "print" | "ebook",
          published_on: formText(form, "published_on") || null,
        };
        if (book) return updateBook(book.id, body);
        const made = await createBook({ ...body, subject: Number(formText(form, "subject")) });
        router.push(`/content/books/${made.id}/`);
        return made;
      }}
    >
      {(error) => (
        <div className="grid gap-4 min-[720px]:grid-cols-2">
          <Field id={`${id}-title`} label={words.fields.title} required error={fieldError(error, "title")} className="min-[720px]:col-span-2">
            <Input name="title" defaultValue={book?.title ?? ""} autoComplete="off" />
          </Field>
          {book ? null : (
            <Field id={`${id}-subject`} label={words.fields.subject} required error={fieldError(error, "subject")}>
              <Select name="subject" defaultValue={subjects[0] ? String(subjects[0].id) : ""}>
                {subjects.map((subject) => (
                  <option key={subject.id} value={subject.id}>
                    {labelOf(copy.content.subjects, subject.code)}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field id={`${id}-edition`} label={words.fields.edition} optional error={fieldError(error, "edition")}>
            <Input name="edition" defaultValue={book?.edition ?? ""} autoComplete="off" />
          </Field>
          <Field id={`${id}-slug`} label={words.fields.slug} required help={words.fields.slugHelp} error={fieldError(error, "slug")}>
            <Input name="slug" defaultValue={book?.slug ?? ""} autoComplete="off" className="font-mono" />
          </Field>
          <Field id={`${id}-cover`} label={words.fields.cover} optional help={words.fields.coverHelp} error={fieldError(error, "cover")}>
            <Input name="cover" defaultValue={book?.cover ?? ""} autoComplete="off" className="font-mono" />
          </Field>
          <Field id={`${id}-format`} label={words.fields.format} error={fieldError(error, "format")}>
            <Select name="format" defaultValue={book?.format ?? "print"}>
              {Object.entries(copy.content.formats).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field id={`${id}-isbn`} label={words.fields.isbn} optional help={words.fields.isbnHelp} error={fieldError(error, "isbn")}>
            <Input name="isbn" defaultValue={book?.isbn ?? ""} autoComplete="off" inputMode="numeric" className="font-mono" />
          </Field>
          <Field
            id={`${id}-published_on`}
            label={words.fields.publishedOn}
            optional
            help={words.fields.publishedHelp}
            error={fieldError(error, "published_on")}
          >
            <Input name="published_on" type="date" defaultValue={book?.published_on ?? ""} />
          </Field>
        </div>
      )}
    </ActionForm>
  );
}
