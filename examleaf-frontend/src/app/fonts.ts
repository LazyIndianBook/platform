// The site's two families, self-hosted from the same subset files as the Django site (examleaf-web/static/fonts/,
// licences beside them): Poppins 700/800 for headings (Latin + the rupee sign), Hind Siliguri 400/600 for body text,
// with its Bengali files (Assamese and Bangla) declared for the Bengali range only. adjustFontFallback draws a
// metric-matched Arial while they load, so the swap does not move the page (CLS).
import localFont from "next/font/local";

export const poppins = localFont({
  src: [
    { path: "./fonts/poppins-700.woff2", weight: "700", style: "normal" },
    { path: "./fonts/poppins-800.woff2", weight: "800", style: "normal" },
  ],
  variable: "--font-poppins",
  display: "swap",
  adjustFontFallback: "Arial",
});

export const hind = localFont({
  src: [
    { path: "./fonts/hind-siliguri-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/hind-siliguri-600.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-hind",
  display: "swap",
  adjustFontFallback: "Arial",
});

export const hindBengali = localFont({
  src: [
    { path: "./fonts/hind-siliguri-400-bengali.woff2", weight: "400", style: "normal" },
    { path: "./fonts/hind-siliguri-600-bengali.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-hind-bn",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [{ prop: "unicode-range", value: "U+0980-09FE, U+200C-200D, U+25CC" }],
});

export const fontVariables = `${poppins.variable} ${hind.variable} ${hindBengali.variable}`;
