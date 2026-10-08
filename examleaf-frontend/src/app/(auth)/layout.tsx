// Log-in, register and recovery pages: never indexed; each page frames itself with AuthSheet (Log in, Register) or
// AuthCard (the narrow steps), src/components/auth/auth-card.tsx, on the paper.
import type { Metadata } from "next";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return children;
}
