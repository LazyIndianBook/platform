"use client";

// The cart, Direction A (Cart artboard, Phone cart; Gaps "Cart coupon"; States "Cancel dialog" for Remove), an
// account's or a visitor's guest cart: the copies in the margin, each line a ruled row (cover, title, the price of one,
// Remove with its dialog, the copies stepper: a step is sent at once, a typed number when the box is left or Enter
// pressed, 0 asks first; the line's amount), what stops the checkout (the API's problems), then the summary on paper 2:
// the coupon (POST/DELETE cart/coupon/: the API's discount, or its refusal in words), the books, each saving, delivery
// at the next step, the total so far and Go to checkout. Every answer of the API is the whole cart, so the page shows
// exactly what it said; the header's count follows with a refresh.
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useRef, useState } from "react";

import { useTurnstile } from "@/components/auth/turnstile";
import { useConfig } from "@/components/providers/config-provider";
import { Alert } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { api, ApiError, personal } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { withNext } from "@/lib/auth/next-url";
import { inrShort } from "@/lib/format";
import { focusHere } from "@/lib/utils";

import { CopiesStepper } from "./copies-stepper";
import { OrderSummary } from "./order-summary";
import { ProductCover } from "./product-card";
import { copies, MAX_COPIES, SHOP_DIALOG } from "./shop";

type Cart = components["schemas"]["Cart"];
export type LineInfo = {
  cover: components["schemas"]["Product"]["cover"];
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
  notice,
}: {
  initial: Cart;
  info: Record<string, LineInfo>;
  /** a visitor's guest cart: the bot check on coupons (while the server has one) and the log-in line */
  guest?: boolean;
  /** under the heading: the shop-closed notice */
  notice?: React.ReactNode;
}) {
  const router = useRouter();
  const config = useConfig();
  const siteKey = config?.auth.turnstile_site_key ?? null;
  const [cart, setCart] = useState(initial);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Cart["items"][number] | null>(null);
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);
  const bot = useTurnstile(guest && cart.items.length && !cart.coupon ? siteKey : null, codeError);
  const list = useRef<HTMLUListElement>(null);

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
    if (!done) return;
    toast.success(`${line.title} has left your cart.`);
    // the line and its Remove button are gone: focus the list, or the empty cart's heading, not the page's start
    requestAnimationFrame(() => focusHere(list.current ?? document.querySelector<HTMLElement>("main h2, main h1")));
  }

  async function applyCoupon(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!code.trim()) return setCodeError("Type the code first.");
    setCodeError(null);
    setBusy("coupon");
    try {
      setCart(
        await personal(
          api.POST("/api/v1/cart/coupon/", {
            body: { code: code.trim(), ...(guest && siteKey ? { turnstile: bot.token } : {}) },
          }),
        ),
      );
      setCode("");
      router.refresh();
    } catch (caught) {
      setCodeError(failed(caught)); // the API's words: "This code cannot be applied to this cart."
    } finally {
      setBusy(null);
    }
  }

  if (!cart.items.length) {
    return (
      <div className="shop-sheet">
        <div className="sheet-margin nav:pt-[60px]" aria-hidden="true">
          [0]
        </div>
        <div className="sheet-body flex flex-col items-start gap-3.5 nav:pt-[44px] nav:pb-14 [&>*]:m-0">
          <h1 className="text-[32px] leading-[1.05] nav:text-[40px]">Your cart is empty</h1>
          {notice}
          <p className="text-[17px] text-ink/85">
            Each subject has two books: Sample Papers, and Solutions printed for working without a phone.
          </p>
          <Link href="/shop/" className={buttonVariants({ size: "lg" })}>
            Go to the shop
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="shop-sheet">
      <div className="sheet-margin nav:pt-16" aria-hidden="true">
        [{cart.count}]
      </div>
      <div className="sheet-body flex flex-col gap-5 nav:pt-[52px] nav:pb-16 [&>*]:m-0">
        <h1 className="text-[36px] leading-none nav:text-[56px]">Your cart</h1>
        {notice}
        {digitalOnly ? (
          <p className="text-muted-foreground">
            The revision course opens in your account as soon as the payment is confirmed.
          </p>
        ) : null}
        <ul
          ref={list}
          tabIndex={-1}
          aria-label={digitalOnly ? "In your cart" : "Books in your cart"}
          className="m-0 list-none border-t-[1.5px] border-foreground p-0 focus:outline-none"
        >
          {cart.items.map((line) => {
            const about = info[line.product];
            const draft = drafts[line.product];
            return (
              <li
                key={line.product}
                aria-busy={busy === line.product || undefined}
                className="grid grid-cols-[56px_minmax(0,1fr)] items-center gap-x-3.5 gap-y-1 border-b border-border py-3.5 nav:grid-cols-[64px_minmax(0,1fr)_auto_110px] nav:gap-x-5 nav:py-[18px]"
              >
                <span className="row-span-4 w-14 self-start nav:row-span-3 nav:w-16 nav:self-center">
                  {about ? <ProductCover product={{ ...about, title: line.title }} sizes="64px" /> : null}
                </span>
                <Link
                  href={`/shop/${line.product}/`}
                  className="col-start-2 row-start-1 font-head text-[18px] leading-[1.2] font-semibold text-foreground no-underline hover:underline nav:text-[21px]"
                >
                  {line.title}
                </Link>
                <span className="col-start-2 row-start-2 text-sm text-muted-foreground tabular-nums">
                  {inrShort(line.price)} each
                </span>
                {about?.digital ? (
                  <span className="col-start-2 row-start-3 text-muted-foreground nav:col-start-3 nav:row-span-3 nav:row-start-1">
                    1 (one per account)
                  </span>
                ) : (
                  <span className="col-start-2 row-start-3 justify-self-start py-1 nav:col-start-3 nav:row-span-3 nav:row-start-1 nav:py-0">
                    <CopiesStepper
                      id={`copies-${line.product}`}
                      label={line.title}
                      aria-label={`Copies of ${line.title}`}
                      min={0}
                      value={draft ?? String(line.quantity)}
                      busy={busy !== null}
                      onValue={(value, how) =>
                        how === "step"
                          ? setCopies(line, value)
                          : setDrafts((all) => ({ ...all, [line.product]: value }))
                      }
                      onBlur={() => draft !== undefined && setCopies(line, draft)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && draft !== undefined) {
                          event.preventDefault();
                          setCopies(line, draft);
                        }
                      }}
                    />
                  </span>
                )}
                <strong className="col-start-2 row-start-3 justify-self-end font-head text-[18px] leading-none font-semibold tabular-nums nav:col-start-4 nav:row-span-3 nav:row-start-1 nav:text-[22px]">
                  {inrShort(line.total)}
                </strong>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="col-start-2 row-start-4 -ml-4 justify-self-start text-sm font-semibold nav:row-start-3 nav:min-h-8"
                  onClick={() => busy === null && setRemoving(line)}
                  aria-disabled={busy !== null || undefined}
                >
                  Remove<span className="sr-only"> {line.title}</span>
                </Button>
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
        <p>
          <Link href="/shop/" className="inline-flex min-h-11 items-center font-bold">
            ← Keep shopping
          </Link>
        </p>
      </div>

      <aside className="shop-aside" aria-labelledby="cart-summary">
        <h2 id="cart-summary" className="text-[22px] leading-tight nav:text-[24px]">
          Summary
        </h2>
        {cart.coupon ? (
          cart.coupon_problem ? (
            <Alert variant="error">
              <p>
                <strong>Coupon {cart.coupon}:</strong> {cart.coupon_problem} Coupons are checked when you pay, too.
              </p>
              <p>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="-ml-4 min-h-11"
                  busy={busy === "coupon"}
                  onClick={() => send("coupon", api.DELETE("/api/v1/cart/coupon/"))}
                >
                  Remove the coupon
                </Button>
              </p>
            </Alert>
          ) : (
            // the coupon's amount is the summary's "Coupon <code>" row just below (the API's own label)
            <div className="flex flex-wrap items-center justify-between gap-x-3 rounded-[3px] border border-success-line bg-success-bg py-0.5 pr-0.5 pl-3 text-sm">
              <span>
                <strong>{cart.coupon}</strong> applied
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="min-h-11 px-3 text-sm"
                busy={busy === "coupon"}
                onClick={() => send("coupon", api.DELETE("/api/v1/cart/coupon/"))}
              >
                Remove<span className="sr-only"> the coupon</span>
              </Button>
            </div>
          )
        ) : (
          <form onSubmit={applyCoupon} noValidate className="flex flex-col gap-1.5">
            <label htmlFor="code" className="text-[15px] font-semibold">
              Coupon code
            </label>
            <div className="flex gap-2">
              <Input
                id="code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                autoComplete="off"
                autoCapitalize="characters"
                aria-invalid={codeError ? true : undefined}
                aria-describedby={codeError ? "code-error" : undefined}
                className="flex-1 font-mono uppercase placeholder:normal-case"
              />
              {/* while the bot check runs, a short word: its whole sentence would squeeze the field out */}
              <Button type="submit" variant="secondary" busy={busy === "coupon" || bot.waiting} className="min-h-12">
                {bot.waiting ? "Checking…" : "Apply"}
              </Button>
            </div>
            {codeError ? <FieldError id="code-error">{codeError}</FieldError> : null}
            {bot.widget}
          </form>
        )}
        <OrderSummary
          lines={[]}
          subtotal={cart.subtotal}
          savings={cart.savings}
          digital={digitalOnly}
          booksLabel={digitalOnly ? "Course" : `${cart.count} book${cart.count === 1 ? "" : "s"}`}
          shippingLabel="Delivery"
          shipping="From your state, next step"
          total={cart.total}
          totalLabel={digitalOnly ? "Total" : "Total so far"}
        />
        {cart.problems.length ? (
          // what stops the checkout is said beside the lines
          <Button type="button" size="lg" block disabled className="mt-2 min-h-14">
            Go to checkout
          </Button>
        ) : (
          <Link href="/checkout/" className={buttonVariants({ size: "lg", block: true, className: "mt-2 min-h-14" })}>
            Go to checkout
          </Link>
        )}
        <p className="text-sm leading-normal text-muted-foreground">
          {digitalOnly
            ? "UPI, card or net banking through Razorpay."
            : `UPI, card or net banking through Razorpay${config?.shop.cod ? ", or cash on delivery where it's offered" : ""}.`}
        </p>
        {guest ? (
          <p className="text-sm leading-normal text-muted-foreground">
            {course ? "The course opens in your ExamLeaf account: " : "No account needed. Have one? "}
            <Link href={withNext("/account/login/", "/cart/")}>
              {course ? "log in or register first" : "Log in first to use your saved addresses"}
            </Link>
            .
          </p>
        ) : null}
      </aside>

      <Dialog open={removing !== null} onOpenChange={(open) => (open ? null : setRemoving(null))}>
        <DialogContent className={SHOP_DIALOG}>
          <DialogHeader>
            {removing && info[removing.product]?.digital ? "Remove this course?" : "Remove this book?"}
          </DialogHeader>
          <DialogBody>
            <DialogDescription className="text-[15px] leading-relaxed text-ink/85">
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
