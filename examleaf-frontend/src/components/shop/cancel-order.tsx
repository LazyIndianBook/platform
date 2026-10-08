"use client";

// "Cancel the order" (Django's order page and its dialog): asks first, opened on "Keep the order". The owner's order
// is cancelled through POST orders/<n>/cancel/, an emailed link's through POST orders/t/<token>/cancel/; the answer
// is told in a toast and the page reloads its order from the server.
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTrigger,
} from "@/components/ui/dialog";
import { FieldError } from "@/components/ui/field";
import { api, ApiError, personal } from "@/lib/api/client";

import { cancelledMessage } from "./shop";

export function CancelOrder({
  number,
  paid,
  digital,
  token,
}: {
  number: string;
  paid: boolean;
  digital: boolean;
  /** the emailed link's secret: cancelled by the link (no account), otherwise as the signed-in owner */
  token?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      const order = await personal(
        token
          ? api.POST("/api/v1/orders/t/{token}/cancel/", { params: { path: { token } } })
          : api.POST("/api/v1/orders/{number}/cancel/", { params: { path: { number } } }),
      );
      toast.success(cancelledMessage(number, order.refunds[0]?.amount));
      setOpen(false);
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "That did not work. Check your connection, then try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 [&>*]:m-0">
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button type="button" variant="secondary" className="self-start">
            Cancel the order
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>Cancel this order?</DialogHeader>
          <DialogBody>
            <DialogDescription>
              Order {number} is cancelled{digital ? "" : " and its books are not sent"}.{" "}
              {paid
                ? "The full amount is refunded to the account, card or UPI ID you paid from."
                : "Nothing has been charged."}
            </DialogDescription>
            {error ? <FieldError role="alert">{error}</FieldError> : null}
          </DialogBody>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="secondary" autoFocus>
                Keep the order
              </Button>
            </DialogClose>
            <Button type="button" variant="destructive" busy={busy} onClick={cancel}>
              Cancel the order
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <p className="text-[15px] text-muted-foreground">
        {digital ? "You can cancel until you pay." : "You can cancel until it is packed."}{" "}
        {paid
          ? "The full amount is refunded to the account, card or UPI ID you paid from, within 5–7 working days."
          : "Nothing has been charged."}
      </p>
    </div>
  );
}
