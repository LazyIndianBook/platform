// The checkout's address step waits like the cart (cart/loading.tsx). Only this step: the pay and done pages sit
// outside the group, so that an anonymous visitor gets a real 307 to log in, not a 200 that redirects in script
// once streamed (docs/design/audit-nextjs-parity.md).
export { default } from "../../cart/loading";
