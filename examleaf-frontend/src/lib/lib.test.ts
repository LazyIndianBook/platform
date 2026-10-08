// The pure parts of the API, auth and security layers: what breaks quietly if it is wrong.
import { describe, expect, it } from "vitest";

import { ApiError, toApiError, unwrap } from "./api/errors";
import { pageInfo, pageParam } from "./api/pagination";
import { type AuthResult, nextRoute } from "./auth/headless";
import { safeNext, withNext } from "./auth/next-url";
import { decodeRequestOptions } from "./auth/webauthn";
import { inr, inrShort } from "./format";
import { buildCsp } from "./security/csp";
import { isPersonalPage, shortCode, subjectOf } from "./site";

describe("money", () => {
  it("drops zero paise on display prices and groups in lakhs", () => {
    expect(inrShort("299.00")).toBe("₹299");
    expect(inrShort("718.20")).toBe("₹718.20");
    expect(inr("123456")).toBe("₹1,23,456.00");
  });
});

describe("safeNext", () => {
  it("keeps a path on this site and refuses anything else", () => {
    expect(safeNext("/s/PHY-E02/")).toBe("/s/PHY-E02/");
    expect(safeNext("/shop/?kind=bundle#top")).toBe("/shop/?kind=bundle#top");
    for (const bad of [
      "https://evil.example/",
      "//evil.example/",
      "/\\evil.example",
      "javascript:alert(1)",
      "",
      null,
    ]) {
      expect(safeNext(bad)).toBe("/");
    }
    expect(safeNext("/account/logout/")).toBe("/"); // never back to undo the log-in
    expect(safeNext("/s/PHY-E02/#record")).toBe("/s/PHY-E02/#record");
    expect(safeNext("/shop/?q=a%2Fb")).toBe("/shop/?q=a%2Fb");
    expect(withNext("/account/login/", "/s/PHY-E02/")).toBe("/account/login/?next=%2Fs%2FPHY-E02%2F");
    expect(withNext("/account/login/", "https://evil.example/")).toBe("/account/login/");
  });

  it("refuses the review's dot-segment, encoded and @ vectors (security review S1)", () => {
    for (const bad of [
      "/..//evil.com",
      "/.//evil.com",
      "/././/evil.com",
      "/a/..//evil.com",
      "/%2e%2e//evil.com",
      "/..///evil.com",
      "/account/../..//evil.com",
      "/%2e%2e/evil.com",
      "/../evil.com",
      "/./",
      "///evil.com",
      "/\t/evil.com",
      "/@evil.com",
      "/?x=1#//evil.com",
      "\\\\evil.com",
      "data:text/html,x",
    ]) {
      expect(safeNext(bad), bad).toBe("/");
    }
  });
});

describe("toApiError", () => {
  it("reads DRF field errors and non-field errors", () => {
    const error = toApiError(400, { marks_obtained: ["Enter marks from 0 to 70."], non_field_errors: ["Too late."] });
    expect(error).toMatchObject({ status: 400, code: "invalid", message: "Too late." });
    expect(error.fields).toEqual({ marks_obtained: ["Enter marks from 0 to 70."] });
  });

  it("reads a detail with its code, and allauth.headless's errors by param", () => {
    expect(toApiError(401, { detail: "Given token not valid", code: "token_not_valid" })).toMatchObject({
      code: "token_not_valid",
      message: "Given token not valid",
    });
    const allauth = toApiError(400, {
      status: 400,
      errors: [{ message: "Incorrect code.", code: "incorrect_code", param: "code" }],
    });
    expect(allauth).toMatchObject({
      code: "incorrect_code",
      message: "Incorrect code.",
      fields: { code: ["Incorrect code."] },
    });
  });

  it("calls a missing backend unavailable, and unwrap turns a network failure into one", async () => {
    expect(toApiError(503, null).unavailable).toBe(true);
    expect(toApiError(429, { status: 429 }).message).toMatch(/Too many tries/);
    await expect(unwrap(Promise.reject(new TypeError("fetch failed")))).rejects.toMatchObject({
      status: 0,
      code: "unavailable",
    });
    const response = new Response(null, { status: 404 });
    await expect(unwrap(Promise.resolve({ error: { detail: "Not found." }, response }))).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});

describe("a parent's consent awaited", () => {
  it("marks the API's refusals, whatever their status, so that forms can offer the parent's link", () => {
    const course = toApiError(403, { detail: "A parent or guardian has not confirmed this account yet." });
    const marks = toApiError(400, {
      non_field_errors: [
        "Your parent or guardian has not confirmed your account yet: marks can be saved once they have (see My account).",
      ],
    });
    expect(course.code).toBe("consent_pending");
    expect(marks.code).toBe("consent_pending");
    expect(marks.message).toMatch(/^Your parent or guardian/);
    expect(toApiError(403, { detail: "Confirm your email address first." }).code).toBe("forbidden");
  });
});

describe("pagination", () => {
  it("counts pages and reads ?page=", () => {
    expect(pageInfo({ count: 120 }, 3)).toEqual({ page: 3, pages: 3, hasPrevious: true, hasNext: false });
    expect(pageInfo({ count: 0 }, 5)).toEqual({ page: 1, pages: 1, hasPrevious: false, hasNext: false });
    expect(pageParam("2")).toBe(2);
    expect(pageParam(["x"])).toBe(1);
  });
});

describe("nextRoute", () => {
  const result = (over: Partial<AuthResult>): AuthResult => ({
    status: 401,
    authenticated: false,
    user: null,
    flows: [],
    pending: null,
    data: {},
    ...over,
  });

  it("goes to the destination once signed in, else to the pending step", () => {
    expect(nextRoute(result({ status: 200, authenticated: true }), "/s/PHY-E02/")).toBe("/s/PHY-E02/");
    expect(nextRoute(result({ pending: { id: "verify_email", is_pending: true } }), "/s/PHY-E02/")).toBe(
      "/account/verify-email/?next=%2Fs%2FPHY-E02%2F",
    );
    expect(nextRoute(result({ pending: { id: "mfa_authenticate", is_pending: true } }), null)).toBe(
      "/account/2fa/authenticate/",
    );
    expect(nextRoute(result({ pending: { id: "login_by_code", is_pending: true } }), null)).toBeNull();
  });
});

describe("buildCsp", () => {
  it("allows scripts by nonce only, Razorpay only on checkout, Turnstile only when on", () => {
    const page = buildCsp({ nonce: "abc", pathname: "/" });
    expect(page).toContain("script-src 'self' 'nonce-abc' 'strict-dynamic'");
    expect(page).toContain("frame-ancestors 'none'");
    expect(page).toContain("form-action 'self' https://accounts.google.com");
    expect(page).not.toContain("razorpay");
    expect(page).not.toContain("unsafe-eval");
    const pay = buildCsp({
      nonce: "abc",
      pathname: "/checkout/12/pay/",
      turnstile: true,
      mediaHost: "media.examleaf.in",
    });
    expect(pay).toContain("https://checkout.razorpay.com");
    expect(pay).toContain("https://challenges.cloudflare.com");
    expect(pay).toContain("connect-src 'self' https://media.examleaf.in");
    expect(buildCsp({ nonce: "n", pathname: "/", https: true })).toContain("upgrade-insecure-requests");
  });
});

describe("site", () => {
  it("prints paper codes as the books do and maps subjects to their tokens", () => {
    expect(shortCode("PHY-E01")).toBe("E-01");
    expect(shortCode("MAT-H10")).toBe("H-10");
    expect(subjectOf("MAT")).toEqual({ key: "maths", name: "Mathematics" });
    expect(subjectOf("XYZ")).toBeNull();
  });

  it("keeps the visitor's own pages out of every cache, and solutions and the course once signed in", () => {
    for (const path of ["/account/", "/account/login/", "/cart/", "/checkout/7/pay/", "/orders/t/abc/", "/c/tok/"])
      expect(isPersonalPage(path, false)).toBe(true);
    for (const path of ["/", "/shop/", "/shop/physics-2027/", "/books/physics-2027/", "/contact/", "/s/PHY-E01/"])
      expect(isPersonalPage(path, false)).toBe(false);
    expect(isPersonalPage("/s/PHY-E01/", true)).toBe(true);
    expect(isPersonalPage("/revision/", true)).toBe(true);
    expect(isPersonalPage("/shop/", true)).toBe(false);
    expect(isPersonalPage("/cartoons/", false)).toBe(false);
  });
});

describe("webauthn", () => {
  it("turns the server's base64url options into buffers when the browser cannot", () => {
    const options = decodeRequestOptions({
      challenge: "aGVsbG8",
      allowCredentials: [{ id: "AQID", type: "public-key" }],
    });
    expect([...new Uint8Array(options.challenge as ArrayBuffer)]).toEqual([...new TextEncoder().encode("hello")]);
    expect([...new Uint8Array(options.allowCredentials![0].id as ArrayBuffer)]).toEqual([1, 2, 3]);
  });
});
