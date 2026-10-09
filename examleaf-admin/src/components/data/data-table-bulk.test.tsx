// The list's additions for lists that act on rows: fixed views as links that keep their param with the filters (and
// with a saved view), a checkbox per row and one for the page with the bulk bar for the chosen rows, x to choose the
// active row and Space to look at it.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { setShortcutsEnabled } from "@/lib/shortcuts";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { type Column, DataTable } from "./data-table";

type Row = { id: string; name: string };
const ROWS: Row[] = [
  { id: "1", name: "First" },
  { id: "2", name: "Second" },
  { id: "3", name: "Third" },
];
const COLUMNS: Column<Row>[] = [
  { key: "name", label: "Name", render: (row) => row.name },
  { key: "id", label: "Id", render: (row) => row.id },
];

function renderList(onPeek = vi.fn(), bulk = vi.fn((rows: Row[]) => <p>{rows.map((row) => row.name).join(" + ")}</p>)) {
  render(
    <ManifestProvider manifest={manifestWith([])}>
      <DataTable
        listKey="things"
        caption="Things"
        rows={ROWS}
        columns={COLUMNS}
        rowId={(row) => row.id}
        rowHref={(row) => `/things/${row.id}/`}
        next={null}
        previous={null}
        presets={{
          name: "tab",
          label: "Show",
          all: "All",
          options: [
            { value: "open", label: "Open" },
            { value: "done", label: "Done" },
          ],
        }}
        filters={[{ name: "q", label: "Search", type: "search" }]}
        selection={{ label: (row) => `Select ${row.name}`, page: "Select the page", bulk }}
        onPeek={onPeek}
      />
    </ManifestProvider>,
  );
  return { onPeek, bulk };
}

beforeEach(() => {
  navigation.pathname = "/things/";
  navigation.search = new URLSearchParams("q=first&cursor=c3");
  navigation.router.replace = vi.fn();
  navigation.router.push = vi.fn();
  setShortcutsEnabled(true);
});

describe("DataTable presets", () => {
  it("links each fixed view with the filters kept, the cursor dropped and the current one marked", () => {
    navigation.search = new URLSearchParams("q=first&cursor=c3&tab=open");
    renderList();
    const views = screen.getByRole("navigation", { name: "Show" });
    expect(within(views).getByRole("link", { name: "Open" })).toHaveAttribute("aria-current", "page");
    expect(within(views).getByRole("link", { name: "Done" })).toHaveAttribute("href", "/things/?q=first&tab=done");
    expect(within(views).getByRole("link", { name: "All" })).toHaveAttribute("href", "/things/?q=first");
  });
});

describe("DataTable selection", () => {
  it("chooses rows and the page, and draws the bulk bar for the chosen rows only", async () => {
    const user = userEvent.setup();
    const { bulk } = renderList();
    expect(bulk).not.toHaveBeenCalled();
    await user.click(screen.getByRole("checkbox", { name: "Select Second" }));
    expect(screen.getAllByText("Second")).toHaveLength(2); // the row and the bar
    const page = screen.getByRole("checkbox", { name: "Select the page" }) as HTMLInputElement;
    expect(page.indeterminate).toBe(true);
    await user.click(page);
    expect(screen.getByText("First + Second + Third")).toBeInTheDocument();
    await user.click(page);
    expect(screen.queryByText(/ \+ /)).not.toBeInTheDocument();
  });

  it("x chooses the active row and Space looks at it, while shortcuts are on", async () => {
    const { onPeek } = renderList();
    const second = screen.getByRole("link", { name: "Second" });
    act(() => second.focus());
    fireEvent.keyDown(second, { key: "x" });
    expect(screen.getByRole("checkbox", { name: "Select Second" })).toBeChecked();
    fireEvent.keyDown(second, { key: " " });
    expect(onPeek).toHaveBeenCalledWith(ROWS[1]);
    act(() => setShortcutsEnabled(false));
    fireEvent.keyDown(second, { key: " " });
    expect(onPeek).toHaveBeenCalledTimes(1);
  });
});
