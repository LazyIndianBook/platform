// The bulk bar on the customers' list: only the actions the person may start are drawn; every action is asked in two
// steps, a check that changes nothing (a dry run that says how many accounts it would change, how many it would leave
// alone, how many are children's and whether a second person has to approve) and then the run, which is not offered
// before the check, nor when the check found nothing to change; the API's refusal (a reason missing) shows beside its
// field.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { ApiError } from "@/lib/api/errors";
import { type Job, startCustomersJob } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { customerWith } from "@/test/customers";
import { manifestWith } from "@/test/fixtures";

import { UsersBulk } from "./users-bulk";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  startCustomersJob: vi.fn(),
}));

// the job's progress is the job-progress component's own test; here a finished check is what its job says (it tells
// once per job, as the real one does: its onDone is read when the job ends, not each time the page draws)
const ended = vi.hoisted(() => ({ job: null as unknown }));
vi.mock("@/components/data/job-progress", async () => {
  const { useEffect, useRef } = await import("react");
  return {
    JobProgress: ({ job, onDone }: { job: { id: number }; onDone?: (job: unknown) => void }) => {
      const finished = useRef(onDone);
      useEffect(() => {
        finished.current = onDone;
      });
      useEffect(() => {
        finished.current?.(ended.job);
      }, [job.id]);
      return <p>{`Progress of job ${job.id}`}</p>;
    },
  };
});

const job = (extra: Partial<Job> = {}): Job => ({
  id: 31,
  kind: "bulk_action",
  state: "done",
  dry_run: true,
  params: {},
  done: 2,
  total: 2,
  errors: [],
  result: { outcomes: { valid: 2 }, waiting: [] },
  result_url: null,
  change_request_id: null,
  cancel_requested: false,
  started_by: 7,
  created: "2026-10-09T10:00:00Z",
  started_at: "2026-10-09T10:00:01Z",
  finished_at: "2026-10-09T10:00:02Z",
  ...extra,
});

const rows = [customerWith({ id: 7101 }), customerWith({ id: 7102 })];

function renderBar(permissions: string[], handlers = { clear: vi.fn(), onJob: vi.fn() }) {
  render(
    <ManifestProvider manifest={manifestWith(permissions)}>
      <UsersBulk rows={rows} clear={handlers.clear} onJob={handlers.onJob} />
    </ManifestProvider>,
  );
  return handlers;
}

beforeEach(() => {
  vi.mocked(startCustomersJob).mockReset();
  ended.job = job();
});

describe("the bulk bar", () => {
  it("counts the chosen accounts and draws only what the person may start", () => {
    renderBar([P.usersEndSessions, P.usersResendVerification]);
    expect(screen.getByRole("status")).toHaveTextContent("2 accounts chosen");
    expect(screen.getByRole("button", { name: "Sign out everywhere" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Send the parents' links again" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Suspend" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Lift the suspension" })).toBeNull();
  });

  it("draws the suspension for whoever holds that permission, and nothing else", () => {
    renderBar([P.usersSuspend]);
    expect(screen.getByRole("button", { name: "Suspend" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Lift the suspension" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Sign out everywhere" })).toBeNull();
  });
});

describe("an action in two steps", () => {
  const open = async () => {
    await userEvent.click(screen.getByRole("button", { name: "Sign out everywhere" }));
    return screen.getByRole("dialog", { name: "Sign 2 accounts out everywhere?" });
  };

  it("offers the run only after a check that found something to change, then runs it", async () => {
    const handlers = renderBar([P.usersEndSessions]);
    vi.mocked(startCustomersJob)
      .mockResolvedValueOnce(job({ dry_run: true }))
      .mockResolvedValueOnce(job({ id: 32, dry_run: false, state: "running" }));
    const dialog = await open();
    const run = within(dialog).getByRole("button", { name: "Run it for 2 accounts" });
    expect(run).toBeDisabled();

    await userEvent.type(within(dialog).getByLabelText("Reason"), "A shared computer at the school.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Check first" }));
    expect(startCustomersJob).toHaveBeenLastCalledWith(
      "user.end_sessions",
      [7101, 7102],
      "A shared computer at the school.",
      true,
    );
    expect(await within(dialog).findByText("2 accounts can be changed.")).toBeVisible();
    expect(within(dialog).getByText("It runs at once, within your limits.")).toBeVisible();
    expect(run).toBeEnabled();

    await userEvent.click(run);
    expect(startCustomersJob).toHaveBeenLastCalledWith(
      "user.end_sessions",
      [7101, 7102],
      "A shared computer at the school.",
      false,
    );
    expect(handlers.onJob).toHaveBeenCalledWith(expect.objectContaining({ id: 32 }), "Sign out everywhere");
    expect(handlers.clear).toHaveBeenCalled();
  });

  it("says when a child's account is among them and a second person has to approve", async () => {
    renderBar([P.usersEndSessions]);
    ended.job = job({
      result: {
        outcomes: { valid: 2 },
        waiting: [],
        minors: 1,
        approval:
          "1 account of the 2 is a child's (under 18): a bulk action on children needs a second person's approval.",
      },
    });
    vi.mocked(startCustomersJob).mockResolvedValueOnce(job());
    const dialog = await open();
    await userEvent.type(within(dialog).getByLabelText("Reason"), "A shared computer.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Check first" }));
    expect(await within(dialog).findByText("1 of them is the account of a student under 18.")).toBeVisible();
    expect(
      within(dialog).getByText(/^A second person has to approve it before it runs\. 1 account of the 2/),
    ).toBeVisible();
    expect(within(dialog).queryByText("It runs at once, within your limits.")).toBeNull();
  });

  it("counts the accounts it would leave alone, and does not offer a run when nothing can change", async () => {
    renderBar([P.usersEndSessions]);
    ended.job = job({ result: { outcomes: { refused: 2 }, waiting: [] } });
    vi.mocked(startCustomersJob).mockResolvedValueOnce(job());
    const dialog = await open();
    await userEvent.type(within(dialog).getByLabelText("Reason"), "A shared computer.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Check first" }));
    expect(await within(dialog).findByText("Nothing can be changed in this choice.")).toBeVisible();
    expect(within(dialog).getByText("2 accounts will be left alone. The reasons are below.")).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Run it for 2 accounts" })).toBeDisabled();
  });

  it("asks for the number of accounts to be typed before a suspension runs, and for nothing else", async () => {
    const handlers = renderBar([P.usersSuspend]);
    vi.mocked(startCustomersJob)
      .mockResolvedValueOnce(job())
      .mockResolvedValueOnce(job({ id: 32, dry_run: false, state: "running" }));
    await userEvent.click(screen.getByRole("button", { name: "Suspend" }));
    const dialog = screen.getByRole("dialog", { name: "Suspend 2 accounts?" });
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Spam sign-ups.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Check first" }));
    const run = within(dialog).getByRole("button", { name: "Run it for 2 accounts" });
    const typed = await within(dialog).findByLabelText("To confirm, type 2 below.");
    expect(run).toBeDisabled();
    await userEvent.type(typed, "3");
    expect(within(dialog).getByText("What you typed does not match.")).toBeVisible();
    expect(run).toBeDisabled();
    await userEvent.clear(typed);
    await userEvent.type(typed, "2");
    expect(run).toBeEnabled();
    await userEvent.click(run);
    expect(startCustomersJob).toHaveBeenLastCalledWith("user.suspend", [7101, 7102], "Spam sign-ups.", false);
    expect(handlers.onJob).toHaveBeenCalled();
  });

  it("shows the API's refusal beside its field, and starts nothing", async () => {
    renderBar([P.usersEndSessions]);
    vi.mocked(startCustomersJob).mockRejectedValueOnce(
      new ApiError(400, "invalid", "Say why.", { "params.reason": ["Say why."] }),
    );
    const dialog = await open();
    await userEvent.click(within(dialog).getByRole("button", { name: "Check first" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Say why.");
    expect(within(dialog).getByLabelText("Reason")).toBeInvalid();
    expect(within(dialog).getByRole("button", { name: "Run it for 2 accounts" })).toBeDisabled();
    expect(startCustomersJob).toHaveBeenCalledTimes(1);
  });
});
