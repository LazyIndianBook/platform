// The Content-Security-Policy of every page (docs/examleaf-phase8-nextjs-plan.md, "Security"): scripts only with this
// request's nonce ('strict-dynamic' lets them load their own chunks), Razorpay only on the checkout routes, Turnstile
// only when its site key is set, connections to this origin and the media host, no framing, no foreign forms except
// Google's sign-in redirect. Styles allow 'unsafe-inline': KaTeX sets heights and offsets in style attributes, as on
// the Django site (settings.py, I6); scripts never get it.

/** Routes that load Razorpay's checkout.js (package 8B's pay page lives under /checkout/). */
export const RAZORPAY_ROUTES = /^\/checkout\//;

const RAZORPAY = {
  script: ["https://checkout.razorpay.com"],
  frame: ["https://api.razorpay.com", "https://checkout.razorpay.com"],
  connect: ["https://api.razorpay.com", "https://lumberjack.razorpay.com"],
  img: ["https://cdn.razorpay.com"],
};
const TURNSTILE = "https://challenges.cloudflare.com";

export type CspOptions = {
  nonce: string;
  pathname: string;
  dev?: boolean;
  https?: boolean;
  mediaHost?: string;
  turnstile?: boolean;
};

const origin = (host: string) => (/^https?:\/\//.test(host) ? host.replace(/\/$/, "") : `https://${host}`);

export function buildCsp({ nonce, pathname, dev, https, mediaHost, turnstile }: CspOptions): string {
  const razorpay = RAZORPAY_ROUTES.test(pathname);
  const media = mediaHost ? [origin(mediaHost)] : [];
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": [
      "'self'",
      `'nonce-${nonce}'`,
      "'strict-dynamic'",
      ...(dev ? ["'unsafe-eval'"] : []),
      ...(razorpay ? RAZORPAY.script : []),
      ...(turnstile ? [TURNSTILE] : []),
    ],
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:", ...media, ...(razorpay ? RAZORPAY.img : [])],
    "font-src": ["'self'"],
    "connect-src": ["'self'", ...media, ...(razorpay ? RAZORPAY.connect : [])],
    "media-src": ["'self'", "blob:", ...media],
    "frame-src": ["'self'", ...(razorpay ? RAZORPAY.frame : []), ...(turnstile ? [TURNSTILE] : [])],
    "worker-src": ["'self'"],
    "manifest-src": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'", "https://accounts.google.com"],
    "frame-ancestors": ["'none'"],
  };
  const policy = Object.entries(directives).map(([name, values]) => `${name} ${values.join(" ")}`);
  if (https) policy.push("upgrade-insecure-requests");
  return policy.join("; ");
}
