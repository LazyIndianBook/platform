// The module's home (GET catalogue/summary/): what waits, each a count that opens its list: products the courier
// cannot be quoted for, GST disagreeing with the master, low and empty stock, back-in-stock requests, price, coupon
// and offer changes waiting for approval; and whether the prior-price rule is in force.
import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import type { CatalogueSummary } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate } from "@/lib/format";

type Card = { key: string; count: number; text: string; href: string };

export function cardsOf(summary: CatalogueSummary): Card[] {
  const words = copy.catalogue.cards;
  const cards: Card[] = [
    {
      key: "incomplete",
      count: summary.incomplete,
      text: words.incomplete(summary.incomplete),
      href: "/catalogue/products/?incomplete=true",
    },
    {
      key: "tax",
      count: summary.tax_problems,
      text: words.taxProblems(summary.tax_problems),
      href: "/catalogue/products/?tax_problem=true",
    },
    {
      key: "out",
      count: summary.out_of_stock,
      text: words.outOfStock(summary.out_of_stock),
      href: "/catalogue/stock/?state=out",
    },
    {
      key: "low",
      count: summary.low_stock,
      text: words.lowStock(summary.low_stock, summary.low_stock_line),
      href: "/catalogue/stock/?state=low",
    },
    {
      key: "approvals",
      count: summary.approvals,
      text: words.approvals(summary.approvals),
      href: "/approvals/?status=pending",
    },
  ];
  if (summary.stock_alerts !== null)
    cards.splice(4, 0, {
      key: "alerts",
      count: summary.stock_alerts,
      text: words.alerts(summary.stock_alerts),
      href: "/catalogue/#alerts",
    });
  return cards;
}

export function SummaryCards({ summary }: { summary: CatalogueSummary }) {
  const cards = cardsOf(summary);
  const waiting = cards.filter((card) => card.count > 0);
  return (
    <div className="flex flex-col gap-4">
      <Alert variant={summary.prior_price_applies ? "info" : "warning"} title={copy.catalogue.priorRuleTitle}>
        <p>
          {summary.prior_price_applies
            ? copy.catalogue.priorRuleOn
            : copy.catalogue.priorRuleFrom(formatDate(summary.prior_price_from))}
        </p>
      </Alert>
      {waiting.length ? (
        <ul className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(240px,100%),1fr))] gap-3 p-0">
          {waiting.map((card) => (
            <li key={card.key}>
              <Link
                href={card.href}
                className="flex min-h-11 flex-col gap-1 rounded-lg border border-border bg-card p-4 font-normal text-foreground no-underline hover:border-foreground"
              >
                <span className="font-mono text-2xl font-semibold">{card.count.toLocaleString("en-IN")}</span>
                <span>{card.text}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="m-0 text-muted-foreground">{copy.catalogue.nothingWaits}</p>
      )}
      <p className="m-0 text-sm text-muted-foreground">{copy.catalogue.productsOnSale(summary.products)}</p>
    </div>
  );
}
