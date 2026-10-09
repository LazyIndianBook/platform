// Single-key shortcuts (/, j, k, x, Enter on a row, ?) can be switched off (WCAG 2.1.4): one setting per browser in
// localStorage (a convenience of this device, nothing personal), read through useSyncExternalStore. ⌘K / Ctrl K, which
// needs a modifier, always works.
import { useSyncExternalStore } from "react";

const KEY = "examleaf-admin:single-key-shortcuts";
const listeners = new Set<() => void>();

export function shortcutsEnabled(): boolean {
  try {
    return window.localStorage.getItem(KEY) !== "off";
  } catch {
    return true;
  }
}

export function setShortcutsEnabled(on: boolean) {
  try {
    window.localStorage.setItem(KEY, on ? "on" : "off");
  } catch {
    // storage off: the setting lasts for this page only
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => event.key === KEY && listener();
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function useShortcutsEnabled(): boolean {
  return useSyncExternalStore(subscribe, shortcutsEnabled, () => true);
}

/** A key pressed while typing (a field, an editable region), with a modifier, or while a dialog is open: no shortcut. */
export function notForShortcuts(event: KeyboardEvent): boolean {
  if (event.metaKey || event.ctrlKey || event.altKey || event.defaultPrevented) return true;
  const target = event.target instanceof HTMLElement ? event.target : null;
  if (target?.closest("input, textarea, select, [contenteditable=''], [contenteditable='true']")) return true;
  return Boolean(document.querySelector("dialog[open]"));
}
