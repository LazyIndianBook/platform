// The shop's API for server components (API.md, "Store catalogue" and "Shop"): the public catalogue cached 60 s and
// tagged, the visitor's cart, addresses and orders with their cookies and never cached, and an order by the link in
// its emails without any cookie, never cached. Client components call the same API through `api` (client.ts).
import "server-only";

import { notFound, redirect } from "next/navigation";

import { withNext } from "@/lib/auth/next-url";

import { ApiError, unwrap } from "./errors";
import type { components } from "./schema";
import { anonymousFetch, personalFetch, publicFetch, serverApi } from "./server";

type Schemas = components["schemas"];
export type Product = Schemas["Product"];
export type Category = Schemas["Category"];
export type Collection = Schemas["Collection"];
export type Cart = Schemas["Cart"];
export type Address = Schemas["Address"];
export type Order = Schemas["Order"];
export type OrderBrief = Schemas["OrderBrief"];
export type Reviews = Schemas["ProductReviews"];

/** A product; a renamed one's old slug is an ApiError 301 whose body says `redirect_to` (its Location names the public
 *  site, which this server should not go out to). */
export function getProduct(slug: string): Promise<Product> {
  return unwrap(
    serverApi.GET("/api/v1/products/{slug}/", {
      params: { path: { slug } },
      fetch: (request: Request) => publicFetch("products").fetch(new Request(request, { redirect: "manual" })),
    }),
  );
}

/** A shelf's or a collection's products, narrowed by `?attr_<code>=` filters (at most five: API.md). */
export async function getListing(filter: { category?: string; collection?: string; attrs?: Record<string, string> }) {
  const query = { page_size: 200, ...(filter.category ? { category: filter.category } : {}) } as Record<
    string,
    unknown
  >;
  if (filter.collection) query.collection = filter.collection;
  for (const [code, value] of Object.entries(filter.attrs ?? {}).slice(0, 5)) query[`attr_${code}`] = value;
  // the attr_ parameters are open-ended, so the schema cannot list them
  const list = await unwrap(
    serverApi.GET("/api/v1/products/", { params: { query: query as never }, ...publicFetch("products") }),
  );
  return list.results;
}

export async function getCategories(): Promise<Category[]> {
  const list = await unwrap(
    serverApi.GET("/api/v1/categories/", { params: { query: { page_size: 200 } }, ...publicFetch("categories") }),
  );
  return list.results;
}

export async function getCollections(): Promise<Collection[]> {
  const list = await unwrap(
    serverApi.GET("/api/v1/collections/", { params: { query: { page_size: 200 } }, ...publicFetch("collections") }),
  );
  return list.results;
}

/** Reviews: `can_review` is the signed-in visitor's own, so their call carries the cookies and is not cached. */
export async function getReviews(slug: string, signedIn: boolean): Promise<Reviews> {
  const options = signedIn ? await personalFetch() : publicFetch("reviews");
  return unwrap(serverApi.GET("/api/v1/products/{slug}/reviews/", { params: { path: { slug } }, ...options }));
}

export async function getCart(state?: Address["state"]): Promise<Cart> {
  const query = state ? { state } : {};
  return unwrap(serverApi.GET("/api/v1/cart/", { params: { query }, ...(await personalFetch()) }));
}

export async function getAddresses(): Promise<Address[]> {
  const list = await unwrap(
    serverApi.GET("/api/v1/addresses/", { params: { query: { page_size: 50 } }, ...(await personalFetch()) }),
  );
  return list.results;
}

export async function getOrders(page: number) {
  return unwrap(serverApi.GET("/api/v1/orders/", { params: { query: { page } }, ...(await personalFetch()) }));
}

export async function getOrder(number: string): Promise<Order> {
  return unwrap(
    serverApi.GET("/api/v1/orders/{number}/", { params: { path: { number } }, ...(await personalFetch()) }),
  );
}

/** The order of an emailed link: no cookie (the link is the key), never cached. */
export async function getOrderByToken(token: string): Promise<Order> {
  return unwrap(
    serverApi.GET("/api/v1/orders/t/{token}/", { params: { path: { token } }, ...(await anonymousFetch()) }),
  );
}

/**
 * For pages: the answer, or the ApiError to show (unavailable, a 403 with its reason). A 404 is the not-found page;
 * a 401 (the session ended) sends the visitor to log in and back to `path`.
 */
export async function orProblem<T>(call: Promise<T>, path: string): Promise<T | ApiError> {
  try {
    return await call;
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 404) notFound();
    if (error.status === 401) redirect(withNext("/account/login/", path));
    return error;
  }
}
