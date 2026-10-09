// Every word of the console is in copy.ts, ready for Assamese and Bengali: every key holds words (a string, a list, or
// a sentence that takes its numbers and names), none is empty or padded, and the codes the API sends that no table
// names still read as words.
import { describe, expect, it } from "vitest";

import { copy, en, humanize, labelOf } from "./copy";

type Leaf = { path: string; value: unknown };

function leaves(value: unknown, path: string, out: Leaf[] = []): Leaf[] {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) leaves(child, path ? `${path}.${key}` : key, out);
  } else {
    out.push({ path, value });
  }
  return out;
}

/** Sample arguments for a sentence that takes some: "3" reads as a number and as words alike. */
const sample = (fn: (...args: never[]) => unknown) =>
  (fn as (...args: unknown[]) => unknown)(...Array.from({ length: fn.length }, () => "3"));

describe("copy", () => {
  const all = leaves(en, "");

  it("has words for every key", () => {
    expect(all.length).toBeGreaterThan(400);
    for (const { path, value } of all) {
      if (typeof value === "string") {
        expect(value.trim(), path).not.toBe("");
        // only a suffix may start with its own punctuation (", your account"); nothing ends in a space
        if (!path.endsWith("yourAccount")) expect(value, path).toBe(value.trimStart());
        expect(value, path).toBe(value.trimEnd());
      } else if (typeof value === "function") {
        const words = sample(value as (...args: never[]) => unknown);
        expect(typeof words, path).toBe("string");
        expect(String(words).trim(), path).not.toBe("");
        expect(String(words), path).not.toMatch(/undefined|NaN|\[object/);
      } else if (Array.isArray(value)) {
        expect(value.length, path).toBeGreaterThan(0);
        for (const item of value.flat()) expect(String(item).trim(), path).not.toBe("");
      } else {
        throw new Error(`${path} is neither words nor a sentence`);
      }
    }
  });

  it("is the language the page declares, with twelve months", () => {
    expect(copy.lang).toBe("en");
    expect(copy.time.months).toHaveLength(12);
  });

  it("reads an unknown code as words", () => {
    expect(humanize("sync_failure")).toBe("Sync failure");
    expect(humanize("in-progress")).toBe("In progress");
    expect(labelOf(copy.privacy.kinds, "erasure")).toBe("Erasure");
    expect(labelOf(copy.privacy.kinds, "portability")).toBe("Portability");
    expect(labelOf(copy.privacy.kinds, null)).toBe(copy.common.unknown);
  });
});
