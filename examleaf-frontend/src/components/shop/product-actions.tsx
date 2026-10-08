"use client";

// The product page's islands, Direction A (Product artboard, Phone product, States "Shop closed and out of stock").
// AddToCart: "Choose" as radio cards when the book also comes in a bundle (BEST VALUE stamped on a bundle that saves),
// the copies (one for a course), Add to cart with the line's price, and Buy now (the same, then the checkout); POST
// cart/items/ (a visitor's guest cart, or the account's), then the cart with a toast. While it is sent both buttons
// wait and a second press, or Enter, sends nothing. On a phone the copies and Add stay at the bottom of the screen
// (.buy-bar, shop.css). StockAlert: "Email me when it is back", to the account's own address. ReviewForm: for a buyer
// whose order of it was delivered (the API says can_review), shown once staff read it.
import { Mail } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectableCard } from "@/components/ui/choice";
import { Field, FieldError } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { api, ApiError, ensureCsrfCookie, personal } from "@/lib/api/client";
import { withNext } from "@/lib/auth/next-url";
import { inrShort } from "@/lib/format";

import { CopiesStepper } from "./copies-stepper";
import { copies } from "./shop";

const failed = (caught: unknown) =>
  caught instanceof ApiError ? caught.message : "That did not work. Check your connection, then try again.";

export type BuyOption = {
  slug: string;
  title: string;
  label: string;
  price: string;
  mrp: string;
  inStock: boolean;
  digital: boolean;
  best?: boolean;
};

/** An option's words and price (Product artboard; Phone product: the saving under the label, the MRP under the price,
 *  no stamp). The price is Source Serif; the MRP is struck through and the saving said only when they differ. */
function OptionText({ item }: { item: BuyOption }) {
  const saving = Number(item.mrp) - Number(item.price);
  return (
    <span className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4">
      <span className="flex min-w-0 flex-col gap-1">
        <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-base leading-snug font-semibold nav:text-[17px]">
          {item.label}
          {item.best ? (
            <Badge variant="stamp" className="max-nav:hidden">
              Best value
            </Badge>
          ) : null}
          {item.inStock ? null : (
            <span className="font-mono text-xs font-semibold text-hard uppercase">Out of stock</span>
          )}
        </span>
        {saving > 0 ? (
          <span className="text-[13px] font-bold text-success-fg nav:hidden">
            Save {inrShort(saving)}
            {item.best ? " · best value" : ""}
          </span>
        ) : null}
      </span>
      <span className="flex flex-col items-end tabular-nums nav:flex-row nav:items-baseline nav:gap-x-2.5">
        <span className="font-head text-[20px] leading-none font-semibold nav:text-[26px]">{inrShort(item.price)}</span>
        {saving > 0 ? (
          <>
            <s className="text-[13px] text-muted-foreground nav:text-base">
              <span className="sr-only">MRP </span>
              {inrShort(item.mrp)}
            </s>
            <span className="hidden text-[15px] font-bold whitespace-nowrap text-success-fg nav:inline">
              Save {inrShort(saving)} ({Math.round((saving / Number(item.mrp)) * 100)}%)
            </span>
          </>
        ) : null}
      </span>
    </span>
  );
}

export function AddToCart({
  options,
  compact = false,
  note,
}: {
  options: BuyOption[];
  /** one copy, no copies box, no Buy now */
  compact?: boolean;
  /** between the choice and the buttons (the product page's facts, on a phone) */
  note?: React.ReactNode;
}) {
  const router = useRouter();
  const [chosen, setChosen] = useState(options.find((option) => option.inStock)?.slug ?? options[0].slug);
  const [count, setCount] = useState("1");
  const [busy, setBusy] = useState<"cart" | "checkout" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sending = useRef(false); // a second press (or Enter) in the same moment as the first sends nothing
  const option = options.find((item) => item.slug === chosen) ?? options[0];
  const quantity = option.digital ? 1 : copies(count);

  async function add(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending.current) return;
    const then =
      (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "checkout" ? "checkout" : "cart";
    if (!quantity) {
      setError("Enter a number of copies from 1 to 20.");
      return;
    }
    sending.current = true;
    setBusy(then);
    setError(null);
    try {
      await ensureCsrfCookie(); // a visitor's first change: the guest cart
      await personal(api.POST("/api/v1/cart/items/", { body: { product: option.slug, quantity } }));
      toast.success(`${option.title} is in your cart.`);
      router.push(then === "checkout" ? "/checkout/" : "/cart/");
      router.refresh(); // the header's cart count
    } catch (caught) {
      setError(failed(caught));
      setBusy(null);
      sending.current = false;
    }
  }

  const line = inrShort(Number(option.price) * (quantity || 1));
  return (
    <form onSubmit={add} className="flex flex-col gap-4" noValidate>
      {options.length > 1 ? (
        <fieldset className="m-0 flex min-w-0 flex-col gap-2.5 border-0 p-0">
          <legend className="mb-2.5 font-mono text-xs leading-none font-medium tracking-[0.06em] text-muted-foreground uppercase">
            Choose
          </legend>
          {options.map((item) => (
            <SelectableCard
              key={item.slug}
              name="product"
              value={item.slug}
              checked={chosen === item.slug}
              disabled={!item.inStock}
              onChange={() => setChosen(item.slug)}
              className="items-center gap-3.5 bg-card p-3.5 has-checked:border-foreground has-checked:p-[13px] nav:px-5 nav:py-[18px] nav:has-checked:px-[19px] nav:has-checked:py-[17px] [&>input]:mt-0 [&>span]:flex-1"
            >
              <OptionText item={item} />
            </SelectableCard>
          ))}
        </fieldset>
      ) : null}
      {note}
      <div className="buy-bar">
        {option.digital || compact ? null : (
          <Field id="copies" label="Copies" className="max-nav:[&>label]:sr-only">
            <CopiesStepper value={count} onValue={(value) => setCount(value)} label={option.title} tall busy={!!busy} />
          </Field>
        )}
        <Button
          type="submit"
          size="lg"
          className="min-h-[50px] flex-1 nav:min-h-14"
          busy={busy === "cart"}
          aria-disabled={busy === "checkout" || undefined}
          disabled={!option.inStock}
        >
          {/* "Add · ₹299" on a phone (Phone product), the whole words for everyone else and for screen readers */}
          <span aria-hidden="true">
            Add<span className="max-nav:hidden"> to cart</span> · {line}
          </span>
          <span className="sr-only">Add to cart · {line}</span>
        </Button>
        {compact ? null : (
          <Button
            type="submit"
            name="then"
            value="checkout"
            variant="secondary"
            size="lg"
            className="min-h-14 max-nav:hidden"
            busy={busy === "checkout"}
            aria-disabled={busy === "cart" || undefined}
            disabled={!option.inStock}
          >
            Buy now
          </Button>
        )}
      </div>
      {error ? <FieldError role="alert">{error}</FieldError> : null}
    </form>
  );
}

export function StockAlert({ slug, signedIn, here }: { slug: string; signedIn: boolean; here: string }) {
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<{ ok: boolean; text: string } | null>(null);

  async function ask() {
    setBusy(true);
    try {
      const sent = await personal(api.POST("/api/v1/products/{slug}/stock-alert/", { params: { path: { slug } } }));
      setAnswer({ ok: true, text: sent.detail });
    } catch (caught) {
      setAnswer({ ok: false, text: failed(caught) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 [&>*]:m-0">
      <p className="text-[15px] text-muted-foreground">
        We email you once, when it is back. Nothing else is sent to that address.
      </p>
      {!signedIn ? (
        <p>
          <Link href={withNext("/account/login/", here)} className="font-semibold">
            Log in first
          </Link>
          : we email the address of your account.
        </p>
      ) : answer?.ok ? (
        <Alert variant="success">
          <p>{answer.text}</p>
        </Alert>
      ) : (
        <div className="flex flex-col gap-2">
          <Button type="button" variant="secondary" className="self-start" busy={busy} onClick={ask}>
            <Mail aria-hidden="true" />
            Email me when it is back
          </Button>
          {answer ? <FieldError role="alert">{answer.text}</FieldError> : null}
        </div>
      )}
    </div>
  );
}

const RATINGS = [5, 4, 3, 2, 1];

export function ReviewForm({ slug, what }: { slug: string; what: "book" | "course" }) {
  const router = useRouter();
  const [rating, setRating] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [sent, setSent] = useState(false);

  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!rating) {
      setError(
        new ApiError(400, "invalid", "Choose a rating from 1 to 5.", { rating: ["Choose a rating from 1 to 5."] }),
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await personal(
        api.POST("/api/v1/products/{slug}/reviews/", { params: { path: { slug } }, body: { rating, text } }),
      );
      setSent(true);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "unavailable", failed(caught)));
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <Alert variant="success" title="Thank you for your review">
        <p>It shows here once we have read it.</p>
      </Alert>
    );
  }
  return (
    <form
      onSubmit={send}
      className="flex max-w-[40rem] flex-col gap-4 rounded-lg border-[1.5px] border-foreground bg-card p-5 nav:p-8"
      noValidate
    >
      <div className="flex flex-col gap-1 [&>*]:m-0">
        <h3 className="text-[24px]">Review this {what}</h3>
        <p className="text-[15px] text-muted-foreground">From buyers whose order of it has been delivered.</p>
      </div>
      <fieldset className="m-0 border-0 p-0" aria-describedby={error?.fields.rating ? "rating-error" : undefined}>
        <legend id="rating" tabIndex={-1} className="mb-1 font-semibold">
          Your rating
          <span aria-hidden="true" className="text-destructive">
            {" "}
            *
          </span>
        </legend>
        <div className="flex flex-wrap gap-x-5">
          {RATINGS.map((value) => (
            <label key={value} className="flex min-h-11 cursor-pointer items-center gap-2">
              <input
                type="radio"
                name="rating"
                value={value}
                checked={rating === value}
                onChange={() => setRating(value)}
                className="size-[22px] accent-primary"
              />
              {value} out of 5
            </label>
          ))}
        </div>
        {error?.fields.rating ? <FieldError id="rating-error">{error.fields.rating.join(" ")}</FieldError> : null}
      </fieldset>
      <Field id="text" label="Your review" optional error={error?.fields.text} help="What helped you, in a few lines.">
        <Textarea maxLength={1000} rows={4} value={text} onChange={(event) => setText(event.target.value)} />
      </Field>
      {error && !error.fields.rating && !error.fields.text ? (
        <FieldError role="alert">{error.message}</FieldError>
      ) : null}
      <Button type="submit" className="self-start" busy={busy}>
        Send the review
      </Button>
    </form>
  );
}
