// The banners above every page, from the manifest alone: the TEST band only with test_mode (absent or false is
// production), the break-glass banner for a break-glass account, the impersonation banner with End only in the tab
// that holds the token, and none of them dismissable.
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { manifestWith } from "@/test/fixtures";

import { Banners } from "./banners";

const now = Date.parse("2026-10-09T10:00:00+05:30");
const test = () => screen.queryByRole("region", { name: "Test environment" });
const impersonating = { user_id: 7105, email: "ka•••@example.com", until: "2026-10-09T10:15:00+05:30" };

afterEach(() => window.sessionStorage.clear());

describe("Banners", () => {
  it("draws nothing in production: test_mode absent or false", () => {
    const { container, rerender } = render(<Banners manifest={manifestWith([])} now={now} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<Banners manifest={manifestWith([], { flags: { test_mode: false } })} now={now} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("draws the TEST band with test_mode, beside impersonation, End only with this tab's token", () => {
    window.sessionStorage.setItem("examleaf-admin:impersonation", JSON.stringify({ user: 7105, token: "t-1" }));
    render(<Banners manifest={manifestWith([], { flags: { test_mode: true }, impersonating })} now={now} />);
    expect(test()).toHaveTextContent("Test");
    expect(screen.getByRole("region", { name: /signed in to the website as ka•••@example.com/ })).toBeVisible();
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual(["End"]);
  });

  it("says when an impersonation ends where this tab has no token for it", () => {
    render(<Banners manifest={manifestWith([], { impersonating })} now={now} />);
    expect(screen.getByText(/ends by itself then/)).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("marks a break-glass account, with its reason once given", () => {
    const user = { id: 1, email: "glass@example.com", full_name: "", is_superuser: true };
    render(
      <Banners
        manifest={manifestWith([], {
          user,
          break_glass: { reason_required: false, reason: "The owner is locked out." },
        })}
        now={now}
      />,
    );
    const banner = screen.getByRole("region", { name: "Break-glass session" });
    expect(banner).toHaveTextContent("every check passes");
    expect(banner).toHaveTextContent("Reason given: The owner is locked out.");
    expect(screen.queryByRole("button")).toBeNull();
  });
});
