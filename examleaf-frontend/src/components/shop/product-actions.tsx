"use client";

// The product page's islands. AddToCart: the bundle choice when the book also comes in a bundle (Product artboard,
// "Choose"), the copies (one for a course), POST cart/items/ (a visitor's guest cart, or the account's), then the
// cart with a toast. StockAlert: "Email me when it is back", to the account's own
// address. ReviewForm: for a buyer whose order of it was delivered (the API says can_review), shown once staff read it.
import { Mail, ShoppingBag } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "@/components/ui/toaster";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SelectableCard } from "@/components/ui/choice";
import { Field, FieldError } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { Price } from "@/components/ui/price";
import { api, ApiError, personal } from "@/lib/api/client";
import { withNext } from "@/lib/auth/next-url";

import { CopiesStepper } from "./copies-stepper";
import { copies, ensureCsrfCookie } from "./shop";

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

export function AddToCart({
  options,
  compact = false,
}: {
  options: BuyOption[];
  /** one copy, no copies box (the catalogue's featured bundle) */
  compact?: boolean;
}) {
  const router = useRouter();
  const [chosen, setChosen] = useState(options.find((option) => option.inStock)?.slug ?? options[0].slug);
  const [count, setCount] = useState("1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const option = options.find((item) => item.slug === chosen) ?? options[0];

  async function add(event: React.FormEvent) {
    event.preventDefault();
    const quantity = option.digital ? 1 : copies(count);
    if (!quantity) {
      setError("Enter a number of copies from 1 to 20.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await ensureCsrfCookie(); // a visitor's first change: the guest cart
      await personal(api.POST("/api/v1/cart/items/", { body: { product: option.slug, quantity } }));
      toast.success(`${option.title} is in your cart.`);
      router.push("/cart/");
      router.refresh(); // the header's cart count
    } catch (caught) {
      setError(failed(caught));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={add} className="flex flex-col gap-4" noValidate>
      {options.length > 1 ? (
        <fieldset className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
          <legend className="mb-2 font-head text-[17px] font-bold text-heading">Choose</legend>
          {options.map((item) => (
            <SelectableCard
              key={item.slug}
              name="product"
              value={item.slug}
              checked={chosen === item.slug}
              disabled={!item.inStock}
              onChange={() => setChosen(item.slug)}
            >
              <span className="flex flex-wrap items-center gap-2 font-semibold">
                {item.label}
                {item.best ? <Badge variant="gold">Best value</Badge> : null}
                {item.inStock ? null : <Badge>Out of stock</Badge>}
              </span>
              <Price as="span" price={item.price} mrp={item.mrp} />
            </SelectableCard>
          ))}
        </fieldset>
      ) : null}
      <div className="flex flex-wrap items-end gap-3">
        {option.digital || compact ? null : (
          <Field id="copies" label="Copies">
            <CopiesStepper value={count} onValue={(value) => setCount(value)} label={option.title} />
          </Field>
        )}
        <Button type="submit" variant="accent" size="lg" busy={busy} disabled={!option.inStock}>
          <ShoppingBag aria-hidden="true" />
          Add to cart
        </Button>
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
      <Alert variant="warning" title="Out of stock for now">
        <p>We email you once, when it is back. Nothing else is sent to that address.</p>
      </Alert>
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
      className="flex max-w-[40rem] flex-col gap-4 rounded-lg border border-border bg-card p-5 shadow-card"
      noValidate
    >
      <div className="flex flex-col gap-1 [&>*]:m-0">
        <h3>Review this {what}</h3>
        <p className="text-muted-foreground">From buyers whose order of it has been delivered.</p>
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
