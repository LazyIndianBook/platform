"use client";

// The toast region, Direction A (Components board, 05): an ink bar with a leaf-green tick, the message in 15 px and a
// "Dismiss" text button (a 44 px target); top right under the header on desktop, at the bottom on phones (where
// globals.css keeps a focused field clear of it), a polite live region that is in the page from the start, so each
// message is announced once. A toast stays 6 s, at least the 5 s the review asks for, and its time stops while the
// pointer is on it or the keyboard is in it; it outlives the navigation it was raised for, so "added to your cart" is
// still there on the cart (accessibility review F4, F13). Dismissing one puts focus back where it was before the
// region. It rises in (globals.css, [data-toast]) and leaves at once. Raise one with toast.success("…") from any client
// component. A few lines in place of a toast library: about 15 KB less JavaScript on every page (Lighthouse review L1).
import { Check } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { focusHere } from "@/lib/utils";

type Item = { id: number; message: string };

const SHOWN_MS = 6000;
const NONE: Item[] = [];
let items: Item[] = NONE;
let lastId = 0;
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((listener) => listener());

function remove(id: number) {
  items = items.filter((item) => item.id !== id);
  changed();
}

export const toast = {
  success(message: string) {
    items = [...items, { id: ++lastId, message }];
    changed();
  },
};

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function Toast({ item, onDismiss }: { item: Item; onDismiss: () => void }) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (hovered || focused) return;
    const timer = setTimeout(() => remove(item.id), SHOWN_MS);
    return () => clearTimeout(timer);
  }, [hovered, focused, item.id]);

  return (
    <li
      data-toast=""
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={(event) => setFocused(event.currentTarget.contains(event.relatedTarget as Node | null))}
      className="pointer-events-auto flex items-center gap-3.5 bg-ink py-[3px] pr-1 pl-4 text-white shadow-[0_18px_30px_-16px_rgba(0,0,0,0.5)] [--ring:var(--leaf-light)]"
    >
      <Check aria-hidden="true" className="size-5 shrink-0 text-leaf-light" />
      <p className="m-0 flex-1 py-2.5 text-[15px] leading-snug">{item.message}</p>
      <button
        type="button"
        onClick={onDismiss}
        className="inline-flex min-h-11 shrink-0 cursor-pointer items-center px-3 text-sm font-bold text-white underline underline-offset-[3px] hover:decoration-2"
      >
        Dismiss
      </button>
    </li>
  );
}

function Toaster() {
  const shown = useSyncExternalStore(
    subscribe,
    () => items,
    () => NONE,
  );
  const cameFrom = useRef<HTMLElement | null>(null);
  return (
    <section
      data-toaster=""
      aria-label="Messages"
      aria-live="polite"
      aria-relevant="additions text"
      onFocus={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          cameFrom.current = event.relatedTarget as HTMLElement | null;
      }}
      className="pointer-events-none fixed inset-x-4 bottom-4 z-50 nav:top-20 nav:right-6 nav:bottom-auto nav:left-auto nav:w-[24rem]"
    >
      <ol className="m-0 flex list-none flex-col gap-2 p-0">
        {shown.map((item) => (
          <Toast
            key={item.id}
            item={item}
            onDismiss={() => {
              remove(item.id);
              const back = cameFrom.current;
              focusHere(back?.isConnected ? back : document.getElementById("main"));
            }}
          />
        ))}
      </ol>
    </section>
  );
}

export { Toaster };
