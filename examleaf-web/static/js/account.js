// The account pages (templates/account/): a file, not an inline script, as the CSP allows none.

// The 6-digit code (components.md, .otp): the one "code" box allauth reads becomes six boxes that fill it. Typing
// moves on, Backspace goes back, a pasted or autofilled code fills all six. Without this file the one box stays.
document.querySelectorAll("input[data-otp]").forEach((field) => {
  const group = document.createElement("div");
  group.className = "otp";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", "6-digit code");
  const boxes = Array.from({ length: 6 }, (_, index) => {
    const box = document.createElement("input");
    box.className = "input";
    box.inputMode = "numeric";
    box.setAttribute("aria-label", `Digit ${index + 1} of 6`);
    if (field.hasAttribute("aria-invalid")) box.setAttribute("aria-invalid", "true");
    group.append(box);
    return box;
  });
  boxes[0].autocomplete = "one-time-code";
  boxes[0].setAttribute("aria-describedby", field.getAttribute("aria-describedby") || "");
  const fill = (from, text) => {
    let at = from;
    for (const digit of text.replace(/\D/g, "").slice(0, 6 - from)) boxes[at++].value = digit;
    field.value = boxes.map((box) => box.value).join("");
    boxes[Math.min(at, 5)].focus();
  };
  boxes.forEach((box, index) => {
    box.addEventListener("focus", () => box.select());
    box.addEventListener("input", () => {
      const text = box.value;
      box.value = "";
      fill(index, text);
    });
    box.addEventListener("keydown", (event) => {
      if (event.key !== "Backspace" || box.value || !index) return;
      event.preventDefault();
      boxes[index - 1].value = "";
      fill(index - 1, "");
    });
    box.addEventListener("paste", (event) => {
      event.preventDefault();
      fill(index, event.clipboardData.getData("text"));
    });
  });
  const value = field.value;
  boxes[0].id = field.id; // the label now names the first box
  field.removeAttribute("id");
  field.type = "hidden";
  field.after(group);
  if (value) fill(0, value); // a code sent back with an error
});

// Register: the parent's fields show for a date of birth under 18, and whenever one of them has an error.
const minor = document.querySelector("[data-minor]");
const birth = document.querySelector("input[name=date_of_birth]");
if (minor && birth) {
  const update = () => {
    const eighteen = new Date();
    eighteen.setFullYear(eighteen.getFullYear() - 18);
    minor.hidden = !minor.querySelector("[aria-invalid]") && !(new Date(birth.value) > eighteen);
  };
  birth.addEventListener("input", update);
  update();
}
