// Log-in, register and recovery pages: never indexed; each page frames its card with AuthSection
// (src/components/auth/auth-card.tsx) on the paper's alternate colour.
import type { Metadata } from "next";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return children;
}
