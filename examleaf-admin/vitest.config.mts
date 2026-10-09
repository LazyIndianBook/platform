// Vitest: components in jsdom with Testing Library; the Playwright specs (e2e/) are not Vitest's.
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const src = fileURLToPath(new URL("./src", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": src,
      // server-only throws outside a server bundle; the modules that import it are tested for their pure parts
      "server-only": fileURLToPath(new URL("./vitest.empty.ts", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    // as next.config.ts's trailingSlash: <Link href="/books/x/"> keeps its slash
    env: { __NEXT_TRAILING_SLASH: "true" },
  },
});
