// The reply box: a saved reply goes in with Alt and its number (or its button) where the cursor is; a reply is sent
// with how it went, a note with the colleagues it names; someone who may only note gets the note box alone; the API's
// field error stands beside its field; and leaving with an unsent reply asks first.
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { ApiError } from "@/lib/api/errors";
import { addTicketMessage, type Agent } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { ticketWith } from "@/test/support";

import { Compose, defaultChannel, savedReplyKey } from "./compose";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  addTicketMessage: vi.fn(),
}));

const AGENTS: Agent[] = [
  { id: 7, name: "Staff Member", handles: true },
  { id: 9003, name: "Rahul Saikia", handles: true },
  { id: 9004, name: "Priya Gogoi", handles: false },
];

function renderCompose(permissions: string[] = [P.ticketsHandle, P.ticketsNote], ticket = ticketWith()) {
  return render(
    <ManifestProvider manifest={manifestWith(permissions)}>
      <Compose ticket={ticket} agents={AGENTS} />
    </ManifestProvider>,
  );
}

beforeEach(() => {
  vi.mocked(addTicketMessage).mockReset();
  window.sessionStorage.clear();
});

describe("savedReplyKey", () => {
  it("reads Alt and a digit from the key's code (Alt on a Mac types other characters), never with Ctrl or ⌘", () => {
    expect(savedReplyKey({ altKey: true, ctrlKey: false, metaKey: false, code: "Digit2" })).toBe(2);
    expect(savedReplyKey({ altKey: true, ctrlKey: false, metaKey: false, code: "Numpad9" })).toBe(9);
    expect(savedReplyKey({ altKey: true, ctrlKey: false, metaKey: false, code: "Digit0" })).toBeNull();
    expect(savedReplyKey({ altKey: false, ctrlKey: false, metaKey: false, code: "Digit1" })).toBeNull();
    expect(savedReplyKey({ altKey: true, ctrlKey: true, metaKey: false, code: "Digit1" })).toBeNull();
  });

  it("replies by email when there is an address or an account, on NCH's portal for its complaints, else as a call", () => {
    expect(defaultChannel(ticketWith())).toBe("email");
    const none = { name: "", email: "", phone: "••••••2345", user: null };
    expect(defaultChannel(ticketWith({ requester: none }))).toBe("phone");
    expect(defaultChannel(ticketWith({ requester: none, source: "nch" }))).toBe("nch");
  });
});

describe("Compose", () => {
  it("puts a saved reply in with Alt and its number, and by its button, where the cursor is", async () => {
    renderCompose();
    const box = screen.getByLabelText("Your reply") as HTMLTextAreaElement;
    await userEvent.type(box, "Hello.");
    fireEvent.keyDown(box, { key: "¡", code: "Digit1", altKey: true });
    expect(box.value).toBe("Hello.\n\nDear Bikash, the refund is on its way.");
    await userEvent.click(screen.getByRole("button", { name: /Parcel on its way/ }));
    expect(box.value).toContain("Dear Bikash, your parcel is with the courier.");
    expect(screen.getByRole("button", { name: /Refund timeline/ })).toHaveAttribute("aria-keyshortcuts", "Alt+1");
    // the ticket's language comes first in the API's order; a third reply is Alt 3
    expect(screen.getByRole("button", { name: /অনুৰোধ পোৱা গৈছে/ })).toHaveAttribute("aria-keyshortcuts", "Alt+3");
  });

  it("sends a reply with how it went, then clears the box", async () => {
    vi.mocked(addTicketMessage).mockResolvedValue({} as never);
    renderCompose();
    await userEvent.selectOptions(screen.getByLabelText("How"), "phone");
    await userEvent.type(screen.getByLabelText("Your reply"), "Told her the parcel left today.");
    await userEvent.click(screen.getByRole("button", { name: "Record the reply" }));
    expect(addTicketMessage).toHaveBeenCalledWith("SR-2026-000101", {
      direction: "out",
      body: "Told her the parcel left today.",
      channel: "phone",
    });
    expect((screen.getByLabelText("Your reply") as HTMLTextAreaElement).value).toBe("");
  });

  it("saves a note naming colleagues (never oneself)", async () => {
    vi.mocked(addTicketMessage).mockResolvedValue({} as never);
    renderCompose();
    await userEvent.click(screen.getByRole("radio", { name: "Internal note" }));
    expect(screen.queryByRole("checkbox", { name: "Staff Member" })).toBeNull();
    await userEvent.click(screen.getByRole("checkbox", { name: "Rahul Saikia" }));
    await userEvent.type(screen.getByLabelText("Your note"), "Can you call the courier?");
    await userEvent.click(screen.getByRole("button", { name: "Save the note" }));
    expect(addTicketMessage).toHaveBeenCalledWith("SR-2026-000101", {
      direction: "note",
      body: "Can you call the courier?",
      channel: "",
      mentions: [9003],
    });
    // sent: the box is empty again and nobody is named for the next note
    expect(screen.getByLabelText("Your note")).toHaveValue("");
    expect(screen.getByRole("checkbox", { name: "Rahul Saikia" })).not.toBeChecked();
  });

  it("gives someone who may only note the note box alone", () => {
    renderCompose([P.ticketsNote]);
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.getByLabelText("Your note")).toBeInTheDocument();
    expect(screen.queryByText("Saved replies")).toBeNull();
  });

  it("draws nothing for someone who may neither reply nor note", () => {
    const { container } = renderCompose([P.ticketsView]);
    expect(container).toBeEmptyDOMElement();
  });

  it("puts the API's words beside the field", async () => {
    vi.mocked(addTicketMessage).mockRejectedValue(
      new ApiError(400, "invalid", "No email address for this requester.", {
        channel: ["No email address for this requester: record how you answered (phone, WhatsApp)."],
      }),
    );
    renderCompose();
    await userEvent.type(screen.getByLabelText("Your reply"), "Hello.");
    await userEvent.click(screen.getByRole("button", { name: "Send the reply" }));
    expect(screen.getByLabelText("How")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("How: No email address for this requester");
    expect((screen.getByLabelText("Your reply") as HTMLTextAreaElement).value).toBe("Hello.");
  });

  it("asks before the page is left with a reply unsent", async () => {
    renderCompose();
    const leave = () => {
      const event = new Event("beforeunload", { cancelable: true });
      act(() => {
        window.dispatchEvent(event);
      });
      return event.defaultPrevented;
    };
    expect(leave()).toBe(false);
    await userEvent.type(screen.getByLabelText("Your reply"), "Half a sentence");
    expect(leave()).toBe(true);
  });
});
