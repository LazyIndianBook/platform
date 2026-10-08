// A book cover or a product picture, always with its width and height: a product's picture as the API gives it (its
// AVIF and WebP sizes, then the uploaded original); one of the site's static covers with the AVIF and WebP at 320 and
// 480 wide that Django's manage.py build_covers makes (direction.md, "Images"); no picture at all draws .no-cover in the
// subject's colours. The static covers come at 240 too: a phone's 104 to 112 px box at 1.75x takes it, not the 320.
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
        "flex aspect-[480/678] flex-col items-center justify-center gap-1.5 rounded-cover bg-(--base,var(--navy)) p-4 text-center text-white shadow-cover",
      )}
    >
      <span className="font-head text-[15px] leading-none font-extrabold">
        Exam<span className="text-leaf-light">Leaf</span>
      </span>
      <strong className="font-head text-2xl leading-tight font-extrabold text-white">{name}</strong>
      <span className="rounded-pill bg-(--pill,var(--leaf-light)) px-2.5 py-0.5 font-head text-xs font-bold text-(--base,var(--navy))">
        {kind}
      </span>
      <span className="text-sm font-semibold text-(--pill,var(--leaf-light))">Class 12 · 2027</span>
    </div>
  );
}

export { CoverPicture, NoCover };
