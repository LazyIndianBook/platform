"use client";

// A product's sections as forms, each behind its own save bar (plan 5.0: more than five inputs means sections) and
// each sending only what changed (PATCH catalogue/products/{slug}/), so the API checks each part against its own
// permission: the page (shop.change_product), the courier's data, the tax (staff.change_product_tax), the search
// engines. A bundle's books go all at once (PUT …/bundle/), the stock by hand with its reason (POST …/stock/, refused
// when orders changed it since the page was read), pictures one by one. The API's words come back beside the fields.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { FormDialog } from "@/components/modules/orders/form-dialog";
import { Checkbox } from "@/components/ui/choice";
import { Field, FieldLegend, FieldSet, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { ApiError } from "@/lib/api/errors";
import {
  addProductPicture,
  type CatalogueOptions,
  type CatalogueProduct,
  type CatalogueProductChange,
  changeProductPicture,
  removeProductPicture,
  setBundleLines,
  setProductStock,
  updateCatalogueProduct,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { bundleLinesOf, bundleText, changedOnly, wholeOrNull } from "./shared";

const TITLE_LIMIT = 70; // where search results cut a title, about
const DESCRIPTION_LIMIT = 320;

/** A section's form: what it changes against the product, sent alone; nothing changed is said, not sent. */
function SectionForm({
  id,
  product,
  current,
  read,
  submitLabel,
  labels,
  children,
}: {
  id: string;
  product: Pick<CatalogueProduct, "slug">;
  current: Record<string, unknown>;
  read: (form: FormData) => CatalogueProductChange;
  submitLabel: string;
  labels: Record<string, string>;
  children: (error: ApiError | null) => React.ReactNode;
}) {
  const router = useRouter();
  return (
    <ActionForm
      id={id}
      submitLabel={submitLabel}
      success={copy.catalogue.saved}
      labels={labels}
      saveBar
      onSubmit={async (form) => {
        const body = changedOnly(current, read(form));
        if (!Object.keys(body).length) throw new ApiError(400, "invalid", copy.catalogue.nothingChanged);
        return updateCatalogueProduct(product.slug, body);
      }}
      onDone={(result) => {
        const slug = (result as { slug?: string } | null)?.slug;
        if (slug && slug !== product.slug) router.replace(`/catalogue/products/${encodeURIComponent(slug)}/`);
      }}
    >
      {children}
    </ActionForm>
  );
}

const choice = (rows: { value: string; label: string }[], none?: string) => (
  <>
    {none !== undefined ? <option value="">{none}</option> : null}
    {rows.map((row) => (
      <option key={row.value} value={row.value}>
        {row.label}
      </option>
    ))}
  </>
);

/** The page's fields: words, addresses, what it is, its shelves and its attributes. */
export function IdentityForm({ product, options }: { product: CatalogueProduct; options: CatalogueOptions }) {
  const f = copy.catalogue.fields;
  const current = {
    title: product.title,
    slug: product.slug,
    kind: product.kind,
    is_active: product.is_active,
    subject: product.subject?.id ?? null,
    book: product.book?.slug ?? null,
    isbn: product.isbn,
    pages: product.pages,
    product_type: product.product_type?.id ?? null,
    categories: product.categories.map((shelf) => shelf.slug),
    description: product.description,
    attributes: Object.fromEntries(product.attributes.map((attribute) => [attribute.code, attribute.value ?? ""])),
  };
  return (
    <SectionForm
      id="identity"
      product={product}
      current={current}
      submitLabel={copy.catalogue.savePage}
      labels={f}
      read={(form) => ({
        title: formText(form, "title"),
        slug: formText(form, "slug"),
        kind: formText(form, "kind") as CatalogueProduct["kind"],
        is_active: form.get("is_active") === "on",
        subject: wholeOrNull(form, "subject"),
        book: formText(form, "book") || null,
        isbn: formText(form, "isbn"),
        pages: wholeOrNull(form, "pages"),
        product_type: wholeOrNull(form, "product_type"),
        categories: form.getAll("categories").map(String),
        description: String(form.get("description") ?? ""),
        attributes: Object.fromEntries(
          product.attributes.map((attribute) => [attribute.code, formText(form, `attribute-${attribute.code}`)]),
        ),
      })}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="identity-title" label={f.title} error={fieldError(error, "title")}>
              <Input name="title" defaultValue={product.title} maxLength={200} aria-required="true" />
            </Field>
            <Field id="identity-slug" label={f.slug} help={copy.catalogue.help.slug} error={fieldError(error, "slug")}>
              <Input name="slug" defaultValue={product.slug} autoComplete="off" maxLength={200} className="font-mono" />
            </Field>
          </FormGrid>
          <FormGrid>
            <Field id="identity-kind" label={f.kind} help={copy.catalogue.help.kind} error={fieldError(error, "kind")}>
              <Select name="kind" defaultValue={product.kind}>
                {choice(options.kinds)}
              </Select>
            </Field>
            <Field
              id="identity-isbn"
              label={f.isbn}
              optional
              help={copy.catalogue.help.isbn}
              error={fieldError(error, "isbn")}
            >
              <Input name="isbn" defaultValue={product.isbn} inputMode="numeric" autoComplete="off" maxLength={17} />
            </Field>
            <Field id="identity-pages" label={f.pages} optional error={fieldError(error, "pages")}>
              <Input name="pages" defaultValue={product.pages ?? ""} inputMode="numeric" autoComplete="off" />
            </Field>
          </FormGrid>
          <Checkbox name="is_active" defaultChecked={product.is_active}>
            {copy.catalogue.onSaleBox}
          </Checkbox>
          <FormGrid>
            <Field id="identity-subject" label={f.subject} optional error={fieldError(error, "subject")}>
              <Select name="subject" defaultValue={product.subject ? String(product.subject.id) : ""}>
                {choice(options.subjects, copy.common.none)}
              </Select>
            </Field>
            <Field id="identity-book" label={f.book} optional error={fieldError(error, "book")}>
              <Select name="book" defaultValue={product.book?.slug ?? ""}>
                {choice(options.books, copy.common.none)}
              </Select>
            </Field>
            <Field id="identity-product_type" label={f.product_type} optional error={fieldError(error, "product_type")}>
              <Select name="product_type" defaultValue={product.product_type ? String(product.product_type.id) : ""}>
                {choice(options.product_types, copy.common.none)}
              </Select>
            </Field>
          </FormGrid>
          {product.attributes.length ? (
            <FieldSet>
              <FieldLegend>{copy.catalogue.attributes}</FieldLegend>
              <FormGrid>
                {product.attributes.map((attribute) => (
                  <Field
                    key={attribute.code}
                    id={`identity-attribute-${attribute.code}`}
                    label={attribute.name}
                    optional
                    error={fieldError(error, `attributes.${attribute.code}`)}
                  >
                    {attribute.choices.length || attribute.kind === "boolean" ? (
                      <Select name={`attribute-${attribute.code}`} defaultValue={attribute.value ?? ""}>
                        {choice(
                          attribute.kind === "boolean"
                            ? [
                                { value: "yes", label: copy.common.yes },
                                { value: "no", label: copy.common.no },
                              ]
                            : attribute.choices.map((value) => ({ value, label: value })),
                          copy.common.none,
                        )}
                      </Select>
                    ) : (
                      <Input
                        name={`attribute-${attribute.code}`}
                        defaultValue={attribute.value ?? ""}
                        inputMode={attribute.kind === "number" ? "decimal" : undefined}
                        autoComplete="off"
                      />
                    )}
                  </Field>
                ))}
              </FormGrid>
            </FieldSet>
          ) : null}
          <FieldSet>
            <FieldLegend>{f.categories}</FieldLegend>
            {options.categories.length ? (
              <div className="grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-x-5">
                {options.categories.map((shelf) => (
                  <Checkbox
                    key={shelf.value}
                    name="categories"
                    value={shelf.value}
                    defaultChecked={product.categories.some((own) => own.slug === shelf.value)}
                  >
                    {shelf.label}
                  </Checkbox>
                ))}
              </div>
            ) : (
              <p className="m-0 text-muted-foreground">{copy.catalogue.noCategories}</p>
            )}
            {fieldError(error, "categories") ? (
              <p className="m-0 text-sm font-semibold text-destructive">{fieldError(error, "categories")?.join(" ")}</p>
            ) : null}
          </FieldSet>
          <Field
            id="identity-description"
            label={f.description}
            optional
            help={copy.catalogue.help.description}
            error={fieldError(error, "description")}
          >
            <Textarea name="description" defaultValue={product.description} rows={6} />
          </Field>
        </>
      )}
    </SectionForm>
  );
}

/** The courier's data: the weight, the packaging kind or the dimensions. */
export function PhysicalForm({ product, options }: { product: CatalogueProduct; options: CatalogueOptions }) {
  const f = copy.catalogue.fields;
  const current = {
    weight_grams: product.weight_grams,
    packaging: product.packaging,
    length_cm: product.length_cm,
    width_cm: product.width_cm,
    height_cm: product.height_cm,
  };
  return (
    <SectionForm
      id="physical"
      product={product}
      current={current}
      submitLabel={copy.catalogue.savePhysical}
      labels={f}
      read={(form) => ({
        weight_grams: wholeOrNull(form, "weight_grams") ?? 0,
        packaging: formText(form, "packaging") as CatalogueProduct["packaging"],
        length_cm: wholeOrNull(form, "length_cm"),
        width_cm: wholeOrNull(form, "width_cm"),
        height_cm: wholeOrNull(form, "height_cm"),
      })}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field
              id="physical-weight_grams"
              label={f.weight_grams}
              help={copy.catalogue.help.weight}
              error={fieldError(error, "weight_grams")}
            >
              <Input name="weight_grams" defaultValue={product.weight_grams} inputMode="numeric" autoComplete="off" />
            </Field>
            <Field
              id="physical-packaging"
              label={f.packaging}
              help={copy.catalogue.help.packaging}
              error={fieldError(error, "packaging")}
            >
              <Select name="packaging" defaultValue={product.packaging}>
                {choice(options.packaging, copy.catalogue.noPackaging)}
              </Select>
            </Field>
          </FormGrid>
          <FormGrid className="[--min:120px]">
            {(["length_cm", "width_cm", "height_cm"] as const).map((name) => (
              <Field key={name} id={`physical-${name}`} label={f[name]} optional error={fieldError(error, name)}>
                <Input name={name} defaultValue={product[name] ?? ""} inputMode="numeric" autoComplete="off" />
              </Field>
            ))}
          </FormGrid>
          <p className="m-0 text-sm text-muted-foreground">{copy.catalogue.help.dimensions}</p>
        </>
      )}
    </SectionForm>
  );
}

/** The tax: the HSN or SAC code from the master, a bundle's treatment and the CA's note. */
export function TaxForm({ product, options }: { product: CatalogueProduct; options: CatalogueOptions }) {
  const f = copy.catalogue.fields;
  const bundle = product.kind === "bundle";
  const current = {
    hsn: product.hsn,
    tax_note: product.tax_note,
    tax_note_date: product.tax_note_date,
    ...(bundle ? { tax_treatment: product.tax_treatment } : {}),
  };
  return (
    <SectionForm
      id="tax"
      product={product}
      current={current}
      submitLabel={copy.catalogue.saveTax}
      labels={f}
      read={(form) => ({
        hsn: formText(form, "hsn") || null,
        tax_note: String(form.get("tax_note") ?? ""),
        tax_note_date: formText(form, "tax_note_date") || null,
        ...(bundle ? { tax_treatment: formText(form, "tax_treatment") as CatalogueProduct["tax_treatment"] } : {}),
      })}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="tax-hsn" label={f.hsn} help={copy.catalogue.help.hsn} error={fieldError(error, "hsn")}>
              {options.hsn_codes ? (
                <Select name="hsn" defaultValue={product.hsn ?? ""}>
                  {choice(options.hsn_codes, copy.common.none)}
                </Select>
              ) : (
                <Input
                  name="hsn"
                  defaultValue={product.hsn ?? ""}
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={8}
                />
              )}
            </Field>
            {bundle ? (
              <Field id="tax-tax_treatment" label={f.tax_treatment} error={fieldError(error, "tax_treatment")}>
                <Select name="tax_treatment" defaultValue={product.tax_treatment}>
                  {choice(options.tax_treatments)}
                </Select>
              </Field>
            ) : null}
          </FormGrid>
          <FormGrid>
            <Field
              id="tax-tax_note"
              label={f.tax_note}
              optional
              help={copy.catalogue.help.taxNote}
              error={fieldError(error, "tax_note")}
            >
              <Textarea name="tax_note" defaultValue={product.tax_note} rows={3} />
            </Field>
            <Field id="tax-tax_note_date" label={f.tax_note_date} optional error={fieldError(error, "tax_note_date")}>
              <Input name="tax_note_date" type="date" defaultValue={product.tax_note_date ?? ""} />
            </Field>
          </FormGrid>
        </>
      )}
    </SectionForm>
  );
}

function Counted({
  id,
  name,
  label,
  limit,
  value,
  error,
  long,
}: {
  id: string;
  name: string;
  label: string;
  limit: number;
  value: string;
  error: string[] | null;
  long?: boolean;
}) {
  const [length, setLength] = useState(value.length);
  const help = length > limit ? copy.catalogue.tooLong(length, limit) : copy.catalogue.characters(length, limit);
  const props = {
    name,
    defaultValue: value,
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setLength(event.currentTarget.value.length),
  };
  return (
    <Field id={id} label={label} optional help={help} error={error}>
      {long ? (
        <Textarea {...props} rows={3} maxLength={500} />
      ) : (
        <Input {...props} maxLength={200} autoComplete="off" />
      )}
    </Field>
  );
}

/** What search engines show: the title and the description, with their usual lengths. */
export function SeoForm({ product }: { product: CatalogueProduct }) {
  const f = copy.catalogue.fields;
  return (
    <SectionForm
      id="seo"
      product={product}
      current={{ seo_title: product.seo_title, seo_description: product.seo_description }}
      submitLabel={copy.catalogue.saveSeo}
      labels={f}
      read={(form) => ({
        seo_title: formText(form, "seo_title"),
        seo_description: formText(form, "seo_description"),
      })}
    >
      {(error) => (
        <>
          <Counted
            id="seo-seo_title"
            name="seo_title"
            label={f.seo_title}
            limit={TITLE_LIMIT}
            value={product.seo_title}
            error={fieldError(error, "seo_title")}
          />
          <Counted
            id="seo-seo_description"
            name="seo_description"
            label={f.seo_description}
            limit={DESCRIPTION_LIMIT}
            value={product.seo_description}
            error={fieldError(error, "seo_description")}
            long
          />
        </>
      )}
    </SectionForm>
  );
}

/** A bundle's books, one a line: its slug, then its copies. */
export function BundleForm({ product }: { product: CatalogueProduct }) {
  const lines = product.bundle_items.map((item) => ({ product: item.product, quantity: item.quantity }));
  return (
    <ActionForm
      id="bundle"
      submitLabel={copy.catalogue.saveBundle}
      success={copy.catalogue.bundleSaved}
      labels={{ lines: copy.catalogue.fields.lines }}
      saveBar
      onSubmit={async (form) => {
        const read = bundleLinesOf(String(form.get("lines") ?? ""));
        if (read.problem) throw new ApiError(400, "invalid", read.problem, { lines: [read.problem] });
        return setBundleLines(product.slug, read.lines);
      }}
    >
      {(error) => (
        <Field
          id="bundle-lines"
          label={copy.catalogue.fields.lines}
          help={copy.catalogue.help.lines}
          error={fieldError(error, "lines")}
        >
          <Textarea
            name="lines"
            defaultValue={bundleText(lines)}
            rows={Math.max(3, lines.length + 1)}
            className="font-mono"
          />
        </Field>
      )}
    </ActionForm>
  );
}

/** A book's copies set by hand with the reason; the count the page read goes with it (`expected`). */
export function SetStock({ product }: { product: Pick<CatalogueProduct, "slug" | "title" | "stock_info"> }) {
  const labels = {
    stock: copy.catalogue.fields.stock,
    reason: copy.common.reason,
    expected: copy.catalogue.fields.stock,
  };
  return (
    <FormDialog
      triggerLabel={copy.catalogue.setStock}
      title={copy.catalogue.setStockTitle(product.title)}
      text={copy.catalogue.setStockText(product.stock_info.stock)}
      submitLabel={copy.catalogue.setStock}
      labels={labels}
      success={copy.catalogue.stockSet}
      onSubmit={(form) =>
        setProductStock(product.slug, {
          stock: Number(formText(form, "stock")),
          reason: formText(form, "reason"),
          expected: product.stock_info.stock,
        })
      }
    >
      {(prefix, error) => (
        <>
          <Field
            id={`${prefix}stock`}
            label={copy.catalogue.fields.stock}
            error={fieldError(error, "stock") ?? fieldError(error, "expected")}
          >
            <Input
              name="stock"
              inputMode="numeric"
              autoComplete="off"
              defaultValue={product.stock_info.stock}
              aria-required="true"
            />
          </Field>
          <Field
            id={`${prefix}reason`}
            label={copy.common.reason}
            help={copy.catalogue.help.stockReason}
            error={fieldError(error, "reason")}
          >
            <Textarea name="reason" rows={2} maxLength={500} aria-required="true" />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

/** The pictures: each one's words and place, taken off with a confirmation; a new one with its description. */
export function Pictures({
  product,
  canAdd,
  canChange,
  canRemove,
}: {
  product: Pick<CatalogueProduct, "slug" | "title" | "cover" | "images">;
  canAdd: boolean;
  canChange: boolean;
  canRemove: boolean;
}) {
  const f = copy.catalogue.fields;
  return (
    <div className="flex flex-col gap-6">
      {product.images.length ? (
        <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(min(180px,100%),1fr))] gap-4 p-0">
          {product.images.map((image) => (
            <li key={image.id} className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3">
              {/* eslint-disable-next-line @next/next/no-img-element -- the API's own sizes, from the media domain */}
              <img
                src={image.src}
                alt={image.alt}
                width={image.width ?? undefined}
                height={image.height ?? undefined}
                className="h-auto max-h-48 w-full object-contain"
              />
              <p className="m-0 text-sm">{image.alt || copy.catalogue.noAlt}</p>
              <p className="m-0 text-sm text-muted-foreground">{copy.catalogue.position(image.position)}</p>
              <div className="flex flex-wrap gap-2">
                {canChange ? (
                  <FormDialog
                    triggerLabel={copy.catalogue.editPicture}
                    title={copy.catalogue.editPicture}
                    submitLabel={copy.common.save}
                    labels={{ alt: f.alt, position: f.position }}
                    success={copy.catalogue.saved}
                    onSubmit={(form) =>
                      changeProductPicture(product.slug, image.id, {
                        alt: formText(form, "alt"),
                        position: Number(formText(form, "position") || 0),
                      })
                    }
                  >
                    {(prefix, error) => (
                      <>
                        <Field
                          id={`${prefix}alt`}
                          label={f.alt}
                          help={copy.catalogue.help.alt}
                          error={fieldError(error, "alt")}
                        >
                          <Input name="alt" defaultValue={image.alt} maxLength={200} autoComplete="off" />
                        </Field>
                        <Field id={`${prefix}position`} label={f.position} error={fieldError(error, "position")}>
                          <Input name="position" defaultValue={image.position} inputMode="numeric" autoComplete="off" />
                        </Field>
                      </>
                    )}
                  </FormDialog>
                ) : null}
                {canRemove ? (
                  <ConfirmDialog
                    triggerLabel={copy.catalogue.removePicture}
                    title={copy.catalogue.removePictureTitle}
                    text={copy.catalogue.removePictureText}
                    confirmLabel={copy.catalogue.removePicture}
                    success={copy.catalogue.pictureRemoved}
                    onConfirm={() => removeProductPicture(product.slug, image.id)}
                  />
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="m-0 text-muted-foreground">{copy.catalogue.noPictures}</p>
      )}
      {canAdd ? (
        <ActionForm
          id="picture"
          submitLabel={copy.catalogue.addPicture}
          success={copy.catalogue.pictureAdded}
          labels={{ image: f.image, alt: f.alt, position: f.position }}
          onSubmit={(form) => {
            const sent = new FormData();
            const file = form.get("image");
            if (file instanceof File && file.size) sent.append("image", file);
            sent.append("alt", formText(form, "alt"));
            sent.append("position", formText(form, "position") || "0");
            sent.append("as_cover", form.get("as_cover") === "on" ? "true" : "false");
            return addProductPicture(product.slug, sent);
          }}
        >
          {(error) => (
            <>
              <Field
                id="picture-image"
                label={f.image}
                help={copy.catalogue.help.image}
                error={fieldError(error, "image")}
              >
                <Input name="image" type="file" accept="image/jpeg,image/png,image/webp" className="py-2.5" />
              </Field>
              <FormGrid>
                <Field id="picture-alt" label={f.alt} help={copy.catalogue.help.alt} error={fieldError(error, "alt")}>
                  <Input name="alt" maxLength={200} autoComplete="off" />
                </Field>
                <Field id="picture-position" label={f.position} optional error={fieldError(error, "position")}>
                  <Input name="position" inputMode="numeric" autoComplete="off" />
                </Field>
              </FormGrid>
              <Checkbox name="as_cover">{copy.catalogue.asCover}</Checkbox>
            </>
          )}
        </ActionForm>
      ) : null}
    </div>
  );
}
