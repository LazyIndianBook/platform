// An invitation accepted: the name and password sent with the link's token, the welcome with its sign-in link; the
// API's refusal beside its field; an address with an account told to sign in first, with the way back to the link.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { acceptInvite } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { InviteForm } from "./invite-form";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  acceptInvite: vi.fn(),
}));

const accept = vi.mocked(acceptInvite);

beforeEach(() => {
  accept.mockReset();
});

async function fillAndSend() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(copy.auth.acceptName), "Rina Das");
  await user.type(screen.getByLabelText(copy.auth.acceptPassword), "a sentence to remember 2027");
  await user.click(screen.getByRole("button", { name: copy.auth.acceptButton }));
}

describe("InviteForm", () => {
  it("sends the token with the name and password, then shows the welcome and the sign-in link", async () => {
    accept.mockResolvedValue({ detail: "Welcome. Log in, then set up an authenticator app or a passkey." });
    render(<InviteForm token="tok-1" />);
    await fillAndSend();
    expect(accept).toHaveBeenCalledWith("tok-1", "Rina Das", "a sentence to remember 2027");
    expect(await screen.findByRole("heading", { name: copy.auth.acceptedTitle })).toBeInTheDocument();
    expect(screen.getByText("Welcome. Log in, then set up an authenticator app or a passkey.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: copy.auth.acceptedSignIn })).toHaveAttribute("href", "/sign-in/");
  });

  it("shows the API's refusal beside its field, and a used link in one line", async () => {
    accept.mockRejectedValueOnce(
      new ApiError(400, "invalid", "This password is too short.", { password: ["This password is too short."] }),
    );
    render(<InviteForm token="tok-2" />);
    await fillAndSend();
    expect(await screen.findAllByText("This password is too short.")).not.toHaveLength(0);
    accept.mockRejectedValueOnce(
      new ApiError(400, "invalid", "This invitation is not valid: it was used, revoked or expired.", {
        token: ["This invitation is not valid: it was used, revoked or expired."],
      }),
    );
    await userEvent.setup().click(screen.getByRole("button", { name: copy.auth.acceptButton }));
    expect(await screen.findAllByText(/This invitation is not valid/)).not.toHaveLength(0);
  });

  it("tells an address that has an account to sign in first, keeping the way back to the link", async () => {
    accept.mockRejectedValue(
      new ApiError(401, "not_authenticated", "An account has this address: log in first, then open the link again."),
    );
    render(<InviteForm token="tok-3" />);
    await fillAndSend();
    expect(
      await screen.findByText("An account has this address: log in first, then open the link again."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: copy.auth.signIn })).toHaveAttribute(
      "href",
      "/sign-in/?next=%2Finvite%2Ftok-3%2F",
    );
  });
});
