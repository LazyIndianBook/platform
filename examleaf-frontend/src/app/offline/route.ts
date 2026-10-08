// /offline/: what the service worker shows when a page cannot be fetched. Self-contained (inline styles, no script,
// no account menu, no web fonts: the system's serif, sans and mono stand in), so it works from the cache with no
// connection at all. The service worker shows it at the address asked for, so Try again (an empty link) asks for
// that page again. Direction A (ExamLeaf A - Public.dc.html, "Unavailable and offline"; Phone 404 and offline): the
// answer sheet's margin with a dash, the wordmark, the words and one way on.
const STYLE = `*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:#f8f5ee;color:#1d2230;font:400 17px/1.65 "Public Sans","Segoe UI",system-ui,sans-serif;-webkit-text-size-adjust:100%}
main{display:grid;grid-template-columns:120px minmax(0,1fr);max-width:1000px;min-height:100vh}
.margin{padding:68px 0 0 24px;font:600 15px/1 ui-monospace,Menlo,Consolas,monospace;color:#b3342a}
.body{border-left:3px double #b3342a;padding:56px 48px 64px;display:flex;flex-direction:column;gap:18px}
.brand{font:700 23px/1 "Source Serif 4",Georgia,serif;color:#1d2230}.brand span{color:#1a6e30}
h1{margin:0;font:600 48px/1.05 "Source Serif 4",Georgia,serif;letter-spacing:-0.02em}
p{margin:0;max-width:36em;font-size:18px;color:#3e4454}
a{align-self:flex-start;display:inline-flex;align-items:center;min-height:52px;padding:0 24px;border:1.5px solid #1d2230;border-radius:4px;color:#1d2230;font-weight:700;text-decoration:none}
a:active{transform:translateY(1px)}
a:focus-visible{outline:2px solid #2f8f3a;outline-offset:2px}
@media (max-width:899.98px){main{display:block;min-height:100vh;border-left:3px double #b3342a}.margin{display:none}
.body{border:0;padding:28px 16px;gap:12px}.brand{font-size:21px}h1{font-size:32px}p{font-size:15px;line-height:1.6}
a{align-self:stretch;justify-content:center;min-height:48px}}`;

const HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<meta name="theme-color" content="#0b2a5b">
<title>Offline · ExamLeaf</title>
<style>
${STYLE}
</style>
</head>
<body>
<main>
<div class="margin" aria-hidden="true">—</div>
<div class="body">
<p class="brand">Exam<span>Leaf</span></p>
<h1>You are offline</h1>
<p>This page needs the internet. Your book works without it: sit the paper now, and open its solutions when you're back online.</p>
<a href="">Try again</a>
</div>
</main>
</body>
</html>`;

export function GET() {
  return new Response(HTML, {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=3600" },
  });
}
