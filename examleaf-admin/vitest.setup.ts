import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(cleanup);

// The App Router's hooks outside a Next app: src/test/navigation.ts holds the page, its search params and the router,
// which a test may set or watch.
vi.mock("next/navigation", async () => {
  const { navigation } = await import("./src/test/navigation");
  return {
    usePathname: () => navigation.pathname,
    useRouter: () => navigation.router,
    useSearchParams: () => navigation.search,
    redirect: vi.fn(),
    notFound: vi.fn(),
  };
});

// jsdom lays nothing out, so it has no scrollIntoView (the lists' j and k call it) and no ResizeObserver (the banners')
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

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
