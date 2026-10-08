// A CMS page's sections for "On this page": ids on the h2s, their titles in plain words, no two ids alike.
import { describe, expect, it } from "vitest";

import { sectioned } from "./sections";

describe("sectioned", () => {
  it("gives each h2 an id and lists the sections in plain words", () => {
    const { html, sections } = sectioned(
      "<p>Intro</p>\n<h2>Who we are</h2>\n<p>…</p>\n<h2>Orders, deliveries &amp; <em>refunds</em></h2>\n<h2>Who we are</h2>",
    );
    expect(sections).toEqual([
      { id: "who-we-are", title: "Who we are" },
      { id: "orders-deliveries-refunds", title: "Orders, deliveries & refunds" },
      { id: "who-we-are-3", title: "Who we are" },
    ]);
    expect(html).toContain('<h2 id="who-we-are">Who we are</h2>');
    expect(html).toContain('<h2 id="orders-deliveries-refunds">Orders, deliveries &amp; <em>refunds</em></h2>');
    expect(html).toContain('<h2 id="who-we-are-3">');
  });

  it("leaves a page without sections as it is", () => {
    expect(sectioned("<ul><li>Where we deliver</li></ul>")).toEqual({
      html: "<ul><li>Where we deliver</li></ul>",
      sections: [],
    });
  });
});
