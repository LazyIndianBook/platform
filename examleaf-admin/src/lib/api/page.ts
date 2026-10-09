// What every server page does with the staff API: check the session (requireStaff), get the server's transport, and
// turn each call into its data or its ApiError (a page draws a Problem for the part that failed and keeps the rest);
// a 401 meanwhile sends the person to sign in and back here, a 404 is the page's 404.
import "server-only";

import { notFound, redirect } from "next/navigation";
import { cache } from "react";

import { signInHref } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { staffTransport } from "@/lib/api/server";
import type { Manifest, Transport } from "@/lib/api/staff";
import { requireStaff } from "@/lib/auth/session";

export type SearchParams = Record<string, string | string[] | undefined>;

/** One "now" per request (ms since 1970): the layout's and the page's clocks start from the same moment, and a client
 *  clock's first render matches the server's. */
export const requestTime = cache(() => Date.now());

/** One value of a search param. */
export const param = (params: SearchParams, name: string): string => {
  const value = params[name];
  return (Array.isArray(value) ? value[0] : value) ?? "";
};

/** The page's own address with its query, for "sign in, then back here". */
export function pathOf(path: string, params: SearchParams = {}): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    for (const each of Array.isArray(value) ? value : value === undefined ? [] : [value]) search.append(name, each);
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export async function staffPage(path: string): Promise<{ manifest: Manifest; transport: Transport; path: string }> {
  const manifest = await requireStaff(path);
  return { manifest, transport: await staffTransport(), path };
}

/** The data, or the ApiError of a call that failed for any reason but an ended session (sign in) or a 404. */
export async function attempt<T>(
  answer: Promise<T>,
  path: string,
  missing: "404" | "error" = "error",
): Promise<T | ApiError> {
  try {
    return await answer;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect(signInHref(path, "expired"));
    if (error instanceof ApiError && error.status === 404 && missing === "404") notFound();
    if (error instanceof ApiError) return error;
    throw error;
  }
}
