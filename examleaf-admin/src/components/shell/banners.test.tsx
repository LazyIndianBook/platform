// The TEST band shows only when the manifest's flags say so (test_mode: true; absent or false is production), beside
// the impersonation banner, and neither offers a way to dismiss it.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { manifestWith } from "@/test/fixtures";

import { Banners } from "./banners";

const now = Date.parse("2026-10-09T10:00:00+05:30");
const test = () => screen.queryByRole("region", { name: "Test environment" });

describe("Banners", () => {
  it("draws nothing in production: test_mode absent or false", () => {
    const { container, rerender } = render(<Banners manifest={manifestWith([])} now={now} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<Banners manifest={manifestWith([], { flags: { test_mode: false } })} now={now} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("draws the TEST band with test_mode, beside impersonation, with nothing to dismiss either", () => {
    const impersonating = { user_id: "7105", email: "ka•••@example.com", until: "2026-10-09T10:15:00+05:30" };
    render(<Banners manifest={manifestWith([], { flags: { test_mode: true }, impersonating })} now={now} />);
    expect(test()).toHaveTextContent("Test");
    expect(screen.getByRole("region", { name: /signed in to the website as ka•••@example.com/ })).toBeVisible();
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual(["End"]);
  });
});
