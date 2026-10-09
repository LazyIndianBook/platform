// The list primitive: filters live in the address (the cursor dropped when they change), saved views carry their
// filters and columns (saved and updated through the API, a colleague's shared one read-only), the column chooser and
// the keyboard (j, k, /, and off when single-key shortcuts are off).
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { createSavedView, type SavedView, updateSavedView } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { setShortcutsEnabled } from "@/lib/shortcuts";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { type Column, DataTable } from "./data-table";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  createSavedView: vi.fn(),
  updateSavedView: vi.fn(),
  deleteSavedView: vi.fn(),
}));

type Row = { id: string; name: string; kind: string };
const ROWS: Row[] = [
  { id: "1", name: "First", kind: "a" },
  { id: "2", name: "Second", kind: "b" },
  { id: "3", name: "Third", kind: "a" },
];
const COLUMNS: Column<Row>[] = [
  { key: "name", label: "Name", render: (row) => row.name },
  { key: "kind", label: "Kind", render: (row) => row.kind },
  { key: "extra", label: "Extra", render: () => "more", hidden: true },
];
const VIEWS = [P.savedViewsView, P.savedViewsAdd, P.savedViewsChange, P.savedViewsDelete];

function renderTable(views: SavedView[] = [], permissions = VIEWS) {
  return render(
    <ManifestProvider manifest={manifestWith(permissions)}>
      <DataTable
        listKey="things"
        caption="Things"
        rows={ROWS}
        columns={COLUMNS}
        rowId={(row) => row.id}
        rowHref={(row) => `/things/${row.id}/`}
        next="c2"
        previous={null}
        views={views}
        filters={[
          { name: "q", label: "Search", type: "search" },
          { name: "kind", label: "Kind", type: "select", options: [{ value: "a", label: "Kind A" }] },
        ]}
      />
    </ManifestProvider>,
  );
}

type Replace = (href: string, options?: { scroll?: boolean }) => void;
let replace = vi.fn<Replace>();
let push = vi.fn<(href: string) => void>();
let refresh = vi.fn<() => void>();

beforeEach(() => {
  replace = vi.fn<Replace>();
  push = vi.fn<(href: string) => void>();
  refresh = vi.fn<() => void>();
  navigation.pathname = "/inbox/";
  navigation.search = new URLSearchParams();
  navigation.router.replace = replace;
  navigation.router.push = push;
  navigation.router.refresh = refresh;
  setShortcutsEnabled(true);
  window.localStorage.clear();
  vi.mocked(createSavedView).mockReset();
  vi.mocked(updateSavedView).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the address", () => {
  it("takes the filters and drops the cursor", async () => {
    navigation.search = new URLSearchParams("cursor=abc");
    renderTable();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search" }), "first{Enter}");
    expect(replace).toHaveBeenLastCalledWith("/inbox/?q=first", { scroll: false });
    // a choice applies at once, with what the other fields hold
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Kind" }), "a");
    expect(replace).toHaveBeenLastCalledWith("/inbox/?q=first&kind=a", { scroll: false });
  });

  it("pages with the cursor, keeping the filters", () => {
    navigation.search = new URLSearchParams("kind=a");
    renderTable();
    expect(screen.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/inbox/?kind=a&cursor=c2");
  });
});

describe("saved views", () => {
  const view: SavedView = {
    id: 5,
    owner: 7,
    role: "SUPPORT",
    list_key: "things",
    name: "Mine",
    filters: { kind: "a" },
    columns: ["name"],
    sort: "",
    created: "2026-10-01T10:00:00Z",
    modified: "2026-10-01T10:00:00Z",
  };

  it("are links that carry their filters, and set the columns", () => {
    navigation.search = new URLSearchParams("view=5&kind=a");
    renderTable([view]);
    const tab = screen.getByRole("link", { name: /^Mine/ });
    expect(tab).toHaveAttribute("href", "/inbox/?view=5&kind=a");
    expect(tab).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("columnheader", { name: /Kind/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Update this view" })).toBeNull();
  });

  it("offer an update when the filters differ, and send it", async () => {
    navigation.search = new URLSearchParams("view=5&kind=b");
    vi.mocked(updateSavedView).mockResolvedValueOnce({ ...view, filters: { kind: "b" } });
    renderTable([view]);
    await userEvent.click(screen.getByRole("button", { name: "Update this view" }));
    expect(updateSavedView).toHaveBeenCalledWith(5, { filters: { q: "", kind: "b" }, columns: ["name"] });
    expect(refresh).toHaveBeenCalled();
  });

  it("leave a colleague's shared view as it is: neither update nor delete", () => {
    navigation.search = new URLSearchParams("view=5&kind=b");
    renderTable([{ ...view, owner: 9002 }]);
    expect(screen.queryByRole("button", { name: "Update this view" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete this view" })).toBeNull();
  });

  it("save the list as it stands, shared with a role, and open it", async () => {
    navigation.search = new URLSearchParams("kind=a");
    vi.mocked(createSavedView).mockResolvedValueOnce({ ...view, id: 9, name: "Kind A things" });
    renderTable();
    await userEvent.click(screen.getByRole("button", { name: "Save as a view" }));
    const dialog = screen.getByRole("dialog", { name: "Save as a view" });
    await userEvent.type(within(dialog).getByLabelText("Name of the view"), "Kind A things");
    await userEvent.selectOptions(within(dialog).getByLabelText("Share with"), "SUPPORT");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(createSavedView).toHaveBeenCalledWith({
      list_key: "things",
      name: "Kind A things",
      role: "SUPPORT",
      sort: "",
      filters: { q: "", kind: "a" },
      columns: ["name", "kind"],
    });
    expect(push).toHaveBeenCalledWith("/inbox/?view=9&kind=a");
  });

  it("offer no saving without the permission to add one", () => {
    renderTable([], [P.savedViewsView]);
    expect(screen.queryByRole("button", { name: "Save as a view" })).toBeNull();
  });
});

describe("columns", () => {
  it("are chosen and kept on this device for the plain list", async () => {
    renderTable();
    expect(screen.queryByRole("columnheader", { name: "Extra" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Columns" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Extra" }));
    expect(screen.getByRole("columnheader", { name: "Extra" })).toBeInTheDocument();
    expect(window.localStorage.getItem("examleaf-admin:columns:things")).toBe("name,kind,extra");
  });
});

describe("the keyboard", () => {
  it("moves with j and k and searches with /", () => {
    renderTable();
    const links = () => screen.getAllByRole("link", { name: /^(First|Second|Third)$/ });
    fireEvent.keyDown(document.body, { key: "j" });
    expect(links()[0]).toHaveFocus();
    fireEvent.keyDown(document.body, { key: "j" });
    expect(links()[1]).toHaveFocus();
    fireEvent.keyDown(document.body, { key: "k" });
    expect(links()[0]).toHaveFocus();
    fireEvent.keyDown(document.body, { key: "/" });
    expect(screen.getByRole("searchbox", { name: "Search" })).toHaveFocus();
  });

  it("does nothing with single-key shortcuts off, or while typing", () => {
    renderTable();
    act(() => setShortcutsEnabled(false));
    fireEvent.keyDown(document.body, { key: "j" });
    expect(document.body).toHaveFocus();
    act(() => setShortcutsEnabled(true));
    const search = screen.getByRole("searchbox", { name: "Search" });
    search.focus();
    fireEvent.keyDown(search, { key: "j" });
    expect(search).toHaveFocus();
  });
});
