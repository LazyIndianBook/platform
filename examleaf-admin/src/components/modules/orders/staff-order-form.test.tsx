// The staff order form: a book found and added, what it comes to and the approval rule's answer shown before saving
// (the API's preview), and a discount above the limit answered with the change request (nothing made).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { ApiError } from "@/lib/api/errors";
import { createStaffOrder, previewStaffOrder, searchProducts } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { StaffOrderForm } from "./staff-order-form";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  searchProducts: vi.fn(),
  previewStaffOrder: vi.fn(),
  createStaffOrder: vi.fn(),
}));

const BOOK = {
  slug: "physics-sample-papers",
  title: "Physics Sample Papers",
  kind: "sample-papers" as const,
  isbn: "",
  price: "299.00",
  mrp: "349.00",
  available: 10,
};

beforeEach(() => {
  navigation.router.push = vi.fn();
  vi.mocked(searchProducts).mockResolvedValue([BOOK]);
  vi.mocked(previewStaffOrder).mockResolvedValue({
    lines: [
      { product: BOOK.slug, title: BOOK.title, unit_price: "299.00", quantity: 2, line_total: "598.00", available: 10 },
    ],
    subtotal: "598.00",
    offers: "0.00",
    discount: "200.00",
    percent: "33.44",
    shipping: "40.00",
    total: "438.00",
    limit: "10.00",
    approval: "33.44% off is beyond the limit of 10%.",
    problems: [],
  });
});

describe("StaffOrderForm", () => {
  it("shows the rule's answer before saving, and the change request made instead of the order", async () => {
    const user = userEvent.setup();
    vi.mocked(createStaffOrder).mockRejectedValue(
      new ApiError(
        202,
        "approval_required",
        "A second person needs to approve this",
        {},
        {
          id: 77,
          status: "pending",
          checker: "staff.approve_discount",
          payload_sha256: "b".repeat(64),
        },
      ),
    );
    render(
      <ManifestProvider manifest={manifestWith([P.ordersAdd])}>
        <StaffOrderForm />
      </ManifestProvider>,
    );
    await user.type(screen.getByLabelText("Find a book"), "phys");
    await user.click(await screen.findByRole("button", { name: "Add Physics Sample Papers" }));
    await user.clear(screen.getByLabelText("Copies of Physics Sample Papers"));
    await user.type(screen.getByLabelText("Copies of Physics Sample Papers"), "2");
    await user.selectOptions(screen.getByLabelText("State"), "AS");
    await user.type(screen.getByLabelText("Discount, in rupees"), "200");
    expect(await screen.findByText("33.44% off is beyond the limit of 10%.")).toBeInTheDocument();
    await vi.waitFor(() =>
      expect(previewStaffOrder).toHaveBeenLastCalledWith(
        expect.objectContaining({ lines: [{ product: BOOK.slug, quantity: 2 }], state: "AS", discount: "200" }),
        expect.anything(),
      ),
    );
    expect(screen.getByRole("button", { name: "Ask for approval" })).toBeInTheDocument();

    await user.type(screen.getByLabelText("Email address"), "school@example.com");
    await user.type(screen.getByLabelText("Reason"), "A school's order by phone");
    await user.click(screen.getByRole("button", { name: "Ask for approval" }));
    expect(createStaffOrder).toHaveBeenCalledWith(
      expect.objectContaining({ channel: "phone", email: "school@example.com", discount: "200", send_link: true }),
    );
    expect(await screen.findByText("A second person needs to approve this")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open the change request/ })).toHaveAttribute("href", "/approvals/77/");
    expect(navigation.router.push).not.toHaveBeenCalled();
  });
});
