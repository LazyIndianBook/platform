"use client";

// A customer's nominee on their record (GET privacy/nominees/{user}/, recorded as a look at their data): the name, the
// relation, the contact masked with Reveal (POST reveal/ with a reason: logged, re-authenticated, throttled), when it
// was recorded and whether a claim proved it.
import { MaskedValue } from "@/components/data/masked-value";
import { Facts } from "@/components/data/record-page";
import { useCan } from "@/components/shell/manifest";
import { type AccountNominee, revealNominee } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

export function NomineeFacts({ nominee }: { nominee: AccountNominee }) {
  const can = useCan();
  const found = nominee.nominee;
  if (!found) return <p className="m-0 text-[15px] text-muted-foreground">{copy.legal.noNominee}</p>;
  return (
    <Facts
      items={[
        { label: copy.legal.nomineeName, value: found.name },
        { label: copy.legal.nomineeRelation, value: found.relation || copy.common.none },
        {
          label: copy.legal.nomineeContact,
          value: (
            <MaskedValue
              masked={found.contact}
              what={copy.legal.nomineeContactWhat}
              reveal={can(P.usersReveal) ? (reason) => revealNominee(nominee.user, reason) : undefined}
            />
          ),
        },
        { label: copy.legal.nomineeRecorded, value: formatDateTime(found.updated) },
        {
          label: copy.legal.nomineeVerified,
          value: found.verified_at ? formatDateTime(found.verified_at) : copy.legal.notVerified,
        },
      ]}
    />
  );
}
