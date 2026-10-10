// The course's small words: the item analysis as the bank shows it (N/A under 30 learners), its flags in words, tags
// as typed, and the bulk edit's payload holding only what was filled in.
import { describe, expect, it } from "vitest";

import { copy } from "@/lib/copy";

import { metadataPayload } from "./bank-table";
import { flagLabel, statOf, tagsOf } from "./shared";

const words = copy.course.bank;
const stats = (row: Partial<Parameters<typeof statOf>[0]> = {}) => ({
  n: 412,
  p: 0.8125,
  discrimination: 0.4189,
  flags: [],
  computed_at: "2026-10-09T02:00:00Z",
  n_too_small: false,
  ...row,
});

describe("statOf", () => {
  it("gives the numbers, or N/A under 30 learners and before the first run", () => {
    expect(statOf(stats(), "n")).toBe("412");
    expect(statOf(stats(), "p")).toBe("81.3%");
    expect(statOf(stats(), "discrimination")).toBe("0.42");
    expect(statOf(stats({ n: 12, n_too_small: true }), "p")).toBe(words.na);
    expect(statOf(stats({ n: null, p: null, discrimination: null, n_too_small: true }), "n")).toBe(words.na);
  });
});

describe("flagLabel", () => {
  it("names a distractor's option", () => {
    expect(flagLabel("low_discrimination")).toBe(words.flags.low_discrimination);
    expect(flagLabel("distractor_2")).toBe(words.distractor("2"));
  });
});

describe("tagsOf", () => {
  it("trims and drops the empty ones", () => {
    expect(tagsOf(" formula, ,bridge ,")).toEqual(["formula", "bridge"]);
  });
});

describe("metadataPayload", () => {
  const form = (values: Record<string, string>) => {
    const data = new FormData();
    for (const [name, value] of Object.entries(values)) data.set(name, value);
    return data;
  };

  it("holds only the fields filled in; 'not set' clears a level", () => {
    expect(metadataPayload(form({ topic: "", marks: "", difficulty: "", bloom: "" }))).toEqual({});
    expect(
      metadataPayload(
        form({
          topic: " Ohm's law ",
          marks: "2",
          difficulty: "none",
          bloom: "apply",
          tags_add: "a, b",
          tags_remove: "",
        }),
      ),
    ).toEqual({ topic: "Ohm's law", marks: 2, difficulty: "", bloom: "apply", tags_add: ["a", "b"] });
  });
});
