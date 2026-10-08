/* Draws the $…$ and $$…$$ maths of a solutions page with KaTeX (loaded before this file, in templates/solutions.html):
   a question at a time as it comes near the screen, so a long paper never holds up a phone (no long task after load),
   and all of it before printing. It waits for KaTeX's stylesheet, applied at the end of the page so that it does not
   delay the first paint; without the stylesheet (blocked or offline) it draws anyway. */
{  // a block: these names stay out of the page's shared global scope
  const options = {
    delimiters: [{left: "$$", right: "$$", display: true}, {left: "$", right: "$", display: false}],
    throwOnError: false,
    strict: false,
  };
  const parts = new Set(document.querySelectorAll("main details.accordion, main .part, main .group, main article.question"));
  const draw = (part) => parts.delete(part) && renderMathInElement(part, options);
  const start = () => {
    window.addEventListener("beforeprint", () => parts.forEach(draw));
    if (!("IntersectionObserver" in window)) return parts.forEach(draw);
    const near = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) {
        near.unobserve(entry.target);
        draw(entry.target);
      }
    }), {rootMargin: "800px 0px"});
    parts.forEach((part) => near.observe(part));
  };
  const css = document.getElementById("katex-css");
  if (css && !css.sheet) {
    css.addEventListener("load", start, {once: true});
    css.addEventListener("error", start, {once: true});
  } else {
    start();
  }
}
