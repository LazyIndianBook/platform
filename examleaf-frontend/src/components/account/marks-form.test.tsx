// The record card's states (ExamLeaf A - States.dc.html): one save at a time, "Consent pending" (the form closed with
// the reason, the parent's link sent again), "Session expired" (what was typed comes back after logging in) and
// "Marks saved" (the red circle only once the server has answered). The checks and words of the form itself are in
// account.test.tsx.
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api/client";

import { MarksForm } from "./marks-form";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn() },
}));

const DRAFT = "examleaf:marks-draft:PHY-E01:new";
const answer = (status: number, body: unknown) =>
  ({
    data: status < 400 ? body : undefined,
    error: status < 400 ? undefined : body,
    response: new Response(null, { status }),
  }) as never;
const attempt = (marks: string) =>
  answer(201, { id: 9, paper: "PHY-E01", date: "2026-10-08", marks_obtained: marks, full_marks: 70, percent: 75 });
const save = () => screen.getByRole("button", { name: "Save to my record" });

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
});

describe("MarksForm's states", () => {
  it("is busy while saving, and a second press or submit sends nothing", async () => {
    let reply!: (value: unknown) => void;
    vi.mocked(api.POST).mockReturnValue(new Promise((resolve) => (reply = resolve)) as never);
    render(<MarksForm paper="PHY-E01" fullMarks={70} />);
    await userEvent.type(screen.getByLabelText(/Marks obtained/), "52.5");
    await userEvent.click(save());
    expect(save()).toHaveAttribute("aria-busy", "true");

    await userEvent.click(save()); // the busy button swallows the press
    fireEvent.submit(save().closest("form")!); // and the form a second submit (Enter, a script)
    expect(api.POST).toHaveBeenCalledTimes(1);

    await act(async () => reply(attempt("52.5")));
    expect(await screen.findByText("Saved to My record")).toBeInTheDocument();
    expect(save()).not.toHaveAttribute("aria-busy");
  });

  it("circles the score only once the server has answered", async () => {
    let reply!: (value: unknown) => void;
    vi.mocked(api.POST).mockReturnValue(new Promise((resolve) => (reply = resolve)) as never);
    const { container } = render(<MarksForm paper="PHY-E01" fullMarks={70} nextPaper="PHY-E02" />);
    await userEvent.type(screen.getByLabelText(/Marks obtained/), "52.5");
    await userEvent.click(save());
    expect(container.querySelector("[data-mark-landed]")).toBeNull();
    expect(screen.queryByText("Saved to My record")).toBeNull();

    await act(async () => reply(attempt("52.5")));
    expect(await screen.findByText("Saved to My record")).toBeInTheDocument();
    expect(container.querySelector("[data-mark-landed]")).toHaveTextContent("52.5");
    expect(screen.getByRole("link", { name: "Next: Paper E-02 →" })).toHaveAttribute("href", "/s/PHY-E02/");
    expect(screen.getByRole("link", { name: "Edit" })).toHaveAttribute("href", "/account/record/9/edit/");
  });

  it("closes the form while a parent's consent is awaited, says why, and sends the link again", async () => {
    const refusal =
      "Your parent or guardian has not confirmed your account yet: marks can be saved once they have (see My account).";
    vi.mocked(api.POST)
      .mockResolvedValueOnce(answer(400, { non_field_errors: [refusal] }))
      .mockResolvedValueOnce(answer(200, { detail: "We have sent parent@example.com a link to confirm." }));
    vi.mocked(api.GET).mockResolvedValueOnce(answer(200, { parent_contact: "parent@example.com" }));
    render(<MarksForm paper="PHY-E01" fullMarks={70} />);
    await userEvent.type(screen.getByLabelText(/Marks obtained/), "40");
    await userEvent.click(save());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Waiting for your parent");
    expect(alert).toHaveTextContent(refusal);
    expect(alert).toHaveFocus(); // the Save button that had it is disabled now
    expect(save()).toBeDisabled();
    expect(screen.getByLabelText(/Marks obtained/)).toBeDisabled();
    expect(screen.getByText("Saving opens once your parent confirms.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Send them the link again" })).toHaveAttribute("href", "/account/privacy/");

    await userEvent.click(screen.getByRole("button", { name: "Send the link again" }));
    expect(await screen.findByText("We have sent parent@example.com a link to confirm.")).toBeInTheDocument();
    expect(api.GET).toHaveBeenCalledWith("/api/v1/me/");
    expect(api.POST).toHaveBeenLastCalledWith("/api/v1/me/parent-consent/", {
      body: { parent_contact: "parent@example.com" },
    });
  });

  it("brings back what was typed after the log-in a 401 led to, and forgets it once saved", async () => {
    // the session has ended: the client takes the visitor to log in (sessionMiddleware); nothing is shown here
    vi.mocked(api.POST).mockResolvedValueOnce(answer(401, { detail: "Authentication credentials were not provided." }));
    const before = render(<MarksForm paper="PHY-E01" fullMarks={70} />);
    await userEvent.type(screen.getByLabelText(/Marks obtained/), "61");
    await userEvent.type(screen.getByLabelText(/What to revise/), "Gauss's law");
    await userEvent.click(save());
    await waitFor(() => expect(save()).not.toHaveAttribute("aria-busy"));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(JSON.parse(window.sessionStorage.getItem(DRAFT)!)).toMatchObject({
      marks_obtained: "61",
      notes: "Gauss's law",
    });
    before.unmount();

    // back from logging in, on the same page: the form as it was left
    render(<MarksForm paper="PHY-E01" fullMarks={70} />);
    expect(screen.getByLabelText(/Marks obtained/)).toHaveValue("61");
    expect(screen.getByLabelText(/What to revise/)).toHaveValue("Gauss's law");

    vi.mocked(api.POST).mockResolvedValueOnce(attempt("61"));
    await userEvent.click(save());
    expect(await screen.findByText("Saved to My record")).toBeInTheDocument();
    expect(api.POST).toHaveBeenLastCalledWith("/api/v1/attempts/", {
      body: expect.objectContaining({ paper: "PHY-E01", marks_obtained: "61", notes: "Gauss's law" }),
    });
    expect(window.sessionStorage.getItem(DRAFT)).toBeNull();
    expect(screen.getByLabelText(/Marks obtained/)).toHaveValue(""); // a fresh form for the next paper
  });
});
