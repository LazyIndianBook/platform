"use client";

// What a person types in a form is kept in sessionStorage as they type (the public site's marks-form pattern), so a
// session that ends meanwhile (idle sign-out, a 401, a reload) costs nothing: after signing in again the form on that
// page fills itself back in. Cleared when the save worked. Passwords and fields marked data-no-draft are never kept.
// Uncontrolled fields (name + defaultValue) only: the draft is put back into the DOM after hydration.
import { useCallback, useEffect, useRef } from "react";

const PREFIX = "examleaf-admin:draft:";

type Values = Record<string, string | boolean>;

function fields(form: HTMLFormElement) {
  return [...form.elements].filter(
    (element): element is HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement =>
      (element instanceof HTMLInputElement ||
        element instanceof HTMLTextAreaElement ||
        element instanceof HTMLSelectElement) &&
      Boolean(element.name) &&
      !element.hasAttribute("data-no-draft") &&
      !(element instanceof HTMLInputElement && ["password", "hidden", "file", "submit"].includes(element.type)),
  );
}

export function readDraft(key: string): Values | null {
  try {
    const raw = window.sessionStorage.getItem(PREFIX + key);
    return raw ? (JSON.parse(raw) as Values) : null;
  } catch {
    return null;
  }
}

/** `onRestore`: told when a draft was put back into the form (it is unsaved work). */
export function useDraftForm(key: string, onRestore?: () => void) {
  const ref = useRef<HTMLFormElement>(null);
  const restored = useRef(onRestore);
  useEffect(() => {
    restored.current = onRestore;
  });

  useEffect(() => {
    const form = ref.current;
    const draft = readDraft(key);
    if (!form || !draft) return;
    for (const field of fields(form)) {
      const value = draft[field.name];
      if (value === undefined) continue;
      if (field instanceof HTMLInputElement && (field.type === "checkbox" || field.type === "radio")) {
        if (field.type === "checkbox") field.checked = value === true;
        else field.checked = field.value === value;
      } else if (typeof value === "string") {
        field.value = value;
      }
    }
    restored.current?.();
  }, [key]);

  const save = useCallback(() => {
    const form = ref.current;
    if (!form) return;
    const values: Values = {};
    for (const field of fields(form)) {
      if (field instanceof HTMLInputElement && field.type === "checkbox") values[field.name] = field.checked;
      else if (field instanceof HTMLInputElement && field.type === "radio") {
        if (field.checked) values[field.name] = field.value;
      } else values[field.name] = field.value;
    }
    try {
      window.sessionStorage.setItem(PREFIX + key, JSON.stringify(values));
    } catch {
      // storage off or full: nothing kept
    }
  }, [key]);

  const clear = useCallback(() => {
    try {
      window.sessionStorage.removeItem(PREFIX + key);
    } catch {
      // nothing to clear
    }
  }, [key]);

  return { ref, save, clear };
}
