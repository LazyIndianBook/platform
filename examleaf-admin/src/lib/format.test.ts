// The clocks of the privacy queue and the breach register: time left in words, and urgency by the share of the window
// that is left (the last quarter is "soon"); dates and times always in India's time zone.
import { describe, expect, it } from "vitest";

import { formatDateTime, formatDuration, fromLocalInput, remaining, toLocalInput, urgency } from "./format";

const H = 3_600_000;
const start = Date.parse("2026-10-07T10:00:00+05:30");

describe("urgency", () => {
  it("is ok early, soon in the last quarter of the window, overdue once due has passed", () => {
    const due = new Date(start + 48 * H).toISOString();
    const from = new Date(start).toISOString();
    expect(urgency(from, due, start + 10 * H)).toBe("ok");
    expect(urgency(from, due, start + 37 * H)).toBe("soon");
    expect(urgency(from, due, start + 48 * H)).toBe("overdue");
    expect(urgency(null, null, start)).toBe("ok");
  });
});

describe("remaining", () => {
  it("says the time left, or how late, rounded up to the minute", () => {
    const due = new Date(start + 6 * H).toISOString();
    expect(remaining(due, start + 2 * H + 40 * 60_000)).toBe("3 h 20 min left");
    expect(remaining(due, start + 8 * H)).toBe("overdue by 2 h 0 min");
    expect(formatDuration(3 * 24 * H + 5 * H)).toBe("3 d 5 h");
    expect(formatDuration(30_000)).toBe("1 min");
  });
});

describe("times in India", () => {
  it("prints a moment in India whatever the browser's zone, and reads a local input as India's", () => {
    expect(formatDateTime("2026-10-09T03:15:00Z")).toBe("9 Oct 2026, 08:45");
    expect(toLocalInput("2026-10-09T03:15:00Z")).toBe("2026-10-09T08:45");
    expect(fromLocalInput("2026-10-09T08:45")).toBe("2026-10-09T08:45:00+05:30");
    expect(formatDateTime(null)).toBe("Never");
  });
});
