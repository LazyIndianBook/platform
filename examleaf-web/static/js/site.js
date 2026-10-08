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
