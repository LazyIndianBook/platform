"use client";

// "Delete this record" on Edit (Account artboard "Record edit"): DELETE attempts/<id>/ behind a dialog that opens on
// its safe button; then back to My record, whose averages change with it.
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "@/components/ui/toaster";

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
import { api, personal } from "@/lib/api/client";

import { useAction } from "./use-action";

export function DeleteAttempt({ id, paper }: { id: number; paper: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { run, busy, error } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          className="inline-flex min-h-11 cursor-pointer items-center border-0 bg-transparent p-0 text-[15px] font-semibold text-destructive underline underline-offset-[3px]"
        >
          Delete this record
        </button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>Delete these marks?</DialogHeader>
        <DialogBody>
          <DialogDescription>
            Your marks for {paper} go from My record, and your averages change with them. This cannot be undone.
          </DialogDescription>
          {error ? <p className="font-semibold text-destructive">{error.message}</p> : null}
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary" autoFocus>
              Keep them
            </Button>
          </DialogClose>
          <Button
            variant="destructive"
            busy={busy}
            onClick={async () => {
              if (await run(() => personal(api.DELETE("/api/v1/attempts/{id}/", { params: { path: { id } } })))) {
                setOpen(false);
                toast.success(`Your marks for ${paper} are deleted.`);
                router.push("/account/record/");
              }
            }}
          >
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
