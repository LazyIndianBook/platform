// The Content-Security-Policy of every page of the console, the public site's builder
// (examleaf-frontend/src/lib/security/csp.ts) without its third parties: scripts only with this request's nonce
// ('strict-dynamic' lets them load their own chunks), connections, fonts and images from this origin only, no framing
// at all, no plugins, forms only to this origin and to Google's sign-in redirect. Styles allow 'unsafe-inline' as on
// the public site (style attributes: a progress bar's width); scripts never get it.

export type CspOptions = { nonce: string; dev?: boolean; https?: boolean };

export function buildCsp({ nonce, dev, https }: CspOptions): string {
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'", ...(dev ? ["'unsafe-eval'"] : [])],
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:"],
    "font-src": ["'self'"],
    "connect-src": ["'self'"],
    "media-src": ["'self'"],
    "frame-src": ["'none'"],
    "worker-src": ["'self'"],
    "manifest-src": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'none'"],
    "form-action": ["'self'", "https://accounts.google.com"],
    "frame-ancestors": ["'none'"],
  };
  const policy = Object.entries(directives).map(([name, values]) => `${name} ${values.join(" ")}`);
  if (https) policy.push("upgrade-insecure-requests");
  return policy.join("; ");
}
