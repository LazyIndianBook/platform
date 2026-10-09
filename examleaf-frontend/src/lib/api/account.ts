// The account area's data for server components (package 8C): the signed-in student's own answers from API v1 and
// allauth.headless, with the visitor's cookies and never cached. A 401 (the session ended) goes to log in and back
// to `path`; any other failure comes back as the ApiError, which the page turns into its unavailable or empty state.
import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { withNext } from "@/lib/auth/next-url";

import { ApiError, unwrap } from "./errors";
import type { components } from "./schema";
import { API_INTERNAL_BASE, apiSignal, FORWARDED_HEADERS, personalFetch, publicFetch, serverApi } from "./server";

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

type Filter = { subject?: number; tier?: "E" | "M" | "H" };

/** My record (GET me/record/): the attempts counted, each tier's and subject's average as Django rounds them, each
 *  paper's best and latest attempt, for the filter. */
export async function getRecord(filter: Filter = {}) {
  return unwrap(serverApi.GET("/api/v1/me/record/", { params: { query: filter }, ...(await personalFetch()) }));
}

/** One page of the saved attempts (filtered), newest first. */
export async function getAttempts(filter: Filter & { page?: number; page_size?: number } = {}) {
  return unwrap(serverApi.GET("/api/v1/attempts/", { params: { query: filter }, ...(await personalFetch()) }));
}

/** allauth.headless (browser client) for a server component: its `data`, or the ApiError. */
export async function allauthGet<T>(path: string): Promise<T> {
  const { headers } = await personalFetch();
  let response: Response;
  try {
    response = await fetch(`${API_INTERNAL_BASE}/_allauth/browser/v1${path}`, {
      headers: { ...FORWARDED_HEADERS, ...headers, Accept: "application/json" },
      cache: "no-store",
      signal: apiSignal(),
    });
  } catch {
    throw new ApiError(0, "unavailable", "ExamLeaf cannot be reached just now.");
  }
  const body = (await response.json().catch(() => null)) as { data?: T } | null;
  if (!response.ok) throw new ApiError(response.status, "error", "That could not be read.", {}, body);
  return body?.data as T;
}
