"use client";

// The pay page's button (Django's shop/checkout.js): asks the API for this order's Razorpay options (POST
// orders/<n>/payment/, or orders/t/<token>/payment/ for a guest's: the server makes Razorpay's order), loads
// checkout.js with this page's CSP nonce, opens Razorpay's window, then posts its answer to …/payment/confirm/. The done page says what the API answered
// (paid, still being confirmed, or not completed); this button never claims success itself. Busy until both the
// options and the script are ready. Unavailable (503), not payable (400), a failed or refused payment: said in words,
// the order kept and the cart with it.
import { Lock, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Script from "next/script";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { api, ApiError, personal } from "@/lib/api/client";
import { inr } from "@/lib/format";

import { openRazorpay, type PaymentStart, type RazorpayConstructor, type RazorpayResponse } from "./shop";

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
}: {
  number: string;
  /** a guest's order: paid by its link's secret */
  token?: string;
  total: string;
  nonce: string;
}) {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [script, setScript] = useState<"loading" | "ready" | "failed">("loading");
  const [paying, setPaying] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
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

  function pay() {
    if (state.kind !== "ready") return;
    const Razorpay = (window as unknown as { Razorpay?: RazorpayConstructor }).Razorpay;
    if (!Razorpay) return setScript("failed");
    setProblem(null);
    setPaying(true);
    openRazorpay(Razorpay, state.options, {
      success: (response) => void confirm(response),
      failure: (message) => {
        setProblem(message);
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

  const ready = state.kind === "ready" && script === "ready";
  return (
    <div className="flex flex-col gap-3 [&>*]:m-0">
      <Script
        src="https://checkout.razorpay.com/v1/checkout.js"
        nonce={nonce}
        strategy="afterInteractive"
        onReady={() => setScript("ready")}
        onError={() => setScript("failed")}
      />
      {state.kind === "ready" && state.options.test_mode ? (
        <Alert variant="warning" title="Test mode">
          <p>No real money is taken. Use Razorpay&apos;s test card or UPI ID.</p>
        </Alert>
      ) : null}
      {script === "failed" ? (
        <Alert variant="error" role="alert">
          <p>The payment window could not be loaded. Check your internet connection and reload this page.</p>
        </Alert>
      ) : null}
      {problem ? (
        <Alert variant="error" role="alert">
          <p>{problem}</p>
        </Alert>
      ) : null}
      <Button
        type="button"
        variant="accent"
        size="lg"
        block
        busy={!ready || paying}
        disabled={script === "failed"}
        onClick={pay}
      >
        <Lock aria-hidden="true" />
        Pay {inr(total)}
      </Button>
      <noscript>
        <Alert variant="error">
          <p>The payment window needs JavaScript.</p>
        </Alert>
      </noscript>
      <p className="text-[15px] text-muted-foreground">
        UPI, cards, net banking and wallets, through Razorpay. Nothing is charged until you confirm in the Razorpay
        window.
      </p>
    </div>
  );
}
