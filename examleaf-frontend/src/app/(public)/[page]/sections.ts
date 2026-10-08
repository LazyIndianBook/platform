// "On this page" for a CMS page: the server's HTML (its Markdown rendered by Django, raw HTML off) with an id on each
// <h2>, and those sections' titles in plain words.
const ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
};

export function sectioned(html: string): { html: string; sections: { id: string; title: string }[] } {
  const sections: { id: string; title: string }[] = [];
  const out = html.replace(/<h2>([\s\S]*?)<\/h2>/g, (_, inner: string) => {
    const title = inner
      .replace(/<[^>]+>/g, "")
      .replace(/&(amp|lt|gt|quot|#x27|#39);/g, (entity) => ENTITIES[entity])
      .trim();
    const base =
      title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "") || "section";
    const id = sections.some((section) => section.id === base) ? `${base}-${sections.length + 1}` : base;
    sections.push({ id, title });
    return `<h2 id="${id}">${inner}</h2>`;
  });
  return { html: out, sections };
}
