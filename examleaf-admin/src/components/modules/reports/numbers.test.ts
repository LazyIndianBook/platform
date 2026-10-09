// How the reports write their figures: rupees to the paisa with India's grouping, counts, fractions as percents, a bar's
// width (never wider than its box, a sliver for anything above nothing), a period by its grain, and the sentence that
// sets a total beside the period before it.
import { describe, expect, it } from "vitest";

import type { HomeCard } from "@/lib/api/staff";

import {
  barWidth,
  cardValue,
  comparisonWords,
  count,
  decimal,
  lastDays,
  maxOf,
  percent,
  periodLabel,
  rupees,
} from "./numbers";

describe("figures", () => {
  it("write rupees to the paisa with India's grouping, and a dash for nothing", () => {
    expect(rupees("184250.00")).toBe("₹1,84,250.00");
    expect(rupees("0.5")).toBe("₹0.50");
    expect(rupees("-50.00")).toBe("-₹50.00");
    expect(rupees(null)).toBe("–");
    expect(rupees("")).toBe("–");
    expect(rupees("not a number")).toBe("–");
  });

  it("write counts with India's grouping", () => {
    expect(count(1850)).toBe("1,850");
    expect(count(184250)).toBe("1,84,250");
    expect(count(0)).toBe("0");
    expect(count(null)).toBe("–");
    expect(count(undefined)).toBe("–");
  });

  it("write a fraction as a percent and a decimal to the places asked", () => {
    expect(percent("0.4000")).toBe("40%");
    expect(percent("0.7112", 1)).toBe("71.1%");
    expect(percent(null)).toBe("–");
    expect(decimal("12.40")).toBe("12.4");
    expect(decimal("1240.56")).toBe("1,240.6");
    expect(decimal(null)).toBe("–");
  });
});

describe("a bar", () => {
  it("is the share of the largest figure, in whole percent", () => {
    expect(barWidth("50", 200)).toBe(25);
    expect(barWidth(200, 200)).toBe(100);
    expect(barWidth("0.4", 1)).toBe(40);
  });

  it("is a sliver for a small figure, nothing for none, and never wider than its box", () => {
    expect(barWidth(1, 10_000)).toBe(2);
    expect(barWidth(0, 100)).toBe(0);
    expect(barWidth(null, 100)).toBe(0); // a hidden cell
    expect(barWidth(-5, 100)).toBe(0);
    expect(barWidth(500, 100)).toBe(100);
    expect(barWidth(5, 0)).toBe(0); // nothing to compare with
  });

  it("finds the largest figure among strings, numbers and holes", () => {
    expect(maxOf(["10.00", 250, null, undefined, "7"])).toBe(250);
    expect(maxOf([])).toBe(0);
    expect(maxOf([null])).toBe(0);
  });
});

describe("periodLabel", () => {
  it("names a day, a week by its Monday and a month", () => {
    expect(periodLabel("day", "2026-10-07")).toBe("7 Oct 2026");
    expect(periodLabel("week", "2026-10-05")).toBe("Week of 5 Oct 2026");
    expect(periodLabel("month", "2026-10-01")).toBe("October 2026");
    expect(periodLabel("week", null)).toBe("–");
  });
});

const card = (extra: Partial<HomeCard>): HomeCard => ({
  key: "net_revenue",
  label: "Net revenue",
  group: "measure",
  unit: "inr",
  value: "184250.00",
  definition: "Money received less money returned.",
  as_of: "2026-10-09T12:00:00Z",
  period: { start: "2026-10-03", end: "2026-10-09", days: 7 },
  href: "/reports/sales/?from=2026-10-03&to=2026-10-09",
  test_mode: false,
  comparison: null,
  error: "",
  ...extra,
});
const against = (extra: object) => ({
  previous: "151900.00",
  difference: "+32350.00",
  percent: "+21.3",
  period: { start: "2026-09-26", end: "2026-10-02", days: 7 },
  ...extra,
});

describe("a card's figure", () => {
  it("is whole rupees for money and a grouped count for the rest, a dash while it has none", () => {
    expect(cardValue(card({}))).toBe("₹1,84,250");
    expect(cardValue(card({ unit: "count", value: "1260" }))).toBe("1,260");
    expect(cardValue(card({ value: null, error: "could not be worked out" }))).toBe("–");
  });

  it("names the days it covers", () => {
    expect(lastDays(1)).toBe("Today");
    expect(lastDays(7)).toBe("The last 7 days");
  });
});

describe("a total beside the period before it", () => {
  it("says up with the size, the percent and the figure before", () => {
    expect(comparisonWords(card({ comparison: against({}) }))).toBe(
      "Up ₹32,350 (21.3%) on the 7 days before (₹1,51,900)",
    );
  });

  it("says down for a fall, counted in whole numbers for a count", () => {
    expect(
      comparisonWords(
        card({ unit: "count", comparison: against({ previous: "221", difference: "-9", percent: "-4.1" }) }),
      ),
    ).toBe("Down 9 (4.1%) on the 7 days before (221)");
  });

  it("leaves the percent out from nothing before, and says the same when nothing moved", () => {
    expect(
      comparisonWords(
        card({ unit: "count", comparison: against({ previous: "0", difference: "+12", percent: null }) }),
      ),
    ).toBe("Up 12 on the 7 days before (0)");
    expect(
      comparisonWords(
        card({ unit: "count", comparison: against({ previous: "40", difference: "+0", percent: "+0.0" }) }),
      ),
    ).toBe("The same as the 7 days before (40)");
  });

  it("says the day before for a day, and nothing for a queue", () => {
    expect(
      comparisonWords(card({ comparison: against({ period: { start: "2026-10-08", end: "2026-10-08", days: 1 } }) })),
    ).toBe("Up ₹32,350 (21.3%) on the day before (₹1,51,900)");
    expect(comparisonWords(card({ group: "queue", comparison: null }))).toBeNull();
  });
});
