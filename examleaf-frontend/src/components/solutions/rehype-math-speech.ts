// Before rehype-katex: each formula gets words a screen reader can say (KaTeX's own render-a11y-string: "X, start
// subscript, C, end subscript, equals, start fraction, 1, divided by, omega, C, end fraction") on a role="img"
// wrapper, and the drawing KaTeX then makes inside it is aria-hidden. The page carries KaTeX's HTML only, no MathML copy
// (markdown.tsx), so without this a screen reader would read the drawing's glyphs one by one; contrast checkers skip
// the drawing too. A formula the helper cannot say keeps its TeX as its name.
import type { Element, ElementContent, Root } from "hast";
import renderA11yString from "katex/contrib/render-a11y-string";

const MATH = ["language-math", "math-inline", "math-display"];

const text = (node: ElementContent): string =>
  node.type === "text" ? node.value : "children" in node ? node.children.map(text).join("") : "";

function speak(tex: string): string {
  try {
    return renderA11yString(tex);
  } catch {
    return tex;
  }
}

function wrap(parent: Root | Element) {
  parent.children.forEach((child, index) => {
    if (child.type !== "element") return;
    // a display formula is <pre><code class="language-math">: the pre is what KaTeX replaces
    const code = child.tagName === "pre" ? child.children.find((node) => node.type === "element") : child;
    const classes = code?.type === "element" ? code.properties.className : undefined;
    if (!Array.isArray(classes) || !MATH.some((name) => classes.includes(name))) return wrap(child);
    const tag = child.tagName === "pre" || classes.includes("math-display") ? "div" : "span";
    parent.children[index] = {
      type: "element",
      tagName: tag,
      properties: { role: "img", ariaLabel: speak(text(child).trim()) },
      children: [{ type: "element", tagName: tag, properties: { ariaHidden: "true" }, children: [child] }],
    };
  });
}

export default function rehypeMathSpeech() {
  return (tree: Root) => wrap(tree);
}
