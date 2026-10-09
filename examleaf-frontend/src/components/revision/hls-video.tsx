"use client";

// A clip's player: hls.js (its light build, about 120 KB gzipped) wherever Media Source Extensions exist, loaded only
// now, else the browser's own HLS (older iPhones), which then needs no script at all. Loaded itself only when a clip is
// asked for (islands.tsx, FreeClip).
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/schema";

type Clip = components["schemas"]["Clip"];

export function HlsVideo({ clip, reload }: { clip: Clip; reload: () => unknown }) {
  const video = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const [reloading, setReloading] = useState(false); // fresh links on their way: a second press sends nothing

  useEffect(() => {
    const element = video.current;
    if (!element) return;
    // as the staff player (static/learn/preview.js): hls.js wherever Media Source Extensions exist, else the
    // browser's own HLS (older iPhones), which then needs no script at all
    if (!("MediaSource" in window || "ManagedMediaSource" in window)) {
      element.src = clip.hls_url;
      return;
    }
    let gone = false;
    let hls: { destroy: () => void } | null = null;
    import("hls.js/light").then(
      ({ default: Hls }) => {
        if (gone) return;
        const player = new Hls({ enableWorker: false }); // its worker would be a blob: script, which the CSP refuses
        player.on(Hls.Events.ERROR, (_event, data) => {
          if (!data.fatal) return;
          player.destroy();
          setFailed(true);
        });
        player.loadSource(clip.hls_url);
        player.attachMedia(element);
        hls = player;
      },
      () => !gone && setFailed(true),
    ); // hls.js itself could not be loaded (offline)
    return () => {
      gone = true;
      hls?.destroy();
    };
  }, [clip.hls_url]);

  return (
    <figure className="m-0 flex flex-col gap-2">
      <video
        ref={video}
        controls
        playsInline
        preload="metadata"
        poster={clip.poster_url}
        aria-label={clip.title}
        onError={() => setFailed(true)}
        className="aspect-[9/16] max-h-[70vh] w-auto max-w-full rounded-lg bg-night"
      />
      <figcaption className="text-[15px] text-muted-foreground">{clip.title}</figcaption>
      {failed ? (
        // the links work for 10 minutes (API.md, "Playing a clip"): a fresh one is the cure for an old page
        <div role="alert" className="flex flex-wrap items-center gap-2 text-[15px]">
          <span className="font-semibold text-destructive">The clip could not be played.</span>
          <Button
            variant="ghost"
            size="sm"
            busy={reloading}
            onClick={() => {
              setReloading(true);
              void Promise.resolve(reload()).finally(() => setReloading(false));
            }}
          >
            Load it again
          </Button>
        </div>
      ) : null}
    </figure>
  );
}
