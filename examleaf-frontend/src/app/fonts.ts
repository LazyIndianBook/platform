// The site's families. Direction A: Source Serif 4 for headings, questions and solutions; Public Sans for the
// interface; IBM Plex Mono for codes and marks; Hind Siliguri (local, unchanged) for Assamese and Bangla in every
// stack. next/font/google downloads the files at BUILD time and serves them from this origin, so the CSP's
// "no third-party font host" rule still holds at runtime. If the build machine has no internet, download the
// woff2 files into ./fonts/ and switch these three to localFont (README_IMPLEMENTATION.md, "Fonts offline").
import { IBM_Plex_Mono, Public_Sans, Source_Serif_4 } from "next/font/google";
import localFont from "next/font/local";

export const serif = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  style: ["normal", "italic"],
  variable: "--font-serif",
  display: "swap",
  adjustFontFallback: true,
});

export const ui = Public_Sans({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-ui",
  display: "swap",
  adjustFontFallback: true,
});

export const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
  preload: false, // labels only; never the LCP text
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

export const fontVariables = `${serif.variable} ${ui.variable} ${mono.variable} ${hind.variable} ${hindBengali.variable}`;
