"use client";

// A list's filters, mirrored in the address (DataTable owns the address): the search box (also "/"), choices that
// apply as soon as they change, dates once a whole date is picked, other text on Enter or Apply. The fields show what
// the address says, so Back, a bookmark or a link from a colleague opens the same list.
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { copy } from "@/lib/copy";

export type FilterDef =
  | { name: string; label: string; type: "search" }
  | { name: string; label: string; type: "select"; options: { value: string; label: string }[]; any?: string }
  | { name: string; label: string; type: "text" | "date" };

export const SEARCH_ID = "list-search";

type FilterBarProps = {
  filters: FilterDef[];
  values: Record<string, string>;
  onApply: (values: Record<string, string>) => void;
};

export function FilterBar({ filters, values, onApply }: FilterBarProps) {
  const read = (form: HTMLFormElement) =>
    Object.fromEntries(
      filters.map((filter) => [filter.name, String(new FormData(form).get(filter.name) ?? "").trim()]),
    );
  const hasText = filters.some((filter) => filter.type === "search" || filter.type === "text");
  // a new address puts its values back into the fields
  const key = filters.map((filter) => values[filter.name] ?? "").join("\u0000");

  return (
    <form
      key={key}
      role="search"
      aria-label={copy.filters.label}
      noValidate
      className="flex flex-wrap items-end gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        onApply(read(event.currentTarget));
      }}
    >
      {filters.map((filter) => {
        const id = filter.type === "search" ? SEARCH_ID : `filter-${filter.name}`;
        const field = (control: React.ReactNode) => (
          <div key={filter.name} className="flex min-w-0 flex-col gap-1">
            <label htmlFor={id} className="text-sm font-semibold">
              {filter.label}
            </label>
            {control}
          </div>
        );
        switch (filter.type) {
          case "search":
            return (
              <div key={filter.name} className="flex min-w-0 flex-[1_1_16rem] flex-col gap-1">
                <label htmlFor={id} className="text-sm font-semibold">
                  {filter.label}
                </label>
                <div className="relative">
                  <Search
                    aria-hidden="true"
                    className="pointer-events-none absolute top-3.5 left-3 size-5 text-muted-foreground"
                  />
                  <Input
                    id={id}
                    name={filter.name}
                    type="search"
                    defaultValue={values[filter.name] ?? ""}
                    autoComplete="off"
                    className="min-h-11 pl-10"
                    aria-keyshortcuts="/"
                  />
                </div>
              </div>
            );
          case "select":
            return field(
              <Select
                id={id}
                name={filter.name}
                defaultValue={values[filter.name] ?? ""}
                className="min-h-11 min-w-40"
                onChange={(event) => onApply(read(event.currentTarget.form!))}
              >
                <option value="">{filter.any ?? copy.filters.any}</option>
                {filter.options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>,
            );
          case "date":
            return field(
              <Input
                id={id}
                name={filter.name}
                type="date"
                defaultValue={values[filter.name] ?? ""}
                className="min-h-11 w-auto"
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  if (!value || /^\d{4}-\d{2}-\d{2}$/.test(value)) onApply(read(event.currentTarget.form!));
                }}
              />,
            );
          default:
            return field(
              <Input
                id={id}
                name={filter.name}
                defaultValue={values[filter.name] ?? ""}
                autoComplete="off"
                className="min-h-11 w-44"
              />,
            );
        }
      })}
      {hasText ? (
        <Button type="submit" variant="secondary" size="sm">
          {copy.filters.apply}
        </Button>
      ) : null}
    </form>
  );
}
