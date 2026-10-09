// One error shape for every answer: the staff API's codes (401, the four 403s, 409, 429 with Retry-After), DRF's and
// allauth.headless's formats, and no answer at all.
import { describe, expect, it } from "vitest";

import { ApiError, retryAfterSeconds, toApiError } from "./errors";

describe("toApiError", () => {
  it("maps a 401 to a sign-in again", () => {
    const error = toApiError(401, { detail: "Authentication credentials were not provided." });
    expect(error.status).toBe(401);
    expect(error.code).toBe("unauthenticated");
    expect(error.message).toBe("Authentication credentials were not provided.");
  });

  it("keeps the code of each 403 the console acts on", () => {
    for (const code of ["permission_denied", "scope_denied", "reauth_required", "mfa_setup_required"]) {
      const error = toApiError(403, { detail: "No.", code });
      expect(error.code).toBe(code);
      expect(error.message).toBe("No.");
      expect(error.unavailable).toBe(false);
    }
  });

  it("finds the change request an approval_required names, in any of its shapes", () => {
    expect(
      toApiError(403, { detail: "Asked.", code: "approval_required", change_request: { id: 12 } }).changeRequestId,
    ).toBe("12");
    expect(toApiError(403, { detail: "Asked.", code: "approval_required", change_request: 13 }).changeRequestId).toBe(
      "13",
    );
    expect(
      toApiError(403, { detail: "Asked.", code: "approval_required", change_request_id: "cr-14" }).changeRequestId,
    ).toBe("cr-14");
    expect(toApiError(403, { detail: "Asked.", code: "approval_required" }).changeRequestId).toBeNull();
  });

  it("tells Django's CSRF page (a 403 without JSON) from the API's refusals", () => {
    const error = toApiError(403, null);
    expect(error.code).toBe("forbidden");
    expect(error.body).toBeNull();
  });

  it("maps a stale update to a conflict", () => {
    const error = toApiError(409, { detail: "This request changed since you opened it." });
    expect(error.code).toBe("conflict");
    expect(error.message).toBe("This request changed since you opened it.");
  });

  it("reads Retry-After on a 429, in seconds or as a date, and when the wait ends", () => {
    const headers = new Headers({ "Retry-After": "60" });
    const before = Date.now();
    const error = toApiError(429, { detail: "Request was throttled." }, headers);
    expect(error.code).toBe("throttled");
    expect(error.retryAfter).toBe(60);
    expect(error.retryAt).toBeGreaterThanOrEqual(before + 60_000);
    expect(toApiError(429, { detail: "Slow down." }).retryAfter).toBeNull();
    expect(
      retryAfterSeconds(new Date(Date.UTC(2026, 9, 9, 10, 1, 30)).toUTCString(), Date.UTC(2026, 9, 9, 10, 0, 0)),
    ).toBe(90);
    expect(retryAfterSeconds("soon")).toBeNull();
  });

  it("puts DRF's field errors beside their fields and keeps its non-field message", () => {
    const error = toApiError(400, { reason: ["Give a reason."], non_field_errors: ["Not now."] });
    expect(error.fields).toEqual({ reason: ["Give a reason."] });
    expect(error.message).toBe("Not now.");
    expect(toApiError(400, { email: ["Enter a work email address."] }).message).toBe("Enter a work email address.");
  });

  it("reads allauth.headless's errors", () => {
    const error = toApiError(400, {
      status: 400,
      errors: [
        { message: "Incorrect code.", code: "incorrect_code", param: "code" },
        { message: "Too many attempts.", code: "too_many_login_attempts" },
      ],
    });
    expect(error.fields).toEqual({ code: ["Incorrect code."] });
    expect(error.message).toBe("Too many attempts.");
    expect(error.code).toBe("incorrect_code");
  });

  it("calls no answer at all, and a 5xx, unavailable", () => {
    expect(toApiError(0, null).unavailable).toBe(true);
    expect(toApiError(502, "<html>Bad gateway</html>").unavailable).toBe(true);
    expect(new ApiError(200, "bad_response", "x").unavailable).toBe(false);
  });
});
