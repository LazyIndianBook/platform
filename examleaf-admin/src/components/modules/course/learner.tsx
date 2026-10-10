"use client";

// A learner's phone signed out (POST course/learners/{user}/devices/{device}/sign-out/, staff.end_user_sessions): no
// more reminders reach it until the app registers it again. Asked once: it is easy to undo by signing in again.
import { ConfirmDialog } from "@/components/data/confirm-typed";
import { signOutDevice } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const words = copy.course.learner;

export function SignOutDevice({ user, device, name }: { user: number; device: number; name: string }) {
  return (
    <ConfirmDialog
      triggerLabel={
        <>
          {words.signOut}
          <span className="sr-only">: {name}</span>
        </>
      }
      title={words.signOutTitle}
      text={words.signOutText}
      confirmLabel={words.signOut}
      success={words.signedOut}
      onConfirm={() => signOutDevice(user, device)}
    />
  );
}
