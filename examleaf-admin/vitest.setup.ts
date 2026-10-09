import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(cleanup);

// The App Router's hooks outside a Next app: a fixed page and its search params (a test may set them), a router that
// records what it was asked to do.
export const navigation = vi.hoisted(() => ({
  pathname: "/inbox/",
  search: new URLSearchParams(),
  router: {
    push: (() => undefined) as (href: string) => void,
    replace: (() => undefined) as (href: string) => void,
    refresh: () => undefined,
    prefetch: () => undefined,
    back: () => undefined,
  },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => navigation.router,
  useSearchParams: () => navigation.search,
  redirect: vi.fn(),
  notFound: vi.fn(),
}));

// jsdom's <dialog> has no showModal() or close(): enough of both for the dialogs' tests
if (typeof HTMLDialogElement !== "undefined" && !HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
