"use client";

// The refund dialog (POST orders/{number}/refunds/): the copies of each book (from 0), the shipping, the copies back
// into stock or not, and how the money goes back, with Razorpay's rules, the days each way takes and the API's own
// warnings (a payment older than 6 months) shown before the person confirms. A refund by bank or UPI takes the
// customer's account (sent once, kept encrypted and masked); for an online payment only with the customer's
// agreement. The sum shown is an estimate from the lines' invoiced values: the API computes the refund itself, and
// answers 201 (it ran, within the person's limit) or 202 (a change request waits for FINANCE: shown here). A refund
// for an inspected return sends the return and no lines (its lines are the return's).
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox, Radio } from "@/components/ui/choice";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { askRefund, type OrderDetail, type OrderLine, type RefundAsk } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { paise, rupees } from "./format";

/** The copies of a line still to refund. */
export const leftOf = (line: Pick<OrderLine, "quantity" | "refunded">) => Math.max(0, line.quantity - line.refunded);

/** An estimate of the refund in paise: each line's invoiced value per copy (the last copies of a line take what is
 *  left of it on the server, to the paisa), plus the shipping. */
export function estimate(
  lines: Pick<OrderLine, "id" | "invoiced" | "quantity">[],
  copies: Record<number, number>,
  shipping: string,
) {
  let total = 0;
  for (const line of lines) {
    const count = copies[line.id] ?? 0;
    if (count > 0 && line.quantity > 0) total += Math.round((paise(line.invoiced) * count) / line.quantity);
  }
  const extra = Number(shipping);
  return total + (Number.isFinite(extra) && extra > 0 ? paise(extra) : 0);
}

type Method = "source" | "bank";

export function RefundDialog({
  order,
  returnId,
  triggerLabel = copy.orders.refund.action,
  triggerVariant = "destructive",
}: {
  order: OrderDetail;
  /** An inspected return of this order: its lines are refunded. */
  returnId?: number;
  triggerLabel?: string;
  triggerVariant?: "primary" | "secondary" | "destructive";
}) {
  const id = useId();
  const router = useRouter();
  const options = order.refund;
  const methods = options.methods.filter((method): method is Method => method === "source" || method === "bank");
  const [open, setOpen] = useState(false);
  const [copies, setCopies] = useState<Record<number, number>>({});
  const [shipping, setShipping] = useState("");
  const [method, setMethod] = useState<Method>(methods[0] ?? "source");
  const [speed, setSpeed] = useState<"normal" | "optimum">("normal");
  const [payeeKind, setPayeeKind] = useState<"upi" | "account">("upi");
  const { run, busy, error, setError } = useAction();
  const online = options.payment_method === "razorpay";
  const lines = order.lines.filter((line) => !line.digital || leftOf(line) > 0);
  const byLine = returnId === undefined && !options.cancels;
  const sum = estimate(order.lines, copies, shipping);

  if (!methods.length) return null;

  const close = (next: boolean) => {
    setOpen(next);
    if (!next) setError(null);
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <Button size="sm" variant={triggerVariant} onClick={() => setOpen(true)}>
        {triggerLabel}
      </Button>
      <DialogContent className="w-[min(46rem,calc(100%-32px))]">
        <DialogHeader>{copy.orders.refund.title}</DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={async (event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            const text = (name: string) => String(form.get(name) ?? "").trim();
            const body: RefundAsk = {
              reason: text("reason"),
              restock: form.get("restock") === "on",
              speed,
              customer_agreed: form.get("customer_agreed") === "on",
              method,
            };
            if (returnId !== undefined) body.return = returnId;
            if (byLine) {
              const chosen = Object.entries(copies).filter(([, count]) => count > 0);
              if (chosen.length) body.lines = chosen.map(([item, quantity]) => ({ item: Number(item), quantity }));
              if (shipping.trim()) body.shipping = shipping.trim();
            }
            if (method === "bank")
              body.payee =
                payeeKind === "upi"
                  ? { upi: text("upi") }
                  : { account: text("account"), ifsc: text("ifsc"), name: text("holder") };
            const ok = await run(async () => {
              await askRefund(order.number ?? "", body);
            });
            if (!ok) return;
            setOpen(false);
            setCopies({});
            setShipping("");
            toast.success(copy.orders.refund.done);
            router.refresh();
          }}
        >
          <DialogBody>
            <DialogDescription>{copy.orders.refund.rules}</DialogDescription>
            {options.warnings.map((warning) => (
              <Alert key={warning} variant="warning" title={warning} />
            ))}
            {options.cancels ? <Alert variant="info" title={copy.orders.refund.cancels} /> : null}
          </DialogBody>
          <ErrorSummary
            error={error}
            idPrefix={`${id}-`}
            labels={{
              reason: copy.orders.refund.reason,
              shipping: copy.orders.refund.shipping,
              "payee.upi": copy.orders.refund.upi,
              "payee.account": copy.orders.refund.account,
              "payee.ifsc": copy.orders.refund.ifsc,
              "payee.name": copy.orders.refund.holder,
              customer_agreed: copy.orders.refund.agreed,
            }}
          />
          {byLine ? (
            <fieldset className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
              <legend className="mb-1 text-[15px] font-semibold">{copy.orders.refund.lines}</legend>
              {lines.map((line) => {
                const left = leftOf(line);
                return (
                  <div key={line.id} className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1.5">
                    <Field
                      id={`${id}-line-${line.id}`}
                      label={copy.orders.refund.copies(line.title)}
                      help={`${copy.orders.refund.left(left)} · ${rupees(line.invoiced)} ${copy.orders.lineColumns.invoiced.toLowerCase()}`}
                      className="min-w-0 flex-1"
                    >
                      <Input
                        type="number"
                        inputMode="numeric"
                        min={0}
                        max={left}
                        step={1}
                        disabled={left === 0}
                        value={String(copies[line.id] ?? 0)}
                        onChange={(event) => {
                          const value = Math.max(0, Math.min(left, Math.floor(Number(event.target.value) || 0)));
                          setCopies((current) => ({ ...current, [line.id]: value }));
                        }}
                        className="w-28"
                      />
                    </Field>
                  </div>
                );
              })}
              <Field
                id={`${id}-shipping`}
                label={copy.orders.refund.shipping}
                optional
                help={copy.orders.refund.shippingHelp(rupees(options.shipping_left))}
                error={fieldError(error, "shipping")}
              >
                <Input
                  inputMode="decimal"
                  value={shipping}
                  onChange={(event) => setShipping(event.target.value)}
                  className="w-36"
                  autoComplete="off"
                />
              </Field>
              <Checkbox name="restock">{copy.orders.refund.restock}</Checkbox>
            </fieldset>
          ) : null}

          <fieldset className="m-0 flex min-w-0 flex-col gap-1 border-0 p-0">
            <legend className="mb-1 text-[15px] font-semibold">{copy.orders.refund.method}</legend>
            {methods.map((each) => (
              <Radio key={each} name="method" value={each} checked={method === each} onChange={() => setMethod(each)}>
                <span className="flex flex-col">
                  <span>{copy.orders.refund.methods[each]}</span>
                  <span className="text-sm text-muted-foreground">
                    {each === "bank" ? copy.orders.refund.days.bank : copy.orders.refund.days.source}
                  </span>
                </span>
              </Radio>
            ))}
          </fieldset>

          {method === "source" ? (
            <fieldset className="m-0 flex min-w-0 flex-col gap-1 border-0 p-0">
              <legend className="mb-1 text-[15px] font-semibold">{copy.orders.refund.speed}</legend>
              {(["normal", "optimum"] as const).map((each) => (
                <Radio key={each} name="speed" value={each} checked={speed === each} onChange={() => setSpeed(each)}>
                  <span className="flex flex-col">
                    <span>{copy.orders.refund.speeds[each]}</span>
                    <span className="text-sm text-muted-foreground">
                      {each === "optimum" ? copy.orders.refund.days.optimum : copy.orders.refund.days.source}
                    </span>
                  </span>
                </Radio>
              ))}
            </fieldset>
          ) : (
            <fieldset className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
              <legend className="mb-1 text-[15px] font-semibold">{copy.orders.refund.payee}</legend>
              <div className="flex flex-wrap gap-x-6">
                {(["upi", "account"] as const).map((each) => (
                  <Radio
                    key={each}
                    name="payee_kind"
                    value={each}
                    checked={payeeKind === each}
                    onChange={() => setPayeeKind(each)}
                  >
                    {copy.orders.refund.payeeKinds[each]}
                  </Radio>
                ))}
              </div>
              {payeeKind === "upi" ? (
                <Field id={`${id}-payee.upi`} label={copy.orders.refund.upi} error={fieldError(error, "payee.upi")}>
                  <Input name="upi" autoComplete="off" spellCheck={false} data-no-draft="" />
                </Field>
              ) : (
                <>
                  <Field
                    id={`${id}-payee.account`}
                    label={copy.orders.refund.account}
                    error={fieldError(error, "payee.account")}
                  >
                    <Input name="account" inputMode="numeric" autoComplete="off" data-no-draft="" />
                  </Field>
                  <Field
                    id={`${id}-payee.ifsc`}
                    label={copy.orders.refund.ifsc}
                    error={fieldError(error, "payee.ifsc")}
                  >
                    <Input name="ifsc" autoComplete="off" autoCapitalize="characters" data-no-draft="" />
                  </Field>
                  <Field
                    id={`${id}-payee.name`}
                    label={copy.orders.refund.holder}
                    error={fieldError(error, "payee.name")}
                  >
                    <Input name="holder" autoComplete="off" data-no-draft="" />
                  </Field>
                </>
              )}
              {online ? <Checkbox name="customer_agreed">{copy.orders.refund.agreed}</Checkbox> : null}
            </fieldset>
          )}

          <Field
            id={`${id}-reason`}
            label={copy.orders.refund.reason}
            help={copy.orders.refund.reasonHelp}
            error={fieldError(error, "reason")}
          >
            <Textarea name="reason" rows={2} aria-required="true" />
          </Field>

          {byLine ? (
            <p className="m-0 text-[15px] font-semibold" aria-live="polite">
              {sum > 0 ? copy.orders.refund.amount(rupees(sum / 100)) : copy.orders.refund.nothing}
            </p>
          ) : null}

          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary">{copy.common.cancel}</Button>
            </DialogClose>
            <Button type="submit" variant="destructive" busy={busy}>
              {copy.orders.refund.submit}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
