// A book cover or a product picture, always with its width and height: a product's picture as the API gives it (its
// AVIF and WebP sizes, then the uploaded original); one of the site's static covers with the AVIF and WebP at 320 and
// 480 wide that Django's manage.py build_covers makes (direction.md, "Images"); no picture at all draws NoCover, the
// card of the Shop artboard: the subject's base colour, the mono eyebrow, the subject and the kind in the serif and
// "cover coming" (decorative: the card names the product). The static covers come at 240 too: a phone's 104 to 112 px
// box at 1.75x takes it, not the 320.
import { cn } from "cn";

import type { components } from "@/lib/api/schema";
import type { SubjectKey } from "@/lib/site";

export type Picture = components["schemas"]["Picture"];

const STATIC_COVER = /^(.*\/static\/img\/[a-z-]+)\.png$/;
const WIDTHS = [240, 320, 480];

type CoverProps = {
  src: string | Picture | null | undefined;
  alt: string;
  sizes: string;
  priority?: boolean;
  className?: string;
};

/** The <source>s of a picture: the API's by type (AVIF first), or a static cover's hand-made sizes. */
function sourcesOf(src: string | Picture): [string, string][] {
  if (typeof src !== "string")
    return Object.entries(src.sources).map(([type, sizes]) => [
      type,
      Object.entries(sizes)
        .map(([width, url]) => `${url} ${width}w`)
        .join(", "),
    ]);
  const stem = STATIC_COVER.exec(src)?.[1];
  if (!stem) return [];
  return ["avif", "webp"].map((format) => [
    `image/${format}`,
    WIDTHS.map((width) => `${stem}-${width}.${format} ${width}w`).join(", "),
  ]);
}

function CoverPicture({ src, alt, sizes, priority, className }: CoverProps & { src: string | Picture }) {
  const picture = typeof src === "string" ? null : src;
  const sources = sourcesOf(src);
  const img = (
    // eslint-disable-next-line @next/next/no-img-element -- the API's and the static covers' own AVIF/WebP sizes
    <img
      src={picture ? picture.src : (src as string)}
      alt={alt}
      width={picture?.width ?? 480}
      height={picture?.height ?? 678}
      sizes={sizes}
      className={className}
      fetchPriority={priority ? "high" : undefined}
      loading={priority ? undefined : "lazy"}
      decoding="async"
    />
  );
  if (!sources.length) return img;
  return (
    <picture>
      {sources.map(([type, srcSet]) => (
        <source key={type} type={type} sizes={sizes} srcSet={srcSet} />
      ))}
      {img}
    </picture>
  );
}

function NoCover({ subject, name, kind }: { subject?: SubjectKey; name: string; kind: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        subject && `subject-${subject}`,
        "flex aspect-[480/678] flex-col justify-between rounded-[3px] bg-(--base,var(--navy)) p-[18px] text-white",
      )}
    >
      <span className="font-mono text-[11px] leading-none font-medium tracking-[0.08em] text-white/85 uppercase">
        ExamLeaf · ASSEB 12
      </span>
      <span className="flex flex-col font-head text-[26px] leading-[1.05] font-semibold">
        <span>{name}</span>
        <span>{kind}</span>
      </span>
      <span className="font-mono text-[11px] leading-none font-medium text-white/85">cover coming</span>
    </div>
  );
}

export { CoverPicture, NoCover };
