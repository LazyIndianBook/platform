// The staff API client: what goes out (the path, the CSRF token on a change, If-Match), what the guards make of the
// answer (typed data, or bad_response), and what the browser does with each refusal (sign in again, confirm it's you
// then send once more, read the manifest again, a change request instead of the action).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { copy } from "@/lib/copy";

import { ANSWER_TIMEOUT_MS } from "./client";
import { ApiError } from "./errors";
import {
  cursorOf,
  getSession,
  listInbox,
  revealUser,
  resetUserMfa,
  staffPath,
  updateDataRequest,
  userAction,
} from "./staff";

const client = vi.hoisted(() => ({ sessionEnded: vi.fn(), manifestStale: vi.fn(), reauthRequest: vi.fn() }));
vi.mock("./client", async (original) => {
  const real = await original<typeof import("./client")>();
  return {
    ...real,
    sessionEnded: client.sessionEnded,
    manifestStale: client.manifestStale,
    reauth: { ...real.reauth, request: client.reauthRequest },
  };
});

const SESSION = {
  user: { id: 7, email: "staff@example.com", name: "Staff Member" },
  roles: [{ name: "SUPPORT", expires_at: null }],
  permissions: ["accounts.view_user", "staff.view_inboxitem"],
  scopes: { subject: ["PHY"] },
  limits: { refund_inr: "2000.00", discount_percent: 20, export_rows: 5000, bulk_rows: 100 },
  flags: { web_course: false },
  reauth_valid_until: null,
  idle_timeout_s: 1800,
  absolute_expires_at: "2026-10-09T20:00:00+05:30",
  impersonating: null,
  manifest_version: "abc123",
};

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  document.cookie = "csrftoken=token-123";
  Object.values(client).forEach((mock) => mock.mockReset());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const sent = (call = 0) => fetchMock.mock.calls[call][0] as Request;

describe("the request", () => {
  it("asks the staff root with the query's set values only", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { results: [], next: null, previous: null }));
    await listInbox({ state: "open", kind: "", assignee: "me" });
    const request = sent();
    expect(new URL(request.url).pathname).toBe("/api/v1/staff/inbox/");
    expect(new URL(request.url).search).toBe("?state=open&assignee=me");
    expect(request.method).toBe("GET");
    expect(request.headers.get("X-CSRFToken")).toBeNull();
    expect(staffPath("people/", { q: "anita", cursor: undefined })).toBe("/api/v1/staff/people/?q=anita");
  });

  it("sends a change with the CSRF token, a JSON body and the version it read", async () => {
    fetchMock.mockResolvedValueOnce(
      json(200, {
        id: 801,
        type: "erasure",
        received_at: "2026-10-07T10:00:00+05:30",
        state: "received",
        requester: {},
        version: 3,
      }),
    );
    await updateDataRequest("801", { notes: "Called back." }, "2");
    const request = sent();
    expect(request.method).toBe("PATCH");
    expect(request.headers.get("X-CSRFToken")).toBe("token-123");
    expect(request.headers.get("If-Match")).toBe('"2"');
    expect(await request.json()).toEqual({ notes: "Called back." });
  });
});

describe("the guards", () => {
  it("turn the session into the manifest the shell draws from", async () => {
    fetchMock.mockResolvedValueOnce(json(200, SESSION));
    const manifest = await getSession();
    expect(manifest.user).toEqual({ id: "7", email: "staff@example.com", name: "Staff Member" });
    expect(manifest.limits).toEqual({ refund_inr: 2000, discount_percent: 20, export_rows: 5000, bulk_rows: 100 });
    expect(manifest.scopes).toEqual({ subject: ["PHY"] });
    expect(manifest.idle_timeout_s).toBe(1800);
    // the platform's User.full_name serves as the name
    fetchMock.mockResolvedValueOnce(
      json(200, { ...SESSION, user: { id: 7, email: "s@example.com", full_name: "S M" } }),
    );
    expect((await getSession()).user.name).toBe("S M");
  });

  it("fail loudly as bad_response when a field the console needs is missing or renamed", async () => {
    const { idle_timeout_s, ...renamed } = SESSION;
    void idle_timeout_s;
    fetchMock.mockResolvedValueOnce(json(200, { ...renamed, idle_seconds: 1800 }));
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(getSession()).rejects.toMatchObject({ code: "bad_response" });
    expect(spy).toHaveBeenCalledWith(expect.stringContaining("idle_timeout_s"));
    spy.mockRestore();
  });

  it("read a cursor out of the pagination's links", () => {
    expect(cursorOf("https://admin.examleaf.in/api/v1/staff/audit/?cursor=cD0yMDI2&q=x")).toBe("cD0yMDI2");
    expect(cursorOf(null)).toBeNull();
    expect(cursorOf("https://admin.examleaf.in/api/v1/staff/audit/?page=2")).toBeNull();
  });
});

describe("in the browser, the answers that act", () => {
  it("a 401 sends the person to sign in again and fails the call", async () => {
    fetchMock.mockResolvedValueOnce(json(401, { detail: "Authentication credentials were not provided." }));
    await expect(userAction("7101", "unlock")).rejects.toMatchObject({ status: 401 });
    expect(client.sessionEnded).toHaveBeenCalledWith("expired");
    // the backend's own idle limit says so, and the sign-in page says why
    fetchMock.mockResolvedValueOnce(json(401, { detail: "Signed out after inactivity.", code: "session_idle" }));
    await expect(userAction("7101", "unlock")).rejects.toMatchObject({ status: 401 });
    expect(client.sessionEnded).toHaveBeenLastCalledWith("idle");
  });

  it("reauth_required waits for 'confirm it's you', then sends the call once more", async () => {
    const flows = [{ id: "mfa_reauthenticate", types: ["totp"] }];
    fetchMock
      .mockResolvedValueOnce(json(403, { detail: "Confirm it's you.", code: "reauth_required", flows }))
      .mockResolvedValueOnce(json(200, { value: "riya.das@example.com" }));
    client.reauthRequest.mockResolvedValueOnce(true);
    await expect(revealUser("7101", "email", "Ticket 4412")).resolves.toBe("riya.das@example.com");
    expect(client.reauthRequest).toHaveBeenCalledWith(flows);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(await sent(1).json()).toEqual({ field: "email", reason: "Ticket 4412" });
  });

  it("a closed 'confirm it's you' fails the call with reauth_required, sent once", async () => {
    fetchMock.mockResolvedValue(json(403, { detail: "Confirm it's you.", code: "reauth_required" }));
    client.reauthRequest.mockResolvedValueOnce(false);
    await expect(revealUser("7101", "email", "Ticket 4412")).rejects.toMatchObject({ code: "reauth_required" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("a refusal by role or scope reads the manifest again", async () => {
    fetchMock.mockResolvedValueOnce(json(403, { detail: "Your role does not allow this.", code: "permission_denied" }));
    await expect(userAction("7101", "suspend")).rejects.toMatchObject({ code: "permission_denied" });
    expect(client.manifestStale).toHaveBeenCalled();
    fetchMock.mockResolvedValueOnce(json(403, { detail: "Not your subject.", code: "scope_denied" }));
    await expect(userAction("7101", "suspend")).rejects.toMatchObject({ code: "scope_denied" });
    expect(client.manifestStale).toHaveBeenCalledTimes(2);
  });

  it("a 202 with a change request is an approval_required with its id", async () => {
    fetchMock.mockResolvedValueOnce(
      json(202, { id: 77, action: "accounts.reset_user_mfa", payload_sha256: "ab", state: "pending" }),
    );
    const error = (await resetUserMfa("7103").catch((caught) => caught)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("approval_required");
    expect(error.changeRequestId).toBe("77");
  });

  it("a 429 says when to try again", async () => {
    fetchMock.mockResolvedValueOnce(json(429, { detail: "Request was throttled." }, { "Retry-After": "30" }));
    await expect(revealUser("7101", "phone", "Ticket")).rejects.toMatchObject({ status: 429, retryAfter: 30 });
  });

  it("no answer is 'unavailable', never a sign-out", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(userAction("7101", "unlock")).rejects.toMatchObject({ status: 0, code: "unavailable" });
    expect(client.sessionEnded).not.toHaveBeenCalled();
  });

  it("no answer in 30 s gives up: a read can't be reached, a change may have gone through, neither is sent again", async () => {
    const timeout = new AbortController(); // the call's AbortSignal.timeout(30 s), fired by hand
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeout.signal);
    fetchMock.mockImplementation(
      (request: Request) =>
        new Promise((_, reject) => {
          if (request.signal.aborted) reject(request.signal.reason);
          request.signal.addEventListener("abort", () => reject(request.signal.reason));
        }),
    );
    try {
      const read = listInbox({ state: "open" });
      const change = userAction("7101", "unlock");
      timeout.abort(new DOMException("signal timed out", "TimeoutError"));
      await expect(read).rejects.toMatchObject({ status: 0, message: copy.errors.unavailable });
      await expect(change).rejects.toMatchObject({ status: 0, message: copy.errors.unconfirmed });
      expect(AbortSignal.timeout).toHaveBeenCalledWith(ANSWER_TIMEOUT_MS);
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(client.sessionEnded).not.toHaveBeenCalled();
    } finally {
      vi.restoreAllMocks();
    }
  });

  it("an answer the timeout cut off is no answer, not a bad one: the change may have gone through", async () => {
    const timeout = new AbortController();
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeout.signal);
    // the headers came, the body stops halfway until the call's signal gives up
    fetchMock.mockImplementation(async (request: Request) => {
      const body = new ReadableStream({
        start(stream) {
          stream.enqueue(new TextEncoder().encode('{"id": '));
          request.signal.addEventListener("abort", () => stream.error(request.signal.reason));
        },
      });
      return new Response(body, { status: 201, headers: { "Content-Type": "application/json" } });
    });
    try {
      const change = userAction("7101", "unlock");
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
      timeout.abort(new DOMException("signal timed out", "TimeoutError"));
      await expect(change).rejects.toMatchObject({ status: 0, message: copy.errors.unconfirmed });
    } finally {
      vi.restoreAllMocks();
    }
  });
});

describe("on the server", () => {
  it("speaks with the transport's base, headers and fetch, and leaves the browser's reactions out", async () => {
    const serverFetch = vi.fn().mockResolvedValue(json(401, { detail: "Signed out." }));
    const transport = { base: "http://web:8000", headers: { Cookie: "sessionid=abc" }, fetch: serverFetch };
    await expect(getSession(transport)).rejects.toMatchObject({ status: 401 });
    const request = serverFetch.mock.calls[0][0] as Request;
    expect(request.url).toBe("http://web:8000/api/v1/staff/session/");
    expect(request.headers.get("Cookie")).toBe("sessionid=abc");
    expect(client.sessionEnded).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
