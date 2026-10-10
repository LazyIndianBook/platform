// Access: account numbers read from what is typed; one row chosen is extended or revoked at once with a reason, more
// go through a bulk job; the learner's page a link that is never prefetched (every opening is logged).
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { type CourseEntitlement, extendEntitlement, revokeEntitlement } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { AccessTable, accountsOf } from "./access";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  extendEntitlement: vi.fn(),
  revokeEntitlement: vi.fn(),
}));

const words = copy.course.access;

const row = (id: number, user: number, extra: Partial<CourseEntitlement> = {}): CourseEntitlement => ({
  id,
  user: { id: user, name: `Learner ${user}`, email: "le•••@example.com", is_minor: user === 7101 },
  subject: "PHY",
  subject_name: "Physics",
  source: "grant",
  reference: "",
  valid_until: "2026-11-30",
  note: "",
  state: "active",
  revoked_at: null,
  created: "2026-09-01T10:00:00Z",
  modified: "2026-09-01T10:00:00Z",
  can_extend: true,
  can_revoke: true,
  ...extra,
});

const renderTable = (permissions: string[]) =>
  render(
    <ManifestProvider manifest={manifestWith(permissions)}>
      <AccessTable rows={[row(801, 7101), row(802, 7102)]} next={null} previous={null} views={null} />
    </ManifestProvider>,
  );

beforeEach(() => {
  vi.mocked(extendEntitlement).mockReset();
  vi.mocked(revokeEntitlement).mockReset();
  navigation.router.refresh = vi.fn();
});

describe("accountsOf", () => {
  it("reads whole account numbers, each once, whatever separates them", () => {
    expect(accountsOf("7101, #7102\n7103 x 7101;7104")).toEqual([7101, 7102, 7103, 7104]);
    expect(accountsOf("")).toEqual([]);
  });
});

describe("AccessTable", () => {
  it("extends one row at once, with the days and a reason", async () => {
    vi.mocked(extendEntitlement).mockResolvedValueOnce(row(801, 7101) as never);
    renderTable([P.accessView, P.accessExtend]);
    await userEvent.click(screen.getByRole("checkbox", { name: words.choose(copy.course.learner.account(7101)) }));
    await userEvent.click(screen.getByRole("button", { name: words.extend(1) }));
    const dialog = screen.getByRole("dialog");
    const days = within(dialog).getByLabelText(words.days);
    await userEvent.clear(days);
    await userEvent.type(days, "45");
    await userEvent.type(within(dialog).getByLabelText(copy.common.reason), "The book came late");
    await userEvent.click(within(dialog).getByRole("button", { name: words.extend(1) }));
    expect(extendEntitlement).toHaveBeenCalledWith(801, 45, "The book came late");
    expect(navigation.router.refresh).toHaveBeenCalled();
  });

  it("offers the bulk job for more than one row, and nothing without the permission", async () => {
    const { unmount } = renderTable([P.accessView, P.accessExtend]);
    await userEvent.click(screen.getByRole("checkbox", { name: words.page }));
    expect(screen.getByRole("button", { name: words.extend(2) })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: words.revoke(2) })).toBeInTheDocument();
    unmount();
    renderTable([P.accessView]);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("links each learner's page without prefetching it", () => {
    renderTable([P.accessView]);
    const links = screen.getAllByRole("link", { name: new RegExp(words.openLearner) });
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/course/learners/7101/",
      "/course/learners/7102/",
    ]);
  });
});
