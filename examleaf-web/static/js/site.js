// Every page loads this file (base.html; the CSP allows no inline script).

// The service worker (/sw.js): the offline page and the static files, so that the site opens like an app.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
}

// The address form: a PIN code found in the directory fills in the district (if empty) and the state.
document.querySelectorAll("input[data-pin-lookup]").forEach((input) => {
  input.addEventListener("input", () => {
    const pin = input.value.replace(/\s/g, "");
    if (!/^[1-9]\d{5}$/.test(pin)) return;
    fetch(`/shop/pin/${pin}/`)
      .then((response) => (response.ok ? response.json() : null))
      .then((found) => {
        if (!found) return;
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
