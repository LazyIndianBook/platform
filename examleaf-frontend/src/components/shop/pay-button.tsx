"use client";

// The pay page's button (Django's shop/checkout.js): asks the API for this order's Razorpay options (POST
// orders/<n>/payment/, or orders/t/<token>/payment/ for a guest's: the server makes Razorpay's order); on Pay, loads
// checkout.js with this page's CSP nonce (loadRazorpay: nothing of Razorpay's before the press), opens Razorpay's
// window, then posts its answer to …/payment/confirm/. The done page says what the API answered (paid, still being
// confirmed, or not completed); this button never claims success itself. Busy until the options are ready.
// Unavailable (503), not payable (400), a failed or refused payment: said in words, the order kept and the cart with
// it. A pay page that is not its own document reloads once first: only the pay page's CSP lets Razorpay in (S2).
// Direction A (Pay artboard; States "Payment failed"): when Razorpay reports a failure, the order is said to be kept,
// Try again opens Razorpay again, and cash on delivery is offered when the server allows it for this order (at the
// checkout: a new order, as the API cannot change this one's way of paying).
import { Lock, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { api, ApiError, personal } from "@/lib/api/client";
import { inr } from "@/lib/format";

import { documentIsPayPage, loadRazorpay, openRazorpay, type PaymentStart, type RazorpayResponse } from "./shop";

type State =
  | { kind: "loading" }
  | { kind: "ready"; options: PaymentStart }
  | { kind: "unavailable"; message: string }
  | { kind: "refused"; message: string };

export function PayButton({
  number,
  token,
  total,
  nonce,
  codInstead = false,
}: {
  number: string;
  /** a guest's order: paid by its link's secret */
  token?: string;
  total: string;
  nonce: string;
  /** after a failed payment, offer cash on delivery (the checkout, with it chosen) */
  codInstead?: boolean;
}) {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [scriptFailed, setScriptFailed] = useState(false);
  const [paying, setPaying] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [declined, setDeclined] = useState(false); // the problem is Razorpay's failure: nothing reached us to check

  useEffect(() => {
    if (!documentIsPayPage()) {
      window.location.reload(); // once: the reloaded document is this pay page, with Razorpay in its CSP
      return;
    }
    const controller = new AbortController();
    personal(
      token
        ? api.POST("/api/v1/orders/t/{token}/payment/", { params: { path: { token } }, signal: controller.signal })
        : api.POST("/api/v1/orders/{number}/payment/", { params: { path: { number } }, signal: controller.signal }),
    )
      .then((options) => setState({ kind: "ready", options }))
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        if (caught instanceof ApiError && caught.status === 400) setState({ kind: "refused", message: caught.message });
        // a guest's order that joined an account at log-in is paid signed in (its link answers 404 for paying)
        else if (caught instanceof ApiError && caught.status === 404 && token)
          setState({
            kind: "refused",
            message: "This order is now in your account: log in and pay it from My orders.",
          });
        else
          setState({
            kind: "unavailable",
            message: caught instanceof ApiError ? caught.message : "The payment service could not be reached.",
          });
      });
    return () => controller.abort();
  }, [number, token]);

  async function confirm(response: RazorpayResponse) {
    setPaying(true);
    try {
      await personal(
        token
          ? api.POST("/api/v1/orders/t/{token}/payment/confirm/", { params: { path: { token } }, body: response })
          : api.POST("/api/v1/orders/{number}/payment/confirm/", { params: { path: { number } }, body: response }),
      );
      router.replace(token ? `/checkout/t/${token}/done/` : `/checkout/${number}/done/`);
      router.refresh(); // the cart was emptied: the header's count
    } catch (caught) {
      setProblem(
        caught instanceof ApiError
          ? caught.message
          : "We could not reach ExamLeaf to confirm this payment. If money was taken from your account, we confirm the order or refund it by ourselves within a few minutes.",
      );
      setPaying(false);
    }
  }

  async function pay() {
    if (state.kind !== "ready" || paying) return;
    setProblem(null);
    setDeclined(false);
    setScriptFailed(false);
    setPaying(true);
    const Razorpay = await loadRazorpay(nonce).catch(() => null);
    if (!Razorpay) {
      setScriptFailed(true);
      setPaying(false);
      return;
    }
    openRazorpay(Razorpay, state.options, {
      success: (response) => void confirm(response),
      failure: (message) => {
        setProblem(message);
        setDeclined(true);
        setPaying(false);
      },
      dismiss: () => setPaying(false),
    });
  }

  if (state.kind === "refused") {
    return (
      <div className="flex flex-col gap-3 [&>*]:m-0">
        <Alert variant="warning" title={state.message}>
          <p>Nothing has been charged.</p>
        </Alert>
        <Link href="/cart/" className={buttonVariants({ variant: "primary", className: "self-start" })}>
          Back to the cart
        </Link>
      </div>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <div className="flex flex-col gap-3 [&>*]:m-0">
        <Alert variant="error" title={state.message}>
          <p>Your order is saved and nothing has been charged. Please try again in a few minutes.</p>
        </Alert>
        <Button type="button" className="self-start" onClick={() => window.location.reload()}>
          <RefreshCw aria-hidden="true" />
          Try again
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3.5 [&>*]:m-0">
      {state.kind === "ready" && state.options.test_mode ? (
        <Alert variant="warning" title="Test mode">
          <p>No real money is taken. Use Razorpay&apos;s test card or UPI ID.</p>
        </Alert>
      ) : null}
      {scriptFailed ? (
        <Alert variant="error" role="alert">
          <p>The payment window could not be loaded. Check your internet connection, then press Pay again.</p>
        </Alert>
      ) : null}
      {problem ? (
        <Alert variant="error" role="alert" title={declined ? problem : undefined}>
          {declined ? <p>Your order {number} is kept: you can pay it again for two days.</p> : <p>{problem}</p>}
        </Alert>
      ) : null}
      <Button type="button" size="lg" block busy={state.kind !== "ready" || paying} onClick={pay} className="min-h-14">
        {declined ? null : <Lock aria-hidden="true" />}
        {declined ? "Try again" : `Pay ${inr(total)}`}
      </Button>
      {declined && codInstead ? (
        <>
          <Link href="/checkout/?pay=cod" className={buttonVariants({ variant: "secondary", block: true })}>
            Pay cash on delivery instead
          </Link>
          <p className="text-sm leading-normal text-muted-foreground">
            Cash on delivery makes a new order at the checkout; this one is then left unpaid.
          </p>
        </>
      ) : null}
      <noscript>
        <Alert variant="error">
          <p>The payment window needs JavaScript.</p>
        </Alert>
      </noscript>
      <p className="text-sm leading-normal text-muted-foreground">
        {declined ? (
          <>
            If money did leave your account, it is refunded automatically. <Link href="/contact/">Contact us</Link> with
            the order number.
          </>
        ) : (
          "The button stays busy until Razorpay's window opens, and again while we check the payment. Closing the window doesn't charge you."
        )}
      </p>
    </div>
  );
}
