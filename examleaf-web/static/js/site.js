// Every page loads this file (base.html; the CSP allows no inline script).

// The service worker (/sw.js): the offline page and the static files, so that the site opens like an app.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
}

// The address form: a PIN code found in the directory fills in the district (if empty) and the state; one it does not
// hold is said in the field's help, so that the customer types them.
document.querySelectorAll("input[data-pin-lookup]").forEach((input) => {
  const help = document.getElementById(`${input.id}_helptext`);
  const usual = help ? help.textContent : "";
  if (help) help.setAttribute("aria-live", "polite");
  input.addEventListener("input", () => {
    const pin = input.value.replace(/\s/g, "");
    if (help) help.textContent = usual;
    if (!/^[1-9]\d{5}$/.test(pin)) return;
    fetch(`/shop/pin/${pin}/`)
      .then((response) => (response.ok ? response.json() : response.status === 404 ? {} : null))
      .then((found) => {
        if (!found) return;  // a server error: nothing to say
        if (!found.pin) {
          if (help) help.textContent = `${usual} ${pin} is not in our list: type the district and state.`;
          return;
        }
        const { district, state } = input.form.elements;
        if (district && !district.value && found.districts.length) district.value = found.districts[0];
        if (state && found.states.length === 1) state.value = found.states[0];
      })
      .catch(() => {});  // offline: the customer types them
  });
});

// Copies (product page, cart): the − and + buttons beside the number box, hidden until this script works them.
document.querySelectorAll("[data-step]").forEach((button) => {
  const input = button.parentElement.querySelector("input");
  button.hidden = false;
  button.addEventListener("click", () => (button.dataset.step === "up" ? input.stepUp() : input.stepDown()));
});

// Confirmations (a cart line's Remove, Cancel the order): a submit button with data-dialog opens that <dialog>, whose
// own button submits the form. Without JavaScript, or without <dialog>, the button simply submits.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-dialog]");
  const dialog = button && document.getElementById(button.dataset.dialog);
  if (!dialog || typeof dialog.showModal !== "function") return;
  event.preventDefault();
  dialog.showModal();
});

{  // a block: these names stay out of the global scope that every script of the page shares
  // Toasts (docs/design/motion.md, f): read once into the polite live region #announce, which screen readers announce
  // (text present at load is not), and dismissed with an exit animation: the <details> closes when the animation ends,
  // or at once without one (reduced motion), so repeated clicks change nothing. Escape dismisses them all. Without this
  // file the <details> simply closes.
  const toasts = [...document.querySelectorAll(".toast-item")];
  if (toasts.length) {
    setTimeout(() => (document.getElementById("announce").textContent = toasts.map((t) => t.textContent.trim()).join(" ")), 400);
  }
  const dismiss = (toast) => {
    toast.dataset.leaving = "";
    Promise.allSettled(toast.getAnimations().map((animation) => animation.finished)).then(() => (toast.open = false));
  };
  document.addEventListener("click", (event) => {
    const summary = event.target.closest(".toast-item > summary");
    if (!summary) return;
    event.preventDefault();
    dismiss(summary.parentElement);
  });

  // The menu and the subject tabs are a checkbox and radios (no JavaScript needed): Enter works them too, as Space
  // does. Escape closes the open menu (focus back on Menu), or else dismisses the toasts.
  const menu = document.getElementById("nav-check");
  if (menu) {
    const expanded = () => menu.setAttribute("aria-expanded", String(menu.checked));
    menu.addEventListener("change", expanded);
    expanded();
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.matches(".nav-check, .tabs input")) {
      event.preventDefault();
      event.target.click();
    } else if (event.key === "Escape" && menu && menu.checked) {
      menu.click();
      menu.focus();
    } else if (event.key === "Escape") {
      document.querySelectorAll(".toast-item[open]:not([data-leaving])").forEach(dismiss);
    }
  });

  // iOS Safari applies :active (the press feedback of buttons and tiles) only when the page listens to touches.
  document.addEventListener("touchstart", () => {}, {passive: true});

  // A form sent shows its button busy (components.md, .btn [aria-busy]) and is not sent twice. The button is disabled
  // only after the browser has read its name and value; it comes back with the page (Back), or after a while when
  // the answer was a file and the page stayed.
  const busy = new Map();  // form sent -> its button (which may sit outside it: form="…")
  const ready = (form) => {
    const button = busy.get(form);
    busy.delete(form);
    if (button) {
      button.removeAttribute("aria-busy");
      button.disabled = false;
    }
  };
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (event.defaultPrevented || form.method === "dialog" || form.target === "_blank") return;
    if (busy.has(form)) {
      event.preventDefault();
      return;
    }
    const button = event.submitter || form.querySelector("[type=submit]");
    busy.set(form, button);
    if (button) {
      button.setAttribute("aria-busy", "true");
      setTimeout(() => (button.disabled = true));
    }
    setTimeout(() => ready(form), 15000);
  });
  window.addEventListener("pageshow", () => [...busy.keys()].forEach(ready));

  // Cross-document view transitions (motion.md, d) are for moving between pages: none after a form is sent.
  let sending = false;
  document.addEventListener("submit", (event) => (sending = event.target.method !== "dialog"));
  window.addEventListener("pageshow", () => (sending = false));
  window.addEventListener("pageswap", (event) => sending && event.viewTransition && event.viewTransition.skipTransition());

  // Printing a solutions page prints its instructions too: closed accordions open for the print, then close again.
  window.addEventListener("beforeprint", () => document.querySelectorAll("details.accordion:not([open])").forEach((d) => {
    d.open = true;
    d.dataset.printed = "";
  }));
  window.addEventListener("afterprint", () => document.querySelectorAll("details[data-printed]").forEach((d) => {
    d.open = false;
    delete d.dataset.printed;
  }));
}
