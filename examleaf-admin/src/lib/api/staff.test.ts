// The staff API client (openapi-fetch, typed from the backend's schema): what goes out (the path, the query's set
// values, the CSRF token and the JSON body on a change, an Idempotency-Key where the API takes one), what comes back
// (a 202 with a change request as approval_required, with its id, status and checker; a reveal as its value; an
// audit export as a file or a job), and what the browser does with each refusal (sign in again with why, confirm
// it's you then send once more, read the manifest again).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { copy } from "@/lib/copy";

import { ANSWER_TIMEOUT_MS } from "./client";
import { ApiError } from "./errors";
import {
  askChange,
  cursorOf,
  exportAudit,
  getSession,
  jobFileHref,
  listInbox,
  listUsers,
  resetUserMfa,
  revealUser,
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
const PAGE = { results: [], next: null, previous: null };

describe("the request", () => {
  it("asks the staff path with the query's set values only, never cached", async () => {
    fetchMock.mockResolvedValueOnce(json(200, PAGE));
    await listInbox({ kind: "approval", mine: true, cursor: "" });
    const request = sent();
    expect(new URL(request.url).pathname).toBe("/api/v1/staff/inbox/");
    expect(new URL(request.url).search).toBe("?kind=approval&mine=true");
    expect(request.method).toBe("GET");
    expect(request.headers.get("X-CSRFToken")).toBeNull();
    expect(fetchMock.mock.calls[0][1]).toEqual({ cache: "no-store" });
  });

  it("sends a change with the CSRF token and a JSON body", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { id: 801, notes: "Called back." }));
    await updateDataRequest(801, { notes: "Called back." });
    const request = sent();
    expect(request.method).toBe("PATCH");
    expect(new URL(request.url).pathname).toBe("/api/v1/staff/data-requests/801/");
    expect(request.headers.get("X-CSRFToken")).toBe("token-123");
    expect(await request.json()).toEqual({ notes: "Called back." });
  });

  it("asks with an Idempotency-Key, the same one when it is sent again", async () => {
    const flows = [{ id: "reauthenticate" }];
    fetchMock
      .mockResolvedValueOnce(json(403, { detail: "Log in again.", code: "reauthentication_required", flows }))
      .mockResolvedValueOnce(json(201, { id: 12, status: "executed", payload_sha256: "ab", checker: "x" }));
    client.reauthRequest.mockResolvedValueOnce(true);
    await askChange({
      action: "order.refund",
      target: "EL-2026-000123",
      payload: { amount: "500" },
      reason: "Damaged",
    });
    const first = sent(0).headers.get("Idempotency-Key");
    expect(first).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent(1).headers.get("Idempotency-Key")).toBe(first);
  });

  it("names the customer's details to show, and answers the value", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { login_phone: null, phone: "+919864012345" }));
    await expect(revealUser(42, ["login_phone", "phone"], "Ticket 4412")).resolves.toBe("+919864012345");
    expect(await sent().json()).toEqual({ show: ["login_phone", "phone"], reason: "Ticket 4412" });
  });
});

describe("the answers", () => {
  it("are the API's own fields, the session's included", async () => {
    const session = {
      user: { id: 7, email: "staff@example.com", full_name: "Staff Member", is_superuser: false },
      roles: [{ name: "SUPPORT", expires_at: null, granted_by: 1 }],
      permissions: ["accounts.view_user", "staff.view_inbox"],
      scopes: { ticket_queue: ["data_request"] },
      role_scopes: {},
      limits: { refund_inr: 1000, export_rows: 100 },
      flags: { test_mode: true },
      reauth_valid_until: null,
      idle_timeout_s: 1800,
      absolute_expires_at: "2026-10-09T17:59:00Z",
      impersonating: null,
      manifest_version: "3f9a1c0d2b7e4a55",
    };
    fetchMock.mockResolvedValueOnce(json(200, session));
    await expect(getSession()).resolves.toEqual(session);
  });

  it("turn a page's links into cursors", async () => {
    const next = "https://admin.examleaf.in/api/v1/staff/users/?cursor=cD0yMDI2&q=riya";
    fetchMock.mockResolvedValueOnce(json(200, { results: [{ id: 1 }], next, previous: null }));
    await expect(listUsers({ q: "riya" })).resolves.toEqual({ results: [{ id: 1 }], next: "cD0yMDI2", previous: null });
    expect(cursorOf(null)).toBeNull();
    expect(cursorOf("https://admin.examleaf.in/api/v1/staff/audit/?page=2")).toBeNull();
  });

  it("an audit export is a file at once, or a job", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response('{"id": 1}\n', {
        headers: {
          "Content-Type": "application/x-ndjson",
          "Content-Disposition": 'attachment; filename="audit-20261009.jsonl"',
        },
      }),
    );
    const file = await exportAudit({ action_prefix: "order." });
    expect(file).toMatchObject({ name: "audit-20261009.jsonl" });
    expect(await sent().json()).toEqual({ filters: { action_prefix: "order." } });
    fetchMock.mockResolvedValueOnce(json(202, { id: 702, state: "queued", change_request_id: 508 }));
    await expect(exportAudit({})).resolves.toEqual({ job: { id: 702, state: "queued", change_request_id: 508 } });
  });

  it("a job's file is the job read again for a fresh link, kept on this origin", async () => {
    fetchMock.mockResolvedValueOnce(
      json(200, { id: 703, state: "done", result_url: "http://web:8000/api/v1/staff/jobs/703/result/?token=abc%3A1" }),
    );
    await expect(jobFileHref(703)).resolves.toBe("/api/v1/staff/jobs/703/result/?token=abc%3A1");
    expect(new URL(sent().url).pathname).toBe("/api/v1/staff/jobs/703/");
    fetchMock.mockResolvedValueOnce(json(200, { id: 703, state: "done", result_url: null }));
    await expect(jobFileHref(703)).resolves.toBeNull();
  });

  it("a 202 with a change request is approval_required, with its id, status and checker", async () => {
    const changeRequest = {
      id: 77,
      action: "user.reset_mfa",
      payload_sha256: "ab",
      status: "pending",
      checker: "staff.reset_user_mfa",
    };
    fetchMock.mockResolvedValueOnce(json(202, changeRequest));
    const error = (await resetUserMfa(7103, "Lost phone").catch((caught) => caught)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("approval_required");
    expect(error.approval).toEqual({ id: "77", status: "pending", checker: "staff.reset_user_mfa" });
  });
});

describe("in the browser, the answers that act", () => {
  it("a 401 sends the person to sign in again, saying why", async () => {
    fetchMock.mockResolvedValueOnce(json(401, { detail: "Not signed in.", code: "not_authenticated" }));
    await expect(userAction(7101, "unlock")).rejects.toMatchObject({ status: 401 });
    expect(client.sessionEnded).toHaveBeenCalledWith("expired");
    fetchMock.mockResolvedValueOnce(json(401, { detail: "Signed out after inactivity.", code: "session_idle" }));
    await expect(userAction(7101, "unlock")).rejects.toMatchObject({ code: "session_idle" });
    expect(client.sessionEnded).toHaveBeenLastCalledWith("idle");
    fetchMock.mockResolvedValueOnce(json(401, { detail: "Session over.", code: "session_expired" }));
    await expect(userAction(7101, "unlock")).rejects.toMatchObject({ code: "session_expired" });
    expect(client.sessionEnded).toHaveBeenLastCalledWith("expired");
  });

  it("reauthentication_required waits for 'confirm it's you', then sends the call once more", async () => {
    const flows = [{ id: "mfa_reauthenticate", types: ["totp"] }];
    fetchMock
      .mockResolvedValueOnce(json(403, { detail: "Log in again.", code: "reauthentication_required", flows }))
      .mockResolvedValueOnce(json(200, { email: "riya.das@example.com" }));
    client.reauthRequest.mockResolvedValueOnce(true);
    await expect(revealUser(7101, ["email"], "Ticket 4412")).resolves.toBe("riya.das@example.com");
    expect(client.reauthRequest).toHaveBeenCalledWith(flows);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(await sent(1).json()).toEqual({ show: ["email"], reason: "Ticket 4412" });
  });

  it("a closed 'confirm it's you' fails the call with reauth_required, sent once", async () => {
    fetchMock.mockResolvedValue(json(403, { detail: "Log in again.", code: "reauthentication_required" }));
    client.reauthRequest.mockResolvedValueOnce(false);
    await expect(revealUser(7101, ["email"], "Ticket 4412")).rejects.toMatchObject({ code: "reauth_required" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("a refusal by permission reads the manifest again; impersonating and not_found do not", async () => {
    fetchMock.mockResolvedValueOnce(json(403, { detail: "You need the permission x.", code: "permission_denied" }));
    await expect(userAction(7101, "unlock")).rejects.toMatchObject({ code: "permission_denied" });
    expect(client.manifestStale).toHaveBeenCalledTimes(1);
    fetchMock.mockResolvedValueOnce(json(403, { detail: "Not while impersonating.", code: "impersonating" }));
    await expect(userAction(7101, "unlock")).rejects.toMatchObject({ code: "impersonating" });
    fetchMock.mockResolvedValueOnce(json(404, { detail: "Not found.", code: "not_found" }));
    await expect(userAction(7101, "unlock")).rejects.toMatchObject({ status: 404, code: "not_found" });
    expect(client.manifestStale).toHaveBeenCalledTimes(1);
  });

  it("a 429 says when to try again", async () => {
    fetchMock.mockResolvedValueOnce(
      json(429, { detail: "Request was throttled.", code: "throttled" }, { "Retry-After": "30" }),
    );
    await expect(revealUser(7101, ["phone"], "Ticket")).rejects.toMatchObject({ status: 429, retryAfter: 30 });
  });

  it("no answer is 'unavailable', never a sign-out", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(userAction(7101, "unlock")).rejects.toMatchObject({ status: 0, code: "unavailable" });
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
      const read = listInbox({ mine: true });
      const change = userAction(7101, "unlock");
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
      const change = userAction(7101, "unlock");
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
    const serverFetch = vi.fn().mockResolvedValue(json(401, { detail: "Signed out.", code: "not_authenticated" }));
    const transport = { base: "http://web:8000", headers: { Cookie: "sessionid=abc" }, fetch: serverFetch };
    await expect(getSession(transport)).rejects.toMatchObject({ status: 401 });
    const request = serverFetch.mock.calls[0][0] as Request;
    expect(request.url).toBe("http://web:8000/api/v1/staff/session/");
    expect(request.headers.get("Cookie")).toBe("sessionid=abc");
    expect(client.sessionEnded).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
