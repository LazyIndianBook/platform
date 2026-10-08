"use client";

// The cart (Cart artboard; Django's shop/cart.html), an account's or a visitor's guest cart: each line with its copies stepper (a step is sent at
// once, a typed number when the box is left or Enter pressed; 0 asks first), Remove with its dialog, the coupon form,
// what stops the checkout (the API's problems), and the summary: Books, each saving, Shipping at checkout, the total
// before shipping. Every answer of the API is the whole cart, so the page shows exactly what it said; the header's
// count follows with a refresh.
import { ArrowRight, Tag } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Turnstile } from "@/components/auth/turnstile";
import { useConfig } from "@/components/providers/config-provider";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api, ApiError, personal } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { withNext } from "@/lib/auth/next-url";
import { inr } from "@/lib/format";

import { CopiesStepper } from "./copies-stepper";
import { OrderSummary } from "./order-summary";
import { ProductCover } from "./product-card";
import { copies, MAX_COPIES } from "./shop";

type Cart = components["schemas"]["Cart"];
export type LineInfo = {
  cover: string | null;
  subject: string | null;
  kind: components["schemas"]["ProductKindEnum"];
  digital: boolean;
};

const failed = (caught: unknown) =>
  caught instanceof ApiError ? caught.message : "That did not work. Check your connection, then try again.";

export function CartView({
  initial,
  info,
  guest = false,
}: {
  initial: Cart;
  info: Record<string, LineInfo>;
  /** a visitor's guest cart: the bot check on coupons (while the server has one) and the log-in line */
  guest?: boolean;
}) {
  const router = useRouter();
  const siteKey = useConfig()?.auth.turnstile_site_key ?? null;
  const [turnstile, setTurnstile] = useState("");
  const [cart, setCart] = useState(initial);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Cart["items"][number] | null>(null);
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);

  const digitalOnly = cart.items.length > 0 && cart.items.every((line) => info[line.product]?.digital);
  const course = cart.items.some((line) => info[line.product]?.digital);

  async function send(what: string, call: Promise<{ data?: Cart; error?: unknown; response: Response }>) {
    setBusy(what);
    setError(null);
    try {
      setCart(await personal(call));
      router.refresh();
      return true;
    } catch (caught) {
      setError(failed(caught));
      return false;
    } finally {
      setBusy(null);
    }
  }

  function setCopies(line: Cart["items"][number], value: string) {
    const count = copies(value);
    if (count === null) return setError(`Enter a number of copies from 0 to ${MAX_COPIES}.`);
    setDrafts((all) => {
      const rest = { ...all };
      delete rest[line.product];
      return rest;
    });
    if (count === line.quantity) return;
    if (count === 0) return setRemoving(line);
    void send(
      line.product,
      api.PATCH("/api/v1/cart/items/{product}/", {
        params: { path: { product: line.product } },
        body: { quantity: count },
      }),
    );
  }

  async function remove(line: Cart["items"][number]) {
    setRemoving(null);
    const done = await send(
      line.product,
      api.DELETE("/api/v1/cart/items/{product}/", { params: { path: { product: line.product } } }),
    );
    if (done) toast.success(`${line.title} has left your cart.`);
  }

  async function applyCoupon(event: React.FormEvent) {
    event.preventDefault();
    if (!code.trim()) return setCodeError("Type the code first.");
    setCodeError(null);
    setBusy("coupon");
    try {
      setCart(
        await personal(
          api.POST("/api/v1/cart/coupon/", {
            body: { code: code.trim(), ...(guest && siteKey ? { turnstile } : {}) },
          }),
        ),
      );
      setCode("");
      router.refresh();
    } catch (caught) {
      setCodeError(failed(caught));
    } finally {
      setBusy(null);
    }
  }

  if (!cart.items.length) {
    return (
      <EmptyState
        art="cart"
        title="Your cart is empty"
        action={
          <Link href="/shop/" className={buttonVariants({ variant: "primary" })}>
            See the books
          </Link>
        }
      >
        <p>Each subject has a Sample Papers book and a Solutions book, delivered anywhere in India.</p>
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-wrap items-start gap-8">
      <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-4 [&>*]:m-0">
        <p className="text-muted-foreground">
          {digitalOnly
            ? "The revision course is in your cart: it opens in your account as soon as the payment is confirmed."
            : `${cart.count} book${cart.count === 1 ? "" : "s"} in your cart. Copies and coupon can still change at checkout.`}
        </p>
        <ul
          aria-label={digitalOnly ? "In your cart" : "Books in your cart"}
          className="m-0 list-none border-t border-border p-0"
        >
          {cart.items.map((line) => {
            const about = info[line.product];
            const draft = drafts[line.product];
            return (
              <li
                key={line.product}
                aria-busy={busy === line.product || undefined}
                className="flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-border py-4"
              >
                <span className="w-14 shrink-0">
                  {about ? <ProductCover product={{ ...about, title: line.title }} sizes="56px" /> : null}
                </span>
                <span className="flex min-w-0 flex-[1_1_200px] flex-col items-start">
                  <Link href={`/shop/${line.product}/`} className="font-semibold">
                    {line.title}
                  </Link>
                  <span className="text-[15px] text-muted-foreground tabular-nums">{inr(line.price)} each</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="-ml-3"
                    onClick={() => setRemoving(line)}
                    disabled={busy !== null}
                  >
                    Remove
                  </Button>
                </span>
                {about?.digital ? (
                  <span className="text-muted-foreground">1 (one per account)</span>
                ) : (
                  <CopiesStepper
                    id={`copies-${line.product}`}
                    label={line.title}
                    aria-label={`Copies of ${line.title}`}
                    min={0}
                    value={draft ?? String(line.quantity)}
                    disabled={busy !== null}
                    onValue={(value, how) =>
                      how === "step" ? setCopies(line, value) : setDrafts((all) => ({ ...all, [line.product]: value }))
                    }
                    onBlur={() => draft !== undefined && setCopies(line, draft)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && draft !== undefined) {
                        event.preventDefault();
                        setCopies(line, draft);
                      }
                    }}
                  />
                )}
                <strong className="num ml-auto min-w-24">{inr(line.total)}</strong>
              </li>
            );
          })}
        </ul>
        {error ? <FieldError role="alert">{error}</FieldError> : null}
        {cart.problems.map((problem) => (
          <Alert key={problem} variant="warning" title="Before you check out">
            <p>{problem}</p>
          </Alert>
        ))}
      </div>

      <Card className="flex-[1_1_320px]">
        <CardHeader>
          <CardTitle>Summary</CardTitle>
        </CardHeader>
        <CardContent className="gap-5">
          <OrderSummary
            lines={[]}
            subtotal={cart.subtotal}
            savings={cart.savings}
            digital={digitalOnly}
            shipping="at checkout, from your state"
            total={cart.total}
            totalLabel={digitalOnly ? "Total" : "Total before shipping"}
          />
          {cart.coupon ? (
            <div className="flex flex-col gap-2 [&>*]:m-0">
              {cart.coupon_problem ? (
                <Alert variant="warning">
                  <p>
                    Coupon {cart.coupon}: {cart.coupon_problem}
                  </p>
                </Alert>
              ) : null}
              <p className="flex flex-wrap items-center gap-2">
                <Badge variant="gold">
                  <Tag aria-hidden="true" />
                  {cart.coupon}
                  {cart.coupon_problem ? "" : " applied"}
                </Badge>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  busy={busy === "coupon"}
                  onClick={() => send("coupon", api.DELETE("/api/v1/cart/coupon/"))}
                >
                  Remove coupon
                </Button>
              </p>
            </div>
          ) : (
            <form onSubmit={applyCoupon} className="flex items-start gap-2" noValidate>
              <Field id="code" label="Coupon code" error={codeError} className="flex-1">
                <Input
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  autoComplete="off"
                  autoCapitalize="characters"
                />
              </Field>
              <Button type="submit" variant="secondary" busy={busy === "coupon"} className="mt-7 min-h-12">
                Apply
              </Button>
            </form>
          )}
          {guest && siteKey && !cart.coupon ? <Turnstile siteKey={siteKey} onToken={setTurnstile} /> : null}
          {cart.problems.length ? (
            // what stops the checkout is said above, line by line
            <Button type="button" variant="accent" size="lg" block disabled>
              Checkout
              <ArrowRight aria-hidden="true" />
            </Button>
          ) : (
            <Link href="/checkout/" className={buttonVariants({ variant: "accent", size: "lg", block: true })}>
              Checkout
              <ArrowRight aria-hidden="true" />
            </Link>
          )}
          <Link href="/shop/" className={buttonVariants({ variant: "secondary", block: true })}>
            Add more books
          </Link>
          {guest ? (
            <p className="text-[15px] text-muted-foreground">
              {course ? "The course opens in your ExamLeaf account: " : "No account needed. Have one? "}
              <Link href={withNext("/account/login/", "/cart/")}>
                {course ? "log in or register first" : "Log in first to use your saved addresses"}
              </Link>
              .
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={removing !== null} onOpenChange={(open) => (open ? null : setRemoving(null))}>
        <DialogContent>
          <DialogHeader>
            {removing && info[removing.product]?.digital ? "Remove this course?" : "Remove this book?"}
          </DialogHeader>
          <DialogBody>
            <DialogDescription>
              {removing?.title} leaves your cart. You can add it again from the shop.
            </DialogDescription>
          </DialogBody>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="secondary" autoFocus>
                Keep it
              </Button>
            </DialogClose>
            <Button type="button" variant="destructive" onClick={() => removing && remove(removing)}>
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
