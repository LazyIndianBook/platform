// /offline/: what the service worker shows when a page cannot be fetched. Self-contained (inline styles, no script,
// no account menu), so it works from the cache with no connection at all. The service worker shows it at the address
// asked for, so Try again (an empty link) asks for that page again.
import { statusPage } from "@/lib/status-page";

const HTML = statusPage({
  title: "Offline",
  heading: "You are offline",
  text: "ExamLeaf needs an internet connection for this page. Check your mobile data or Wi-Fi, then try again.",
});

export function GET() {
  return new Response(HTML, {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=3600" },
  });
}
