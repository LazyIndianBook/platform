"use client";

// The session manifest (GET session/) for client components, kept in memory only (React context, never
// localStorage). It draws the console and nothing more: the API checks every call. After a refusal by role or scope
// the page is rendered again from the server, which reads the manifest afresh (research 1.7).
import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect } from "react";

import { MANIFEST_STALE } from "@/lib/api/client";
import type { Manifest } from "@/lib/api/staff";
import { has } from "@/lib/modules";

const ManifestContext = createContext<Manifest | null>(null);

export function ManifestProvider({ manifest, children }: { manifest: Manifest; children: React.ReactNode }) {
  const router = useRouter();
  useEffect(() => {
    const stale = () => router.refresh();
    window.addEventListener(MANIFEST_STALE, stale);
    return () => window.removeEventListener(MANIFEST_STALE, stale);
  }, [router]);
  return <ManifestContext.Provider value={manifest}>{children}</ManifestContext.Provider>;
}

export function useManifest(): Manifest {
  const manifest = useContext(ManifestContext);
  if (!manifest) throw new Error("useManifest() belongs inside the panel's ManifestProvider");
  return manifest;
}

/** can(permission): whether the manifest lists it, to decide what to draw. */
export function useCan(): (permission: string) => boolean {
  const manifest = useManifest();
  return (permission) => has(manifest, permission);
}
