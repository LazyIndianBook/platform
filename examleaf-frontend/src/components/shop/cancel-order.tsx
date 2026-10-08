"use client";

// "Cancel order" (Order artboard; States "Cancel dialog", the browser's own <dialog>): asks first, opened on "Keep the
// order", and gives the focus back to the button that opened it. The owner's order is cancelled through POST
// orders/<n>/cancel/, an emailed link's through POST orders/t/<token>/cancel/ (the API takes no reason); the answer is
// told in a toast and the page reloads its order from the server.
import { useRouter } from "next/navigation";
import { useState } from "react";

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
import { toast } from "@/components/ui/toaster";
import { api, ApiError, personal } from "@/lib/api/client";
import { inr } from "@/lib/format";

import { cancelledMessage, SHOP_DIALOG } from "./shop";

export function CancelOrder({
  number,
  paid,
  digital,
  token,
  total,
}: {
  number: string;
  paid: boolean;
  digital: boolean;
  /** the emailed link's secret: cancelled by the link (no account), otherwise as the signed-in owner */
  token?: string;
  /** what was paid, for the refund's words */
  total?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function cancel() {
    if (busy) return;
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

  const refund = paid
    ? `You paid ${total ? inr(total) : "online"}: it goes back in full to the account, card or UPI ID you paid from, within 5–7 working days.`
    : "Nothing has been charged.";
  return (
    <div className="flex flex-col gap-3 [&>*]:m-0">
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button type="button" variant="destructive" block>
            Cancel order
          </Button>
        </DialogTrigger>
        <DialogContent className={SHOP_DIALOG}>
          <DialogHeader>Cancel order {number}?</DialogHeader>
          <DialogBody>
            <DialogDescription className="text-[15px] leading-relaxed text-ink/85">
              {digital ? "The course closes again. " : "It hasn't been packed, so the books are not sent. "}
              {refund}
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
              Cancel order
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <p className="text-sm leading-normal text-muted-foreground">
        {digital ? "You can cancel until you pay." : "You can cancel until the books are packed."}{" "}
        {paid
          ? "A paid order is refunded in full to the account, card or UPI ID you paid from, within 5–7 working days."
          : "Nothing has been charged."}
      </p>
    </div>
  );
}
