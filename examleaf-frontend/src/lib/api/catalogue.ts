// The public catalogue and content for server components: cached 60 s and tagged (books, papers, products, pages),
// so a revalidateTag() from a webhook could refresh them early. Solutions are personal for a signed-in visitor
// (their cookies, never cached) and public otherwise (open samples, or SOLUTIONS_REQUIRE_LOGIN=0).
import "server-only";

import { unwrap } from "./errors";
import type { components } from "./schema";
import { personalFetch, publicFetch, serverApi } from "./server";

export type Book = components["schemas"]["Book"];
export type Paper = components["schemas"]["Paper"];
export type Product = components["schemas"]["Product"];
export type Question = components["schemas"]["Question"];
export type LegalPage = components["schemas"]["Page"];

export async function getBooks(): Promise<Book[]> {
  const list = await unwrap(
    serverApi.GET("/api/v1/books/", { params: { query: { page_size: 50 } }, ...publicFetch("books") }),
  );
  return list.results;
}

export function getBook(slug: string): Promise<Book> {
  return unwrap(serverApi.GET("/api/v1/books/{slug}/", { params: { path: { slug } }, ...publicFetch("books") }));
}

/** A book's marks and time, from its first paper (every paper of a book has the same). */
export async function getBookFacts(slug: string): Promise<Pick<Paper, "full_marks" | "time_text"> | null> {
  const list = await unwrap(
    serverApi.GET("/api/v1/papers/", {
      params: { query: { book: slug, page_size: 1, ordering: "number" } },
      ...publicFetch("papers"),
    }),
  );
  return list.results[0] ?? null;
}

export async function getProducts(): Promise<Product[]> {
  const list = await unwrap(
    serverApi.GET("/api/v1/products/", { params: { query: { page_size: 200 } }, ...publicFetch("products") }),
  );
  return list.results;
}

/** A paper by the code of a scanned QR (any case, as printed or typed): its canonical code is paper.code. */
export function getPaperByQr(code: string): Promise<Paper> {
  return unwrap(serverApi.GET("/api/v1/qr/{code}/", { params: { path: { code } }, ...publicFetch("papers") }));
}

export async function getSolutions(code: string, signedIn: boolean): Promise<Question[]> {
  const options = signedIn ? await personalFetch() : publicFetch("papers", `solutions-${code}`);
  return unwrap(serverApi.GET("/api/v1/papers/{code}/solutions/", { params: { path: { code } }, ...options }));
}

export function getLegalPage(slug: LegalPage["slug"]): Promise<LegalPage> {
  return unwrap(serverApi.GET("/api/v1/pages/{slug}/", { params: { path: { slug } }, ...publicFetch("pages") }));
}

/** The copies in the signed-in visitor's cart (0 when they cannot have one through the API yet). */
export async function getCartCount(): Promise<number> {
  try {
    const cart = await unwrap(serverApi.GET("/api/v1/cart/", await personalFetch()));
    return cart.count ?? 0;
  } catch {
    return 0;
  }
}
