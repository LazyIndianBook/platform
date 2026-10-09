// A self-contained page (inline styles, no script) for the answer React does not render: the proxy's 503 while Django
// cannot be reached (src/proxy.ts), as the public site's src/lib/status-page.ts. "Try again" is the same address again.
import { copy } from "@/lib/copy";

const STYLE = `body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f8f5ee;color:#1d2230;font:400 17px/1.65 "Segoe UI",system-ui,sans-serif}
main{width:min(34rem,calc(100% - 32px));margin:48px auto;padding:40px 24px;border:1.5px dashed #c9c0ae;background:#fff}
h1{margin:0 0 12px;font:600 28px/1.2 Georgia,serif}
p{margin:0 0 20px;color:#5b6170}
a{display:inline-flex;align-items:center;min-height:44px;padding:0 18px;border-radius:4px;background:#0b2a5b;color:#fff;font-weight:700;text-decoration:none}
a:focus-visible{outline:2px solid #2f8f3a;outline-offset:2px}`;

const escape = (value: string) =>
  value.replace(/[&<>"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[char] ?? char);

export function statusPage({ title, heading, text }: { title: string; heading: string; text: string }): string {
  return `<!doctype html>
<html lang="${copy.lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>${escape(copy.app.titleTemplate.replace("%s", title))}</title>
<style>
${STYLE}
</style>
</head>
<body>
<main>
<h1>${escape(heading)}</h1>
<p>${escape(text)}</p>
<a href="">${escape(copy.common.retry)}</a>
</main>
</body>
</html>`;
}
