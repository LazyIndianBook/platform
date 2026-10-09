// The list primitive: filters and sort live in the address (the cursor dropped when they change), saved views carry
// their filters, sort and columns (saved, updated through the API), the column chooser, the keyboard (j, k, x, /, and
// off when single-key shortcuts are off), and bulk actions as a background job with the rows that failed.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { ApiError } from "@/lib/api/errors";
import { createSavedView, getJob, type SavedView, startJob, updateSavedView } from "@/lib/api/staff";
import { setShortcutsEnabled } from "@/lib/shortcuts";
import { manifestWith } from "@/test/fixtures";

import { navigation } from "@/test/navigation";
import { type Column, DataTable } from "./data-table";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  startJob: vi.fn(),
  getJob: vi.fn(),
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
  { key: "kind", label: "Kind", render: (row) => row.kind, sort: "kind" },
  { key: "extra", label: "Extra", render: () => "more", hidden: true },
];

function renderTable(views: SavedView[] = []) {
  return render(
    <ManifestProvider manifest={manifestWith([])}>
      <DataTable
        listKey="things"
        caption="Things"
        rows={ROWS}
        columns={COLUMNS}
        rowId={(row) => row.id}
        rowLabel={(row) => row.name}
        rowHref={(row) => `/things/${row.id}/`}
        next="c2"
        previous={null}
        views={views}
        filters={[
          { name: "q", label: "Search", type: "search" },
          { name: "kind", label: "Kind", type: "select", options: [{ value: "a", label: "Kind A" }] },
        ]}
        bulk={[{ action: "things.done", label: "Mark done" }]}
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
  vi.mocked(startJob).mockReset();
  vi.mocked(getJob).mockReset();
  vi.mocked(createSavedView).mockReset();
  vi.mocked(updateSavedView).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the address", () => {
  it("takes the filters and drops the cursor", async () => {
    navigation.search = new URLSearchParams("cursor=abc&sort=kind");
    renderTable();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search" }), "first{Enter}");
    expect(replace).toHaveBeenLastCalledWith("/inbox/?sort=kind&q=first", { scroll: false });
    // a choice applies at once, with what the other fields hold
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Kind" }), "a");
    expect(replace).toHaveBeenLastCalledWith("/inbox/?sort=kind&q=first&kind=a", { scroll: false });
  });

  it("sorts by a column, then the other way, then not", async () => {
    const { rerender } = renderTable();
    await userEvent.click(screen.getByRole("button", { name: /^Kind/ }));
    expect(replace).toHaveBeenLastCalledWith("/inbox/?sort=kind", { scroll: false });
    navigation.search = new URLSearchParams("sort=kind");
    rerender(<></>);
    renderTable();
    expect(screen.getByRole("columnheader", { name: /Kind/ })).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(screen.getByRole("button", { name: /^Kind, sorted, first to last/ }));
    expect(replace).toHaveBeenLastCalledWith("/inbox/?sort=-kind", { scroll: false });
  });

  it("pages with the cursor, keeping the filters", () => {
    navigation.search = new URLSearchParams("kind=a");
    renderTable();
    expect(screen.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/inbox/?kind=a&cursor=c2");
  });
});

describe("saved views", () => {
  const view: SavedView = {
    id: "5",
    list_key: "things",
    name: "Mine",
    filters: { kind: "a" },
    columns: ["name"],
    sort: "-kind",
    shared_with_role: "SUPPORT",
  };

  it("are links that carry their filters and sort, and set the columns", () => {
    navigation.search = new URLSearchParams("view=5&kind=a&sort=-kind");
    renderTable([view]);
    const tab = screen.getByRole("link", { name: /^Mine/ });
    expect(tab).toHaveAttribute("href", "/inbox/?view=5&kind=a&sort=-kind");
    expect(tab).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("columnheader", { name: /Kind/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Update this view" })).toBeNull();
  });

  it("offer an update when the filters differ, and send it", async () => {
    navigation.search = new URLSearchParams("view=5&kind=b&sort=-kind");
    vi.mocked(updateSavedView).mockResolvedValueOnce({ ...view, filters: { kind: "b" } });
    renderTable([view]);
    await userEvent.click(screen.getByRole("button", { name: "Update this view" }));
    expect(updateSavedView).toHaveBeenCalledWith("5", {
      filters: { q: "", kind: "b" },
      columns: ["name"],
      sort: "-kind",
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("save the list as it stands, shared with a role, and open it", async () => {
    navigation.search = new URLSearchParams("kind=a");
    vi.mocked(createSavedView).mockResolvedValueOnce({ ...view, id: "9", name: "Kind A things" });
    renderTable();
    await userEvent.click(screen.getByRole("button", { name: "Save as a view" }));
    const dialog = screen.getByRole("dialog", { name: "Save as a view" });
    await userEvent.type(within(dialog).getByLabelText("Name of the view"), "Kind A things");
    await userEvent.selectOptions(within(dialog).getByLabelText("Share with"), "SUPPORT");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(createSavedView).toHaveBeenCalledWith({
      list_key: "things",
      name: "Kind A things",
      shared_with_role: "SUPPORT",
      filters: { q: "", kind: "a" },
      columns: ["name", "kind"],
      sort: "",
    });
    expect(push).toHaveBeenCalledWith("/inbox/?view=9&kind=a&sort=-kind");
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
  it("moves with j and k, selects with x and searches with /", () => {
    renderTable();
    const links = () => screen.getAllByRole("link", { name: /^(First|Second|Third)$/ });
    fireEvent.keyDown(document.body, { key: "j" });
    expect(links()[0]).toHaveFocus();
    fireEvent.keyDown(document.body, { key: "j" });
    expect(links()[1]).toHaveFocus();
    fireEvent.keyDown(document.body, { key: "k" });
    expect(links()[0]).toHaveFocus();
    fireEvent.keyDown(document.body, { key: "x" });
    expect(screen.getByRole("checkbox", { name: "Select First" })).toBeChecked();
    expect(screen.getByRole("region", { name: "1 selected" })).toBeInTheDocument();
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

describe("bulk actions", () => {
  it("run as a job and list the rows that failed", async () => {
    vi.mocked(startJob).mockResolvedValueOnce({ job_id: "41" });
    vi.mocked(getJob).mockResolvedValueOnce({
      id: "41",
      state: "done",
      done: 2,
      total: 2,
      errors: [{ id: "3", label: "Third", message: "Close it from its own page." }],
      result_url: null,
    });
    renderTable();
    await userEvent.click(screen.getByRole("checkbox", { name: "Select First" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Select Third" }));
    const bar = screen.getByRole("region", { name: "2 selected" });
    await userEvent.click(within(bar).getByRole("button", { name: "Mark done" }));
    expect(startJob).toHaveBeenCalledWith({ action: "things.done", ids: ["1", "3"] });
    await waitFor(() => expect(within(bar).getAllByText("Done: 1, 1 row failed").length).toBeGreaterThan(0));
    expect(within(bar).getByText("Third")).toBeInTheDocument();
    expect(within(bar).getByText(/Close it from its own page\./)).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
  });

  it("stay busy while their job runs: a second press starts no second job on the same rows", async () => {
    vi.mocked(startJob).mockResolvedValueOnce({ job_id: "42" });
    let finish: (job: Awaited<ReturnType<typeof getJob>>) => void = () => undefined;
    vi.mocked(getJob).mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
    renderTable();
    await userEvent.click(screen.getByRole("checkbox", { name: "Select First" }));
    const mark = within(screen.getByRole("region", { name: "1 selected" })).getByRole("button", { name: "Mark done" });
    await userEvent.click(mark);
    await waitFor(() => expect(getJob).toHaveBeenCalled());
    expect(mark).toHaveAttribute("aria-busy", "true"); // the job was made, and it runs
    await userEvent.click(mark);
    expect(startJob).toHaveBeenCalledTimes(1);
    await act(async () => finish({ id: "42", state: "done", done: 1, total: 1, errors: [], result_url: null }));
    expect(refresh).toHaveBeenCalled();
  });

  it("say when a second person must approve the job", async () => {
    vi.mocked(startJob).mockRejectedValueOnce(
      new ApiError(403, "approval_required", "Too many rows.", {}, { change_request: { id: 9 } }),
    );
    renderTable();
    await userEvent.click(screen.getByRole("checkbox", { name: "Select every row on this page" }));
    await userEvent.click(
      within(screen.getByRole("region", { name: "3 selected" })).getByRole("button", { name: "Mark done" }),
    );
    expect(await screen.findByText("A second person needs to approve this")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Open the change request/ })).toHaveAttribute("href", "/approvals/9/");
  });
});
