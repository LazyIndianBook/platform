// A book cover: AVIF and WebP at 320 and 480 wide with the PNG for the rest (direction.md, "Images") when the cover
// is one of the site's static covers (Django's manage.py build_covers makes the sizes); a product picture as it is;
// no picture at all draws .no-cover in the subject's colours.
import { cn } from "cn";

import type { SubjectKey } from "@/lib/site";

const STATIC_COVER = /^(.*\/static\/img\/[a-z-]+)\.png$/;
const WIDTHS = [320, 480];

type CoverProps = {
  src: string | null | undefined;
  alt: string;
  sizes: string;
  priority?: boolean;
  className?: string;
};

function CoverPicture({ src, alt, sizes, priority, className }: CoverProps & { src: string }) {
  const stem = STATIC_COVER.exec(src)?.[1];
  const img = (
    // eslint-disable-next-line @next/next/no-img-element -- static covers with hand-made AVIF/WebP sizes
    <img
      src={src}
      alt={alt}
      width={480}
      height={678}
      sizes={sizes}
      className={className}
      fetchPriority={priority ? "high" : undefined}
      loading={priority ? undefined : "lazy"}
      decoding="async"
    />
  );
  if (!stem) return img;
  return (
    <picture>
      {["avif", "webp"].map((format) => (
        <source
          key={format}
          type={`image/${format}`}
          sizes={sizes}
          srcSet={WIDTHS.map((width) => `${stem}-${width}.${format} ${width}w`).join(", ")}
        />
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
