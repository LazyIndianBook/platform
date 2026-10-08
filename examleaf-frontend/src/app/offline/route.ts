// /offline/: what the service worker shows when a page cannot be fetched. Self-contained (inline styles, no script,
// no account menu), so it works from the cache with no connection at all. The service worker shows it at the address
// asked for, so Try again (an empty link) asks for that page again.
const HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<meta name="theme-color" content="#0b2a5b">
<title>Offline · ExamLeaf</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#fbfaf7;color:#1b2330;font:400 17px/1.7 "Segoe UI",system-ui,sans-serif}
main{width:min(34rem,calc(100% - 32px));margin:48px auto;padding:48px 24px;border:2px dashed #d9dde3;border-radius:12px;background:#fff;text-align:center}
h1{margin:0 0 12px;color:#0b2a5b;font:800 28px/1.2 system-ui,sans-serif}
p{margin:0 0 20px;color:#5d6675}
a{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;border-radius:10px;background:#0b2a5b;color:#fff;font-weight:700;text-decoration:none}
a:focus-visible{outline:2px solid #2f8f3a;outline-offset:2px}
</style>
</head>
<body>
<main>
<h1>You are offline</h1>
<p>ExamLeaf needs an internet connection for this page. Check your mobile data or Wi-Fi, then try again.</p>
<a href="">Try again</a>
</main>
</body>
</html>`;

export function GET() {
  return new Response(HTML, {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=3600" },
  });
}
