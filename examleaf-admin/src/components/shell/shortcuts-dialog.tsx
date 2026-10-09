"use client";

// The list of keyboard shortcuts ("?" or the person's menu), as Linear, Shopify and Stripe show theirs.
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { copy } from "@/lib/copy";

export function ShortcutsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>{copy.shell.shortcutsTitle}</DialogHeader>
        <DialogBody>
          <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-5 gap-y-2.5">
            {copy.shell.shortcutsList.map(([keys, what]) => (
              <div key={keys} className="contents">
                <dt>
                  <kbd>{keys}</kbd>
                </dt>
                <dd className="m-0">{what}</dd>
              </div>
            ))}
          </dl>
          <DialogDescription className="text-sm text-muted-foreground">{copy.shell.shortcutsNote}</DialogDescription>
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary">{copy.common.close}</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
