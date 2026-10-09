// The print run a printed QR code carries (`/s/<code>/?printing=PHY-2027-1`), as the server checks a print run's label
// (content/reports.py PRINTING). A plain module: the solutions page (a server component) reads it from the address and
// "Report a mistake" (a client one) sends it.
export const PRINTING = /^[A-Za-z0-9][A-Za-z0-9-]{0,39}$/;

/** The print run of `?printing=`, or "" when it is missing or not a print run's label. */
export function printingOf(value: string | string[] | undefined): string {
  const text = (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
  return PRINTING.test(text) ? text : "";
}
