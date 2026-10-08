// API v1 lists: {"count", "next", "previous", "results"}, 50 a page, ?page=2, ?page_size= up to 200 (API.md, "Lists").
export const PAGE_SIZE = 50;

export type Paginated<T> = { count: number; next?: string | null; previous?: string | null; results: T[] };

export function pageInfo(list: Pick<Paginated<unknown>, "count">, page: number, pageSize = PAGE_SIZE) {
  const pages = Math.max(1, Math.ceil(list.count / pageSize));
  const current = Math.min(Math.max(1, page), pages);
  return { page: current, pages, hasPrevious: current > 1, hasNext: current < pages };
}

/** ?page= from a search param, defaulting to 1 for anything that is not a positive whole number. */
export function pageParam(value: string | string[] | undefined): number {
  const page = Number(Array.isArray(value) ? value[0] : value);
  return Number.isInteger(page) && page > 0 ? page : 1;
}
