// What a customer bought (GET users/{id}/commerce/, from the live orders; opening it is a recorded read): the counts of
// their orders, and for an adult the money (spent, refunded, spent less refunded, the average order), the first and
// the latest order, the saved addresses (masked) and the tags staff put on their orders. For a student under 18 the
// counts alone: the API sends nothing else. These are records of what happened: the console works out no forecast, no
// group and no score.
import { StatusChip } from "@/components/data/status-chip";
import { Facts } from "@/components/data/record-page";
import { rupees } from "@/components/modules/orders/format";
import type { CustomerCommerce } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate } from "@/lib/format";

export function CommerceSummary({ commerce }: { commerce: CustomerCommerce }) {
  const words = copy.customers.commerce;
  if (!commerce.orders) return <p className="m-0 text-[15px] text-muted-foreground">{words.none}</p>;
  const counts = [
    { label: words.orders, value: String(commerce.orders) },
    { label: words.kept, value: String(commerce.kept) },
    { label: words.cancelled, value: String(commerce.cancelled) },
    { label: words.returns, value: String(commerce.returns) },
    { label: words.rtos, value: String(commerce.rtos) },
  ];
  if (commerce.child) {
    return (
      <div className="flex flex-col gap-3">
        <Facts items={counts} />
        <p className="m-0 text-[15px] text-muted-foreground">{words.child}</p>
      </div>
    );
  }
  const money = [
    { label: words.spent, value: rupees(commerce.spent) },
    { label: words.refunded, value: rupees(commerce.refunded) },
    { label: words.lifetime, value: rupees(commerce.lifetime_value) },
    ...(commerce.average_order !== null ? [{ label: words.average, value: rupees(commerce.average_order) }] : []),
  ];
  const dates = [
    ...(commerce.first_order_at ? [{ label: words.first, value: formatDate(commerce.first_order_at) }] : []),
    ...(commerce.last_order_at ? [{ label: words.last, value: formatDate(commerce.last_order_at) }] : []),
  ];
  const addresses = commerce.addresses ?? [];
  const tags = commerce.tags ?? [];
  return (
    <div className="flex flex-col gap-5">
      <Facts items={[...counts, ...money, ...dates]} />
      <div className="flex flex-col gap-1.5">
        <h3 className="m-0 text-[15px] font-semibold">{words.addresses}</h3>
        {addresses.length ? (
          <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
            {addresses.map((address, index) => (
              <li key={`${address.pin}-${index}`} className="flex flex-wrap items-center gap-x-2">
                <span>{words.addressLine(address.city, address.district, address.state, address.pin)}</span>
                <span className="font-mono text-[14px] text-muted-foreground">{address.phone}</span>
                {address.is_default ? <StatusChip tone="stopped">{words.defaultAddress}</StatusChip> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{words.noAddresses}</p>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        <h3 className="m-0 text-[15px] font-semibold">{words.tags}</h3>
        {tags.length ? (
          <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
            {tags.map((tag) => (
              <li key={tag.name}>
                <StatusChip tone="stopped">{words.tagLine(tag.name, tag.orders)}</StatusChip>
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{words.noTags}</p>
        )}
      </div>
    </div>
  );
}
