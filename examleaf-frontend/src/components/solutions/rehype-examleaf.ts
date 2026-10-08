// The solution lines that get their own look, as the Django site's markdown filter gives them
// (content/templatetags/markdown.py): every table scrolls sideways in a .table-scroll box, a marking table (last
// column "Marks") is .steps, "**Final answer:**" is .final, "*Also accepted:*" is .also, and a quote that starts with
// "*Diagram expected:*" is .diagram.
import type { Element, ElementContent, Root, RootContent } from "hast";

const text = (node: ElementContent | RootContent): string =>
  node.type === "text" ? node.value : "children" in node ? node.children.map(text).join("") : "";

const firstElement = (node: Element): Element | undefined =>
  node.children.find((child): child is Element => child.type === "element");

const startsWith = (node: Element | undefined, tag: string, label: string) =>
  node?.type === "element" && node.tagName === tag && text(node).trim() === label;

function addClass(node: Element, name: string) {
  const current = node.properties.className;
  node.properties.className = [...(Array.isArray(current) ? current : current ? [String(current)] : []), name];
}

function isStepsTable(table: Element): boolean {
  const head = firstElement(table);
  if (!head || head.tagName !== "thead") return false;
  const cells = firstElement(head)?.children.filter((child): child is Element => child.type === "element") ?? [];
  const last = cells.at(-1);
  return Boolean(last && text(last).replace(/\*/g, "").trim().toLowerCase() === "marks");
}

function walk(parent: Root | Element) {
  parent.children.forEach((child, index) => {
    if (child.type !== "element") return;
    walk(child);
    if (child.tagName === "table") {
      if (isStepsTable(child)) addClass(child, "steps");
      parent.children[index] = {
        type: "element",
        tagName: "div",
        properties: { className: ["table-scroll"] },
        children: [child],
      };
    } else if (child.tagName === "p") {
      const first = firstElement(child);
      if (child.children[0] === first && startsWith(first, "strong", "Final answer:")) addClass(child, "final");
      if (child.children[0] === first && startsWith(first, "em", "Also accepted:")) addClass(child, "also");
    } else if (child.tagName === "blockquote") {
      const paragraph = firstElement(child);
      const first = paragraph && firstElement(paragraph);
      if (paragraph && paragraph.children[0] === first && startsWith(first, "em", "Diagram expected:")) {
        addClass(child, "diagram");
      }
    }
  });
}

export default function rehypeExamleaf() {
  return (tree: Root) => walk(tree);
}
