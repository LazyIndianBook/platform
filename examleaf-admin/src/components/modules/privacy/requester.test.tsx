// A data request's requester: masked as the API sends it, with Reveal for whoever holds staff.reveal_contact, which
// asks why and calls the request's reveal with the reason.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { revealDataRequester } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { manifestWith } from "@/test/fixtures";

import { RequesterContact } from "./requester";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  revealDataRequester: vi.fn(),
}));

const reveal = vi.mocked(revealDataRequester);

beforeEach(() => {
  reveal.mockReset();
});

const request = { id: 41, requester: "he•••@example.com" };

describe("RequesterContact", () => {
  it("shows the masked contact and no Reveal without the permission", () => {
    render(
      <ManifestProvider manifest={manifestWith(["staff.view_datarequest"])}>
        <RequesterContact request={request} />
      </ManifestProvider>,
    );
    expect(screen.getByText("he•••@example.com")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: new RegExp(`^${copy.masked.reveal}`) })).not.toBeInTheDocument();
  });

  it("reveals with a reason through the request's own reveal", async () => {
    reveal.mockResolvedValue("hemanta.talukdar@example.com");
    render(
      <ManifestProvider manifest={manifestWith(["staff.view_datarequest", "staff.reveal_contact"])}>
        <RequesterContact request={request} />
      </ManifestProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: new RegExp(`^${copy.masked.reveal}`) }));
    await user.type(screen.getByLabelText(copy.common.reason), "The requester asked which address we hold");
    await user.click(screen.getByRole("button", { name: copy.masked.revealButton }));
    expect(reveal).toHaveBeenCalledWith(41, "The requester asked which address we hold");
    expect(await screen.findByText("hemanta.talukdar@example.com")).toBeInTheDocument();
  });
});
