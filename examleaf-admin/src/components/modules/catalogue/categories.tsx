"use client";

// The shop's shelves as a tree (GET catalogue/categories/, in tree order: each followed by those under it): a new one
// under another or at the top, a shelf's words and address, and a move with every shelf under it (treebeard's own
// move: under another, first or last; beside one, before or after; never under itself). A product's shelves are set
// on the product. And the collections (GET catalogue/collections/): hand-picked lists in their order.
import { useRouter } from "next/navigation";

import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { FormDialog } from "@/components/modules/orders/form-dialog";
import { Checkbox } from "@/components/ui/choice";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import {
  type CatalogueCategory,
  type CatalogueCollection,
  createCategory,
  createCollection,
  moveCategory,
  updateCategory,
  updateCollection,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { slugsOf } from "./shared";

/** The shelves that a shelf may move under or beside: neither itself nor any under it. */
export function movesFor(tree: CatalogueCategory[], slug: string): CatalogueCategory[] {
  const index = tree.findIndex((shelf) => shelf.slug === slug);
  if (index < 0) return tree;
  const depth = tree[index].depth;
  let end = index + 1;
  while (end < tree.length && tree[end].depth > depth) end += 1;
  return [...tree.slice(0, index), ...tree.slice(end)];
}

const indent = (shelf: CatalogueCategory) => `${"— ".repeat(Math.max(0, shelf.depth - 1))}${shelf.name}`;

export function CategoryTree({ tree, canChange }: { tree: CatalogueCategory[]; canChange: boolean }) {
  const f = copy.catalogue.fields;
  if (!tree.length) return <p className="m-0 text-muted-foreground">{copy.catalogue.noCategories}</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0" aria-label={copy.catalogue.categoriesTitle}>
      {tree.map((shelf) => (
        <li
          key={shelf.slug}
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3"
          style={{ marginInlineStart: `${Math.min(shelf.depth - 1, 6) * 1.25}rem` }}
        >
          <span className="flex min-w-0 flex-col">
            <span className="font-semibold">{shelf.name}</span>
            <span className="text-[13px] text-muted-foreground">
              <span className="font-mono">{shelf.slug}</span> · {copy.catalogue.productCount(shelf.products)}
            </span>
          </span>
          {canChange ? (
            <span className="flex flex-wrap gap-2">
              <FormDialog
                triggerLabel={copy.catalogue.editShelf}
                title={copy.catalogue.editShelfTitle(shelf.name)}
                submitLabel={copy.common.save}
                labels={{ name: f.name_shelf, slug: f.slug, description: f.description }}
                success={copy.catalogue.saved}
                onSubmit={(form) =>
                  updateCategory(shelf.slug, {
                    name: formText(form, "name"),
                    slug: formText(form, "slug"),
                    description: String(form.get("description") ?? ""),
                  })
                }
              >
                {(prefix, error) => (
                  <>
                    <Field id={`${prefix}name`} label={f.name_shelf} error={fieldError(error, "name")}>
                      <Input name="name" defaultValue={shelf.name} maxLength={100} autoComplete="off" />
                    </Field>
                    <Field
                      id={`${prefix}slug`}
                      label={f.slug}
                      help={copy.catalogue.help.shelfSlug}
                      error={fieldError(error, "slug")}
                    >
                      <Input
                        name="slug"
                        defaultValue={shelf.slug}
                        maxLength={50}
                        autoComplete="off"
                        className="font-mono"
                      />
                    </Field>
                    <Field
                      id={`${prefix}description`}
                      label={f.description}
                      optional
                      error={fieldError(error, "description")}
                    >
                      <Textarea name="description" defaultValue={shelf.description ?? ""} rows={3} />
                    </Field>
                  </>
                )}
              </FormDialog>
              <FormDialog
                triggerLabel={copy.catalogue.moveShelf}
                title={copy.catalogue.moveShelfTitle(shelf.name)}
                text={copy.catalogue.moveShelfText}
                submitLabel={copy.catalogue.moveShelf}
                labels={{ target: f.target, position: f.position_tree }}
                success={copy.catalogue.moved}
                onSubmit={(form) =>
                  moveCategory(shelf.slug, {
                    target: formText(form, "target") || null,
                    position: formText(form, "position") as "first-child" | "last-child" | "left" | "right",
                  })
                }
              >
                {(prefix, error) => (
                  <>
                    <Field id={`${prefix}target`} label={f.target} error={fieldError(error, "target")}>
                      <Select name="target" defaultValue="">
                        <option value="">{copy.catalogue.topLevel}</option>
                        {movesFor(tree, shelf.slug).map((other) => (
                          <option key={other.slug} value={other.slug}>
                            {indent(other)}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field id={`${prefix}position`} label={f.position_tree} error={fieldError(error, "position")}>
                      <Select name="position" defaultValue="last-child">
                        {Object.entries(copy.catalogue.positions).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </>
                )}
              </FormDialog>
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function NewCategoryForm({ tree }: { tree: CatalogueCategory[] }) {
  const f = copy.catalogue.fields;
  return (
    <ActionForm
      id="new-shelf"
      submitLabel={copy.catalogue.makeShelf}
      success={copy.catalogue.shelfMade}
      labels={{ name: f.name_shelf, slug: f.slug, parent: f.parent, description: f.description }}
      onSubmit={(form) =>
        createCategory({
          name: formText(form, "name"),
          slug: formText(form, "slug"),
          parent: formText(form, "parent") || null,
          description: String(form.get("description") ?? ""),
        })
      }
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="new-shelf-name" label={f.name_shelf} error={fieldError(error, "name")}>
              <Input name="name" maxLength={100} autoComplete="off" aria-required="true" />
            </Field>
            <Field
              id="new-shelf-slug"
              label={f.slug}
              help={copy.catalogue.help.shelfSlug}
              error={fieldError(error, "slug")}
            >
              <Input name="slug" maxLength={50} autoComplete="off" className="font-mono" aria-required="true" />
            </Field>
            <Field id="new-shelf-parent" label={f.parent} optional error={fieldError(error, "parent")}>
              <Select name="parent" defaultValue="">
                <option value="">{copy.catalogue.topLevel}</option>
                {tree.map((shelf) => (
                  <option key={shelf.slug} value={shelf.slug}>
                    {indent(shelf)}
                  </option>
                ))}
              </Select>
            </Field>
          </FormGrid>
          <Field id="new-shelf-description" label={f.description} optional error={fieldError(error, "description")}>
            <Textarea name="description" rows={3} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

function CollectionFields({
  prefix,
  collection,
  error,
}: {
  prefix: string;
  collection: CatalogueCollection | null;
  error: Parameters<typeof fieldError>[0];
}) {
  const f = copy.catalogue.fields;
  return (
    <>
      <FormGrid>
        <Field id={`${prefix}name`} label={f.name_collection} error={fieldError(error, "name")}>
          <Input
            name="name"
            defaultValue={collection?.name ?? ""}
            maxLength={100}
            autoComplete="off"
            aria-required="true"
          />
        </Field>
        <Field id={`${prefix}slug`} label={f.slug} error={fieldError(error, "slug")}>
          <Input
            name="slug"
            defaultValue={collection?.slug ?? ""}
            maxLength={50}
            autoComplete="off"
            className="font-mono"
            aria-required="true"
          />
        </Field>
        <Field
          id={`${prefix}position`}
          label={f.order}
          optional
          help={copy.catalogue.help.collectionOrder}
          error={fieldError(error, "position")}
        >
          <Input name="position" defaultValue={collection?.position ?? ""} inputMode="numeric" autoComplete="off" />
        </Field>
      </FormGrid>
      <Field
        id={`${prefix}products`}
        label={f.products_ordered}
        optional
        help={copy.catalogue.help.collectionProducts}
        error={fieldError(error, "products")}
      >
        <Textarea name="products" defaultValue={collection?.products.join("\n") ?? ""} rows={5} className="font-mono" />
      </Field>
      <Field id={`${prefix}description`} label={f.description} optional error={fieldError(error, "description")}>
        <Textarea name="description" defaultValue={collection?.description ?? ""} rows={3} />
      </Field>
      <Checkbox name="is_active" defaultChecked={collection?.is_active ?? true}>
        {copy.catalogue.collectionShown}
      </Checkbox>
    </>
  );
}

/** A collection's fields as the form holds them. */
export function collectionBody(form: FormData) {
  return {
    name: formText(form, "name"),
    slug: formText(form, "slug"),
    position: Number(formText(form, "position") || 0),
    products: slugsOf(String(form.get("products") ?? "")),
    description: String(form.get("description") ?? ""),
    is_active: form.get("is_active") === "on",
  };
}

const COLLECTION_LABELS = {
  name: copy.catalogue.fields.name_collection,
  slug: copy.catalogue.fields.slug,
  position: copy.catalogue.fields.order,
  products: copy.catalogue.fields.products_ordered,
  description: copy.catalogue.fields.description,
};

export function CollectionsList({ rows, canChange }: { rows: CatalogueCollection[]; canChange: boolean }) {
  const router = useRouter();
  if (!rows.length) return <p className="m-0 text-muted-foreground">{copy.catalogue.noCollections}</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0" aria-label={copy.catalogue.collectionsTitle}>
      {rows.map((collection) => (
        <li
          key={collection.slug}
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3"
        >
          <span className="flex min-w-0 flex-col">
            <span className="font-semibold">{collection.name}</span>
            <span className="text-[13px] text-muted-foreground">
              <span className="font-mono">{collection.slug}</span> ·{" "}
              {copy.catalogue.productCount(collection.products.length)} ·{" "}
              {collection.is_active ? copy.catalogue.shown : copy.catalogue.hidden}
            </span>
          </span>
          {canChange ? (
            <FormDialog
              wide
              triggerLabel={copy.catalogue.editCollection}
              title={copy.catalogue.editCollectionTitle(collection.name)}
              submitLabel={copy.common.save}
              labels={COLLECTION_LABELS}
              success={copy.catalogue.saved}
              onSubmit={(form) => updateCollection(collection.slug, collectionBody(form))}
              onDone={() => router.refresh()}
            >
              {(prefix, error) => <CollectionFields prefix={prefix} collection={collection} error={error} />}
            </FormDialog>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function NewCollectionForm() {
  return (
    <ActionForm
      id="new-collection"
      submitLabel={copy.catalogue.makeCollection}
      success={copy.catalogue.collectionMade}
      labels={COLLECTION_LABELS}
      onSubmit={(form) => createCollection(collectionBody(form))}
    >
      {(error) => <CollectionFields prefix="new-collection-" collection={null} error={error} />}
    </ActionForm>
  );
}
