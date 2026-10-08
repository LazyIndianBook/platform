// Clip videos straight to the bucket (learn/uploads.py, H1), on the clip and revision pages of the admin. A video chosen
// in a clip's file field is sent to the PUT link that its hidden field's data-upload-url gives, with its progress shown
// beside it; the signed name the link came with goes into that hidden field and the file field is emptied, so the
// form carries no video. Without data-upload-url (no bucket) nothing happens: the file goes with the form.
(function () {
  "use strict";

  function say(input, text) {
    var note = input.nextElementSibling;
    if (!note || !note.classList.contains("clip-upload")) {
      note = document.createElement("span");
      note.className = "clip-upload help";
      note.setAttribute("role", "status");
      input.insertAdjacentElement("afterend", note);
    }
    note.textContent = " " + text;
  }

  function hold(form, busy) {
    form.querySelectorAll("[type=submit]").forEach(function (button) { button.disabled = busy; });
  }

  function failed(input, form, text) {
    input.value = "";
    hold(form, false);
    say(input, text + " Choose the video again.");
  }

  function send(input, hidden, file, link) {
    var form = input.form;
    var put = new XMLHttpRequest();
    put.open("PUT", link.url);
    Object.keys(link.headers).forEach(function (name) { put.setRequestHeader(name, link.headers[name]); });
    put.upload.addEventListener("progress", function (event) {
      if (event.lengthComputable) say(input, "Uploading: " + Math.floor((event.loaded / event.total) * 100) + " %");
    });
    put.addEventListener("load", function () {
      if (put.status < 200 || put.status >= 300) return failed(input, form, "The bucket refused the video (" + put.status + ").");
      hidden.value = link.key;
      input.value = "";
      hold(form, false);
      say(input, "Uploaded: " + file.name + ". Save to process it.");
    });
    put.addEventListener("error", function () { failed(input, form, "The upload was cut off."); });
    put.send(file);
  }

  document.addEventListener("change", function (event) {
    var input = event.target;
    if (input.type !== "file" || !input.form || !/(^|-)source$/.test(input.name) || !input.files.length) return;
    var hidden = input.form.elements[input.name + "_key"];
    if (!hidden || !hidden.dataset.uploadUrl) return;
    var file = input.files[0];
    var form = input.form;
    var ask = new FormData();
    ask.append("name", file.name);
    ask.append("size", String(file.size));
    hold(form, true);
    hidden.value = "";
    say(input, "Preparing the upload…");
    fetch(hidden.dataset.uploadUrl, {
      method: "POST",
      body: ask,
      credentials: "same-origin",
      headers: { "X-CSRFToken": form.elements.csrfmiddlewaretoken.value },
    })
      .then(function (answer) {
        return answer.json().then(function (data) { return { ok: answer.ok, data: data }; });
      })
      .then(function (answer) {
        if (!answer.ok) return failed(input, form, answer.data.error || "The upload could not start.");
        send(input, hidden, file, answer.data);
      })
      .catch(function () { failed(input, form, "The upload could not start."); });
  });
})();
