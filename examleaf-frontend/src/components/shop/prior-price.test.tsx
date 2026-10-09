// The prior price beside a reduced price (from 1 January 2027): one line when the API gives one, nothing otherwise.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PriorPrice } from "./product-card";

describe("the prior price", () => {
  it("says the lowest price of the 30 days before the reduction, in rupees", () => {
    render(<PriorPrice price="279.00" />);
    expect(screen.getByText("Lowest price in the 30 days before this reduction: ₹279")).toBeInTheDocument();
  });

  it("says nothing before the rule applies or when the price is not reduced", () => {
    const { container } = render(<PriorPrice price={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
