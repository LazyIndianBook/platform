// The account area's data for server components (package 8C): the signed-in student's own answers from API v1 and
// allauth.headless, with the visitor's cookies and never cached. A 401 (the session ended) goes to log in and back
// to `path`; any other failure comes back as the ApiError, which the page turns into its unavailable or empty state.
import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { withNext } from "@/lib/auth/next-url";

import { ApiError, unwrap } from "./errors";
import type { components } from "./schema";
import { API_INTERNAL_BASE, FORWARDED_HEADERS, personalFetch, publicFetch, serverApi } from "./server";

export type Me = components["schemas"]["Profile"];
export type Attempt = components["schemas"]["Attempt"];
export type Board = components["schemas"]["Board"];
export type Subject = components["schemas"]["Subject"];

/** The data, or the ApiError of a call that failed for any reason but an ended session. */
export async function settle<T>(answer: Promise<T>, path: string): Promise<T | ApiError> {
  try {
    return await answer;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect(withNext("/account/login/", path));
    if (error instanceof ApiError) return error;
    throw error; // a redirect or notFound from inside
  }
}

/** GET me/ once per request: the layout, the page and its cards share it. */
export const getMe = cache(async () => unwrap(serverApi.GET("/api/v1/me/", await personalFetch())));

export async function getBoards(): Promise<Board[]> {
  const list = await unwrap(serverApi.GET("/api/v1/boards/", publicFetch("boards")));
  return list.results;
}

export async function getSubjects(): Promise<Subject[]> {
  const list = await unwrap(
    serverApi.GET("/api/v1/subjects/", { params: { query: { page_size: 50 } }, ...publicFetch("subjects") }),
  );
  return list.results;
}

// ponytail: at most 10 pages of 200 (2,000 attempts, 20 a paper a day); an averages endpoint in the API would end it
const MAX_PAGES = 10;

/** Every attempt (filtered), newest first: the tier averages need them all, as Django's My record counts them. */
export async function getAttempts(query: { subject?: number; tier?: "E" | "M" | "H" } = {}): Promise<Attempt[]> {
  const options = await personalFetch();
  const attempts: Attempt[] = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    const list = await unwrap(
      serverApi.GET("/api/v1/attempts/", { params: { query: { ...query, page, page_size: 200 } }, ...options }),
    );
    attempts.push(...list.results);
    if (!list.next) break;
  }
  return attempts;
}

/** allauth.headless (browser client) for a server component: its `data`, or the ApiError. */
export async function allauthGet<T>(path: string): Promise<T> {
  const { headers } = await personalFetch();
  let response: Response;
  try {
    response = await fetch(`${API_INTERNAL_BASE}/_allauth/browser/v1${path}`, {
      headers: { ...FORWARDED_HEADERS, ...headers, Accept: "application/json" },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "unavailable", "ExamLeaf cannot be reached just now.");
  }
  const body = (await response.json().catch(() => null)) as { data?: T } | null;
  if (!response.ok) throw new ApiError(response.status, "error", "That could not be read.", {}, body);
  return body?.data as T;
}

/** Python's round(): halves to the even neighbour (74.5 → 74), as Django's My record rounds the averages. */
const roundHalfEven = (value: number) => {
  const rounded = Math.round(value);
  return value % 1 === 0.5 && rounded % 2 ? rounded - 1 : rounded;
};

/** Each tier's average percentage of the API's attempts (Django's My record); null without an attempt of the tier. */
export function tierAverages(attempts: Pick<Attempt, "tier" | "percent">[]) {
  return (["E", "M", "H"] as const).map((tier) => {
    const rows = attempts.filter((attempt) => attempt.tier === tier);
    const sum = rows.reduce((total, row) => total + row.percent, 0);
    return { tier, count: rows.length, average: rows.length ? roundHalfEven(sum / rows.length) : null };
  });
}
