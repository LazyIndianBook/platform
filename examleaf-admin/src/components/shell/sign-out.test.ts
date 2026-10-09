// @vitest-environment node
// Signing out never fails (a DELETE with no answer still loads the sign-in page, and leaves no unhandled rejection),
// and "everywhere" signs out nothing here when the other sessions could not be ended: the person is told instead.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { auth } from "@/lib/auth/headless";

import { signOut, signOutEverywhere } from "./sign-out";

vi.mock("@/lib/auth/headless", () => ({ auth: { logout: vi.fn(), sessions: vi.fn(), endSessions: vi.fn() } }));

const assign = vi.fn();
beforeEach(() => {
  vi.stubGlobal("window", { location: { assign, pathname: "/inbox/", search: "" } });
  assign.mockReset();
  vi.mocked(auth.logout)
    .mockReset()
    .mockResolvedValue(undefined as never);
  vi.mocked(auth.sessions).mockReset();
  vi.mocked(auth.endSessions).mockReset();
});
afterEach(() => vi.unstubAllGlobals());

const unavailable = () => new ApiError(0, "unavailable", "The ExamLeaf server cannot be reached just now.");

describe("signing out", () => {
  it("loads the sign-in page even when the DELETE gets no answer, and never rejects", async () => {
    vi.mocked(auth.logout).mockRejectedValue(unavailable());
    await expect(signOut("idle", true)).resolves.toBeUndefined();
    expect(assign).toHaveBeenCalledWith(expect.stringMatching(/^\/sign-in\/\?next=%2Finbox%2F.*reason=idle/));
  });

  it("everywhere: ends the others first, and signs out nothing here when they could not be ended", async () => {
    vi.mocked(auth.sessions).mockResolvedValue([
      { id: 1, user_agent: "", ip: null, created_at: 0, is_current: true },
      { id: 2, user_agent: "", ip: null, created_at: 0, is_current: false },
    ]);
    vi.mocked(auth.endSessions).mockRejectedValueOnce(unavailable());
    await expect(signOutEverywhere()).rejects.toMatchObject({ status: 0 });
    expect(auth.logout).not.toHaveBeenCalled();
    expect(assign).not.toHaveBeenCalled();

    vi.mocked(auth.endSessions).mockResolvedValueOnce(undefined as never);
    await signOutEverywhere();
    expect(auth.endSessions).toHaveBeenLastCalledWith([2]);
    expect(auth.logout).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledTimes(1);
  });
});
