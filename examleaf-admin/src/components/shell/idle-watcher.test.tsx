// The idle limit: a warning two minutes before the manifest's idle_timeout_s, Stay signed in tells the server and
// starts again, any key or click counts as activity (in any tab), and at the end the console signs out and comes back
// here afterwards; the absolute end of a session warns too, and cannot be pushed back.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getSession } from "@/lib/api/staff";

import { ACTIVITY_KEY, IdleWatcher, idleDeadlines } from "./idle-watcher";
import { signOut } from "./sign-out";

vi.mock("./sign-out", () => ({ signOut: vi.fn(), signOutEverywhere: vi.fn() }));
vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  getSession: vi.fn().mockResolvedValue({}),
}));

const MINUTE = 60_000;

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-09T10:00:00+05:30"));
  window.localStorage.clear();
  vi.mocked(signOut).mockReset();
  vi.mocked(getSession).mockClear();
});

afterEach(() => {
  vi.useRealTimers();
});

const warning = () => screen.queryByRole("alertdialog", { name: "You'll be signed out soon" });

describe("idleDeadlines", () => {
  it("warns two minutes before the end, or at three quarters of a short limit", () => {
    expect(idleDeadlines(0, 1800)).toEqual({ warnAt: 28 * MINUTE, end: 30 * MINUTE });
    expect(idleDeadlines(0, 240)).toEqual({ warnAt: 3 * MINUTE, end: 4 * MINUTE });
  });
});

describe("IdleWatcher", () => {
  it("warns at 28 minutes and signs out at 30, coming back here afterwards", () => {
    render(<IdleWatcher idleSeconds={1800} absoluteEnd={null} />);
    act(() => vi.advanceTimersByTime(27 * MINUTE));
    expect(warning()).toBeNull();
    act(() => vi.advanceTimersByTime(MINUTE + 10_000));
    expect(warning()).toBeInTheDocument();
    expect(warning()).toHaveTextContent("That happens at 10:30.");
    expect(signOut).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(2 * MINUTE));
    expect(signOut).toHaveBeenCalledWith("idle", true);
  });

  it("keeps to the limit the manifest gives the role: 15 minutes warns at 13", () => {
    render(<IdleWatcher idleSeconds={900} absoluteEnd={null} />);
    act(() => vi.advanceTimersByTime(12 * MINUTE));
    expect(warning()).toBeNull();
    act(() => vi.advanceTimersByTime(MINUTE + 10_000));
    expect(warning()).toHaveTextContent("That happens at 10:15.");
    act(() => vi.advanceTimersByTime(2 * MINUTE));
    expect(signOut).toHaveBeenCalledWith("idle", true);
  });

  it("starts again after Stay signed in, and tells the server", () => {
    render(<IdleWatcher idleSeconds={1800} absoluteEnd={null} />);
    act(() => vi.advanceTimersByTime(28 * MINUTE + 10_000));
    fireEvent.click(screen.getByRole("button", { name: "Stay signed in" }));
    expect(warning()).toBeNull();
    expect(getSession).toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(27 * MINUTE));
    expect(warning()).toBeNull();
    expect(signOut).not.toHaveBeenCalled();
  });

  it("counts a key or a click as activity, and another tab's too", () => {
    render(<IdleWatcher idleSeconds={1800} absoluteEnd={null} />);
    act(() => vi.advanceTimersByTime(20 * MINUTE));
    fireEvent.keyDown(window, { key: "a" });
    act(() => vi.advanceTimersByTime(20 * MINUTE));
    expect(warning()).toBeNull();
    // another tab was used a minute ago
    window.localStorage.setItem(ACTIVITY_KEY, String(Date.now() - MINUTE));
    act(() => vi.advanceTimersByTime(20 * MINUTE));
    expect(warning()).toBeNull();
    expect(signOut).not.toHaveBeenCalled();
  });

  it("warns before the session's absolute end, and signs out then however active", () => {
    const end = new Date(Date.now() + 10 * MINUTE).toISOString();
    render(<IdleWatcher idleSeconds={1800} absoluteEnd={end} />);
    act(() => vi.advanceTimersByTime(8 * MINUTE + 10_000));
    expect(screen.getByRole("alertdialog", { name: "Your session ends soon" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stay signed in" })).toBeNull();
    fireEvent.pointerDown(window);
    act(() => vi.advanceTimersByTime(2 * MINUTE));
    expect(signOut).toHaveBeenCalledWith("expired", true);
  });
});
