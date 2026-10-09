// The App Router's hooks outside a Next app (vitest.setup.ts mocks next/navigation with these): a page and its search
// params that a test may set, and a router whose calls a test may watch.
export const navigation = {
  pathname: "/inbox/",
  search: new URLSearchParams(),
  router: {
    push: (() => undefined) as (href: string) => void,
    replace: (() => undefined) as (href: string, options?: { scroll?: boolean }) => void,
    refresh: (() => undefined) as () => void,
    prefetch: () => undefined,
    back: () => undefined,
  },
};
