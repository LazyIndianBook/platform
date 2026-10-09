// The filters of a report, from the address: only the names the report takes, only those that are there (an empty
// value is "the default"); the API checks each again and answers 400 with the field for one it does not take.
import type { SearchParams } from "@/lib/api/page";
import { toLocalInput } from "@/lib/format";

export function filtersOf(params: SearchParams, names: string[]): Record<string, string> {
  const found: Record<string, string> = {};
  for (const name of names) {
    const value = params[name];
    const first = Array.isArray(value) ? value[0] : value;
    if (first) found[name] = first;
  }
  return found;
}

/** Today in India as a day ("2026-10-09"): the last day a report may name. */
export const todayIn = (now: number) => toLocalInput(now).slice(0, 10);
