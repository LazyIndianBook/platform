// The maintenance band: drawn from the config's `maintenance` while it is on, with the panel's words or the plain line.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MAINTENANCE_DEFAULT, MaintenanceBanner } from "./maintenance-banner";

describe("MaintenanceBanner", () => {
  it("draws nothing while maintenance mode is off or unknown", () => {
    const { container } = render(<MaintenanceBanner maintenance={{ on: false, banner: "Back at 6" }} />);
    expect(container).toBeEmptyDOMElement();
    expect(render(<MaintenanceBanner maintenance={null} />).container).toBeEmptyDOMElement();
  });

  it("shows the panel's banner, or the plain line when none was set", () => {
    render(<MaintenanceBanner maintenance={{ on: true, banner: "Back at 6 pm: orders wait until then." }} />);
    expect(screen.getByRole("region", { name: "Maintenance" })).toHaveTextContent(
      "Back at 6 pm: orders wait until then.",
    );
    render(<MaintenanceBanner maintenance={{ on: true, banner: "  " }} />);
    expect(screen.getAllByRole("region", { name: "Maintenance" })[1]).toHaveTextContent(MAINTENANCE_DEFAULT);
  });
});
