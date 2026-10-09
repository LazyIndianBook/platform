"use client";

// A list's saved views (GET/POST saved-views/, PATCH/DELETE saved-views/{id}/): "Everything" and each view as a row
// of links (a view's link carries its filters, so it works as a bookmark too), then Save as a view (its name,
// and whether everyone with one of the person's roles sees it), Update this view when the filters or columns differ
// from it, and Delete this view.
import { cn } from "cn";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useManifest } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import { createSavedView, deleteSavedView, rolesOf, type SavedView, updateSavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export type ListState = { filters: Record<string, string>; columns: string[] };

/** The address of a view: its filters, and its id. */
export function viewHref(pathname: string, view: Pick<SavedView, "id" | "filters">): string {
  const params = new URLSearchParams();
  params.set("view", String(view.id));
  for (const [name, value] of Object.entries(view.filters)) if (value) params.set(name, value);
  return `${pathname}?${params}`;
}

const same = (a: Record<string, string>, b: Record<string, string>) => {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  return [...keys].every((key) => (a[key] ?? "") === (b[key] ?? ""));
};

export function viewDiffers(view: SavedView, current: ListState): boolean {
  return (
    !same(view.filters, current.filters) ||
    (view.columns.length > 0 && view.columns.join(",") !== current.columns.join(","))
  );
}

type SavedViewsProps = {
  listKey: string;
  pathname: string;
  views: SavedView[];
  active: SavedView | null;
  current: ListState;
};

export function SavedViews({ listKey, pathname, views, active, current }: SavedViewsProps) {
  const id = useId();
  const router = useRouter();
  const manifest = useManifest();
  const [saving, setSaving] = useState(false);
  const save = useAction();
  const update = useAction();
  const differs = active ? viewDiffers(active, current) : false;
  // a view shared by a colleague is read-only here (the API changes only your own)
  const own = active?.owner === manifest.user.id;
  const can = (permission: string) => has(manifest, permission);
  const tab = (selected: boolean) =>
    cn(
      "inline-flex min-h-11 items-center gap-1.5 px-3.5 text-[15px] font-semibold whitespace-nowrap text-muted-foreground no-underline hover:text-foreground",
      selected && "text-foreground shadow-[inset_0_-2px_0_var(--red-ink)]",
    );

  return (
    <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2 border-b border-border">
      <nav aria-label={copy.views.label} className="min-w-0 overflow-x-auto">
        <ul className="m-0 flex list-none p-0">
          <li>
            <Link href={pathname} aria-current={!active ? "page" : undefined} className={tab(!active)}>
              {copy.views.standard}
            </Link>
          </li>
          {views.map((view) => (
            <li key={view.id}>
              <Link
                href={viewHref(pathname, view)}
                aria-current={active?.id === view.id ? "page" : undefined}
                className={tab(active?.id === view.id)}
              >
                {view.name}
                {view.role ? (
                  <span className="font-mono text-[11px] font-medium tracking-[0.04em] uppercase">
                    <span className="sr-only">, </span>
                    {copy.views.shared}
                  </span>
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="flex flex-wrap items-center gap-2 pb-1.5">
        {active && own && differs && can(P.savedViewsChange) ? (
          <Button
            variant="secondary"
            size="sm"
            busy={update.busy}
            onClick={() =>
              update.run(async () => {
                await updateSavedView(active.id, current);
                toast.success(copy.views.updated);
                router.refresh();
              })
            }
          >
            {copy.views.update}
          </Button>
        ) : null}
        {active && own && can(P.savedViewsDelete) ? (
          <ConfirmDialog
            triggerLabel={copy.views.remove}
            triggerVariant="ghost"
            title={copy.views.removeTitle(active.name)}
            text={copy.views.removeText}
            confirmLabel={copy.views.remove}
            success={copy.views.removed}
            onConfirm={() => deleteSavedView(active.id)}
            onDone={() => {
              router.push(pathname);
              router.refresh();
            }}
          />
        ) : null}
        <Dialog
          open={saving}
          onOpenChange={(next) => {
            setSaving(next);
            if (!next) save.setError(null);
          }}
        >
          {can(P.savedViewsAdd) ? (
            <Button variant="secondary" size="sm" onClick={() => setSaving(true)}>
              {copy.views.save}
            </Button>
          ) : null}
          <DialogContent>
            <DialogHeader>{copy.views.save}</DialogHeader>
            <form
              noValidate
              className="flex flex-col gap-3.5"
              onSubmit={async (event) => {
                event.preventDefault();
                const form = new FormData(event.currentTarget);
                await save.run(async () => {
                  const made = await createSavedView({
                    list_key: listKey,
                    name: String(form.get("name") ?? "").trim(),
                    role: String(form.get("role") ?? ""),
                    sort: "",
                    ...current,
                  });
                  setSaving(false);
                  toast.success(copy.views.saved);
                  router.push(viewHref(pathname, made));
                  router.refresh();
                });
              }}
            >
              <DialogDescription className="m-0 text-[15px] text-muted-foreground">
                {copy.views.saveText}
              </DialogDescription>
              <ErrorSummary error={save.error} idPrefix={`${id}-`} labels={{ name: copy.views.name }} />
              <Field id={`${id}-name`} label={copy.views.name} error={fieldError(save.error, "name")}>
                <Input name="name" autoComplete="off" aria-required="true" maxLength={80} />
              </Field>
              <Field id={`${id}-role`} label={copy.views.share} error={fieldError(save.error, "role")}>
                <Select name="role" defaultValue="">
                  <option value="">{copy.views.onlyMe}</option>
                  {rolesOf(manifest).map((role) => (
                    <option key={role.name} value={role.name}>
                      {copy.views.role(labelOf(copy.people.roleNames, role.name))}
                    </option>
                  ))}
                </Select>
              </Field>
              <DialogFooter>
                {/* a plain button, not the dialog's safe one: the dialog opens on the name */}
                <Button variant="secondary" onClick={() => setSaving(false)}>
                  {copy.common.cancel}
                </Button>
                <Button type="submit" busy={save.busy}>
                  {copy.common.save}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>
      {update.error ? (
        <div className="basis-full pb-3">
          <ErrorSummary error={update.error} />
        </div>
      ) : null}
    </div>
  );
}
