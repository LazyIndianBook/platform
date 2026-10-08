// hls.js's light build (no subtitles, alternate audio, DRM or CMCD: the clips use none) ships without a type file.
declare module "hls.js/light" {
  export { default } from "hls.js";
}
