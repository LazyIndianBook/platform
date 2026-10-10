"use client";
// A data request's requester as the API sends it: masked, with Reveal (a reason, logged as a sensitive read,
// re-authenticated, throttled) for whoever holds staff.reveal_contact, as a customer's contact and a nominee's are.
import { MaskedValue } from "@/components/data/masked-value";
import { useCan } from "@/components/shell/manifest";
import { type DataRequest, revealDataRequester } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";

export function RequesterContact({ request }: { request: Pick<DataRequest, "id" | "requester"> }) {
  const can = useCan();
  return (
    <MaskedValue
      masked={request.requester}
      what={copy.privacy.requesterWhat}
      reveal={can(P.usersReveal) ? (reason) => revealDataRequester(request.id, reason) : undefined}
    />
  );
}
