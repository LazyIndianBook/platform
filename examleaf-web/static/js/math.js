/* Draws the $…$ and $$…$$ maths of a solutions page with KaTeX (loaded before this file, in templates/solutions.html). */
renderMathInElement(document.querySelector("main"), {
  delimiters: [{left: "$$", right: "$$", display: true}, {left: "$", right: "$", display: false}],
  throwOnError: false,
  strict: false,
});
