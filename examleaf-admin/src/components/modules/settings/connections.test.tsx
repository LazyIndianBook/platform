// A connection's card says in words whether it works and what to do (never the colour alone), test and live apart;
// its actions are drawn for staff.manage_connections only; a test that fails says why; new keys go as password fields,
// with the provider's overlap warning, and come back only as their last four characters.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { type ConnectionCard, replaceCredentials, testConnection } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { ConnectionCardView } from "./connections";
import { parseVariables, variablesText } from "./templates";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  testConnection: vi.fn(),
  replaceCredentials: vi.fn(),
}));

const NOW = Date.parse("2026-10-09T12:00:00Z");

function card(extra: Partial<ConnectionCard> = {}): ConnectionCard {
  return {
    provider: "razorpay",
    name: "Razorpay",
    kind: "payments",
    status: "connected",
    mode: "test",
    source: "panel",
    held: {},
    accounts: [
      {
        id: 1,
        mode: "test",
        enabled: true,
        label: "",
        held: { key_id: "…9876", key_secret: "…wxyz" },
        unreadable: false,
        credentials_updated_at: "2026-09-01T10:00:00Z",
        credentials_updated_by: 7,
        rotate_by: "2026-10-12",
        rotate_in_days: 3,
        token_expires_at: null,
        token_in_hours: null,
        webhook_token: "",
        webhook_rotated_at: null,
      },
    ],
    last_success_at: "2026-10-09T11:00:00Z",
    last_error_at: null,
    last_error: "",
    last_test: { at: null, ok: null, message: "" },
    circuit: { state: "closed", held_open: false, opened_at: null, failures: 0 },
    calls: { day: 4, day_errors: 1, week: 30, week_errors: 2, p90_ms: 410 },
    fields: ["key_id", "key_secret"],
    optional: [],
    modes: ["test", "live"],
    overlap_warning: "Razorpay may stop a regenerated key's predecessor at once.",
    actions: { test: true, credentials: true, mode: true, circuit: false, webhooks: true },
    extra: { webhook: { last_event_at: null, age_hours: null, paid_in_window: 3, window_hours: 24, silent: true } },
    ...extra,
  };
}

const draw = (row: ConnectionCard, permissions: string[] = [P.connectionsView, P.connectionsManage]) =>
  render(
    <ManifestProvider manifest={manifestWith(permissions)}>
      <ConnectionCardView card={row} now={NOW} />
    </ManifestProvider>,
  );

beforeEach(() => {
  navigation.router.refresh = vi.fn<() => void>();
  vi.mocked(testConnection).mockReset();
  vi.mocked(replaceCredentials).mockReset();
});

describe("ConnectionCardView", () => {
  it("says whether it works and what to do, in words, test apart from live", () => {
    draw(card({ status: "expired", mode: "live" }));
    expect(screen.getByText("Keys refused")).toBeInTheDocument();
    expect(screen.getByText(/replace them with new ones/)).toBeInTheDocument();
    const live = screen.getAllByText("Live")[0];
    const test = screen.getAllByText("Test")[0];
    expect(live.className).not.toEqual(test.className); // two colours, and always the word
    expect(screen.getByText(/Rotate the keys within 3 days/)).toBeInTheDocument();
    expect(screen.getByText(/No webhook for 24 hours while 3 payments came in/)).toBeInTheDocument();
  });

  it("draws the actions for staff.manage_connections only", () => {
    draw(card(), [P.connectionsView]);
    expect(screen.queryByRole("button", { name: /Test the connection/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Replace the keys/ })).toBeNull();
    expect(screen.getByRole("link", { name: /Webhooks, events and calls/ })).toHaveAttribute(
      "href",
      "/settings/connections/razorpay/",
    );
  });

  it("says why a test failed, in the provider's words", async () => {
    vi.mocked(testConnection).mockResolvedValueOnce({
      ok: false,
      message: "Razorpay (test) payments: HTTP 401: Authentication failed",
      card: card(),
    });
    draw(card());
    await userEvent.click(screen.getByRole("button", { name: /Test the connection/ }));
    expect(testConnection).toHaveBeenCalledWith("razorpay");
    expect(await screen.findByText(/The test failed: Razorpay \(test\) payments: HTTP 401/)).toBeInTheDocument();
  });

  it("takes new keys as password fields, with the overlap warning, and sends them with the mode and a reason", async () => {
    vi.mocked(replaceCredentials).mockResolvedValueOnce({ ok: true, message: "Connected", card: card() });
    draw(card());
    await userEvent.click(screen.getByRole("button", { name: /Replace the keys/ }));
    const dialog = screen.getByRole("dialog", { name: "Replace Razorpay's keys" });
    expect(within(dialog).getByText(/regenerated key's predecessor/)).toBeInTheDocument();
    const secret = within(dialog).getByLabelText("Key secret");
    expect(secret).toHaveAttribute("type", "password");
    await userEvent.type(within(dialog).getByLabelText("Key id"), "rzp_test_NewNewNew1234");
    await userEvent.type(secret, "new-test-secret-0123456789");
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Rotation");
    await userEvent.click(within(dialog).getByRole("button", { name: "Replace the keys" }));
    expect(replaceCredentials).toHaveBeenCalledWith("razorpay", {
      mode: "test",
      reason: "Rotation",
      credentials: { key_id: "rzp_test_NewNewNew1234", key_secret: "new-test-secret-0123456789" },
    });
  });
});

describe("the templates' variables", () => {
  it("are one a line, and read back as the API's", () => {
    const rows = parseVariables("var1, alphanumeric, 30, the order number\n\notp, numeric, 6, the code, as sent");
    expect(rows).toEqual([
      { name: "var1", type: "alphanumeric", max_length: 30, about: "the order number" },
      { name: "otp", type: "numeric", max_length: 6, about: "the code, as sent" },
    ]);
    expect(parseVariables(variablesText(rows))).toEqual(rows);
  });
});
