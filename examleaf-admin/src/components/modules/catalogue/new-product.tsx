"use client";

// A new product (POST catalogue/products/): its title, address, kind and MRP at least; something to post needs its
// weight and a packaging kind (a flyer by default) or its dimensions. It is made at its MRP, off sale unless ticked;
// a lower selling price follows through its approval (product.price: beyond your discount limit FINANCE approves),
// and the product's page then shows it waiting. The API's words come back beside the fields.
import { useRouter } from "next/navigation";

import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Checkbox } from "@/components/ui/choice";
import { Field, FieldLegend, FieldSet, FormGrid } from "@/components/ui/field";
import { Input, InputPrefix, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import {
  type CatalogueNewProduct,
  type CatalogueOptions,
  type CatalogueProduct,
  createCatalogueProduct,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { wholeOrNull } from "./shared";

/** The new product's fields as the API takes them: what is left empty is not sent. */
export function newProductBody(form: FormData): CatalogueNewProduct {
  const body: CatalogueNewProduct = {
    title: formText(form, "title"),
    slug: formText(form, "slug"),
    kind: formText(form, "kind") as CatalogueNewProduct["kind"],
    mrp: formText(form, "mrp"),
    is_active: form.get("is_active") === "on",
  };
  const price = formText(form, "price");
  if (price) body.price = price;
  const reason = formText(form, "reason");
  if (reason) body.reason = reason;
  const hsn = formText(form, "hsn");
  if (hsn) body.hsn = hsn;
  if (body.kind !== "digital") {
    body.weight_grams = wholeOrNull(form, "weight_grams") ?? 0;
    body.packaging = formText(form, "packaging") as CatalogueProduct["packaging"];
    for (const name of ["length_cm", "width_cm", "height_cm"] as const) {
      const value = wholeOrNull(form, name);
      if (value !== null) body[name] = value;
    }
  }
  return body;
}

export function NewProductForm({ options }: { options: CatalogueOptions }) {
  const router = useRouter();
  const f = copy.catalogue.fields;
  return (
    <ActionForm
      id="new-product"
      submitLabel={copy.catalogue.makeProduct}
      success={copy.catalogue.productMade}
      labels={f}
      onSubmit={(form) => createCatalogueProduct(newProductBody(form))}
      onDone={(result) => {
        const slug = (result as { product?: { slug?: string } } | null)?.product?.slug;
        if (slug) router.push(`/catalogue/products/${encodeURIComponent(slug)}/`);
      }}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="new-product-title" label={f.title} error={fieldError(error, "title")}>
              <Input name="title" maxLength={200} autoComplete="off" aria-required="true" />
            </Field>
            <Field
              id="new-product-slug"
              label={f.slug}
              help={copy.catalogue.help.newSlug}
              error={fieldError(error, "slug")}
            >
              <Input name="slug" maxLength={200} autoComplete="off" className="font-mono" aria-required="true" />
            </Field>
          </FormGrid>
          <FormGrid>
            <Field id="new-product-kind" label={f.kind} error={fieldError(error, "kind")}>
              <Select name="kind" defaultValue="sample-papers">
                {options.kinds.map((kind) => (
                  <option key={kind.value} value={kind.value}>
                    {kind.label}
                  </option>
                ))}
              </Select>
            </Field>
            {options.hsn_codes ? (
              <Field
                id="new-product-hsn"
                label={f.hsn}
                optional
                help={copy.catalogue.help.newHsn}
                error={fieldError(error, "hsn")}
              >
                <Select name="hsn" defaultValue="">
                  <option value="">{copy.catalogue.hsnDefault}</option>
                  {options.hsn_codes.map((code) => (
                    <option key={code.value} value={code.value}>
                      {code.label}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : null}
          </FormGrid>
          <FieldSet>
            <FieldLegend>{copy.catalogue.sections.prices}</FieldLegend>
            <FormGrid>
              <Field id="new-product-mrp" label={f.mrp} help={copy.catalogue.help.mrp} error={fieldError(error, "mrp")}>
                <InputPrefix prefix="₹" name="mrp" inputMode="decimal" autoComplete="off" aria-required="true" />
              </Field>
              <Field
                id="new-product-price"
                label={f.price}
                optional
                help={copy.catalogue.help.newPrice}
                error={fieldError(error, "price")}
              >
                <InputPrefix prefix="₹" name="price" inputMode="decimal" autoComplete="off" />
              </Field>
            </FormGrid>
            <Field
              id="new-product-reason"
              label={copy.common.reason}
              optional
              help={copy.catalogue.help.newReason}
              error={fieldError(error, "reason")}
            >
              <Textarea name="reason" rows={2} maxLength={500} />
            </Field>
          </FieldSet>
          <FieldSet>
            <FieldLegend>{copy.catalogue.sections.physical}</FieldLegend>
            <p className="m-0 mb-3 text-sm text-muted-foreground">{copy.catalogue.help.newPhysical}</p>
            <FormGrid>
              <Field
                id="new-product-weight_grams"
                label={f.weight_grams}
                help={copy.catalogue.help.weight}
                error={fieldError(error, "weight_grams")}
              >
                <Input name="weight_grams" inputMode="numeric" autoComplete="off" />
              </Field>
              <Field id="new-product-packaging" label={f.packaging} error={fieldError(error, "packaging")}>
                <Select name="packaging" defaultValue="flyer">
                  <option value="">{copy.catalogue.noPackaging}</option>
                  {options.packaging.map((kind) => (
                    <option key={kind.value} value={kind.value}>
                      {kind.label}
                    </option>
                  ))}
                </Select>
              </Field>
            </FormGrid>
            <FormGrid className="mt-4 [--min:120px]">
              {(["length_cm", "width_cm", "height_cm"] as const).map((name) => (
                <Field key={name} id={`new-product-${name}`} label={f[name]} optional error={fieldError(error, name)}>
                  <Input name={name} inputMode="numeric" autoComplete="off" />
                </Field>
              ))}
            </FormGrid>
          </FieldSet>
          <Checkbox name="is_active">{copy.catalogue.onSaleNow}</Checkbox>
        </>
      )}
    </ActionForm>
  );
}
