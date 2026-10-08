"use client";

// useConfig(): the server's feature flags in client components, from the root layout's getConfig().
import { createContext, useContext } from "react";

import type { components } from "@/lib/api/schema";

type SiteConfig = components["schemas"]["Config"];

const ConfigContext = createContext<SiteConfig | null>(null);

export function ConfigProvider({ value, children }: { value: SiteConfig | null; children: React.ReactNode }) {
  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

/** null while the backend cannot be reached: callers show the unavailable state instead of guessing a flag. */
export function useConfig(): SiteConfig | null {
  return useContext(ConfigContext);
}
