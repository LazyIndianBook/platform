// A confirmation's Cancel cancels: it closes the dialog and sends nothing. Every untyped Button used to be a submit
// button (HTML's default), so Cancel, inside the dialog's form, carried out the action it was there to refuse.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "./confirm-typed";

describe("ConfirmDialog", () => {
  it("does nothing on Cancel, and the action once on its own button", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn(async () => undefined);
    render(
      <ConfirmDialog
        triggerLabel="Revoke"
        title="Revoke the role?"
        text="Anita loses Support at once."
        confirmLabel="Revoke the role"
        onConfirm={onConfirm}
        onDone={() => undefined}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Revoke" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onConfirm).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Revoke" }));
    await user.click(screen.getByRole("button", { name: "Revoke the role" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
