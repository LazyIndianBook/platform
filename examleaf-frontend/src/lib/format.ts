// Money as the site prints it (components.md, .price): Indian grouping, the rupee sign from the subset font.
const rupees = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });

/** A total, paise kept: ₹718.20, ₹1,23,456.00. The API sends decimal strings ("299.00"). */
export function inr(value: string | number): string {
  return rupees.format(Number(value));
}

/** A display price, zero paise dropped: ₹299, but ₹718.20. */
export function inrShort(value: string | number): string {
  return inr(value).replace(/\.00$/, "");
}
