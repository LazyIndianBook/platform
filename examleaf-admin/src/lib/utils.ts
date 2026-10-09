export { cn } from "cn";

/** Focus an element that is not a control (a heading, a list, main), as a page load would start a screen reader. */
export function focusHere(element: HTMLElement | null | undefined) {
  if (!element) return;
  if (!element.hasAttribute("tabindex")) element.setAttribute("tabindex", "-1");
  element.focus({ preventScroll: true });
}
