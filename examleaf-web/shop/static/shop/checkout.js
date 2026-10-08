// Razorpay Checkout on the "Pay" button. The options come from the page (json_script: the CSP allows no inline
// script); Checkout's answer goes back to the server in the hidden form, which checks its signature.
(function () {
  var button = document.getElementById("pay-button");
  var error = document.getElementById("pay-error");
  var form = document.getElementById("razorpay-form");
  var options = JSON.parse(document.getElementById("razorpay-options").textContent);
  button.removeAttribute("aria-busy"); // the page renders it busy while Razorpay's script loads
  if (typeof Razorpay === "undefined") {
    error.textContent = "The payment window could not be loaded. Check your internet connection and reload this page.";
    error.hidden = false;
    return;
  }
  options.handler = function (response) {
    form.razorpay_payment_id.value = response.razorpay_payment_id;
    form.razorpay_order_id.value = response.razorpay_order_id;
    form.razorpay_signature.value = response.razorpay_signature;
    button.disabled = true; // busy again while the server checks the payment
    button.setAttribute("aria-busy", "true");
    form.requestSubmit ? form.requestSubmit() : form.submit(); // requestSubmit: a "submit" event, so no page transition
  };
  var checkout = new Razorpay(options);
  checkout.on("payment.failed", function (response) {
    error.textContent = "The payment did not go through (" + response.error.description + "). You can try again.";
    error.hidden = false;
  });
  button.addEventListener("click", function () { error.hidden = true; checkout.open(); });
  button.disabled = false;
})();
