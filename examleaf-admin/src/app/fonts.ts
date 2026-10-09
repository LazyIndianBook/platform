// The site's families, self-hosted from ./fonts/ (the OFL licences sit beside the files), so a build needs nothing
// from the network and serves the same bytes every time (font-src 'self' holds). Direction A: Source Serif 4 for
// headings, questions and solutions; Public Sans for the interface; IBM Plex Mono for codes and marks; Hind Siliguri
// (unchanged) for Assamese and Bangla in every stack, its Bengali files declared for the Bengali range only.
// The files are subsets (Latin, the rupee sign, arrows, ticks, superscripts) made with fontTools from the official
// variable fonts: the serif and the sans keep their weight axis (400 to 700); the serif's optical size is pinned at
// its text value (20) for reading and headings up to h3, and a second cut at the display value (60, as the design's
// Google Fonts link asks for) sets h1, h2 and the display sizes (--font-display in globals.css). adjustFontFallback
// draws a metric-matched system font while a file loads, so the swap does not move the page (CLS).
import localFont from "next/font/local";

export const serif = localFont({
  src: [
    { path: "./fonts/source-serif-4-roman.woff2", weight: "400 700", style: "normal" },
    { path: "./fonts/source-serif-4-italic.woff2", weight: "400 700", style: "italic" },
  ],
  variable: "--font-serif",
  display: "swap",
  preload: false, // reading text paints in the fallback and swaps; the display cut and the sans are preloaded
  adjustFontFallback: "Times New Roman",
});

export const serifDisplay = localFont({
  src: [
    { path: "./fonts/source-serif-4-display.woff2", weight: "600", style: "normal" },
    { path: "./fonts/source-serif-4-display-italic.woff2", weight: "600", style: "italic" },
  ],
  variable: "--font-serif-display",
  display: "swap",
  adjustFontFallback: "Times New Roman",
});

export const ui = localFont({
  src: [{ path: "./fonts/public-sans.woff2", weight: "400 700", style: "normal" }],
  variable: "--font-ui",
  display: "swap",
  adjustFontFallback: "Arial",
});

export const mono = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-500.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-mono-600.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
  preload: false, // labels only; never the LCP text
  adjustFontFallback: false,
});

export const hind = localFont({
  src: [
    { path: "./fonts/hind-siliguri-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/hind-siliguri-600.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-hind",
  display: "swap",
  preload: false,
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

/** Kept so any import of the old heading font still compiles; it now resolves to the serif. */
export const poppins = serif;

export const fontVariables = `${serif.variable} ${serifDisplay.variable} ${ui.variable} ${mono.variable} ${hind.variable} ${hindBengali.variable}`;
