// /settings/connections/: one card per integration (GET connections/): Razorpay, Shiprocket, the manual carrier,
// MSG91, WhatsApp (not before Phase D), Amazon SES, the buckets, the error tracker, Google sign-in, ERPNext. Each says
// whether it works, since when, test or live, and what to do when it does not; Test, Replace the keys, the mode and
// the circuit for whoever may (components/modules/settings/connections.tsx).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { ConnectionCardView } from "@/components/modules/settings/connections";
import { PageHeader } from "@/components/shell/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { listConnections } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const words = copy.management.connections;

export const metadata: Metadata = { title: words.title };

export default async function ConnectionsPage() {
  const { transport, path } = await staffPage("/settings/connections/");
  const cards = await attempt(listConnections(transport), path);
  const now = requestTime();
  return (
    <>
      <PageHeader title={words.title} lead={words.lead} back={{ href: "/settings/", label: copy.settings.title }} />
      {cards instanceof ApiError ? (
        <Problem error={cards} />
      ) : cards.length ? (
        <div className="grid gap-5 min-[1100px]:grid-cols-2">
          {cards.map((card) => (
            <ConnectionCardView key={card.provider} card={card} now={now} />
          ))}
        </div>
      ) : (
        <EmptyState title={words.emptyTitle}>
          <p>{words.advice.not_configured}</p>
        </EmptyState>
      )}
    </>
  );
}
