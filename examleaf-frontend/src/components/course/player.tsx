"use client";

// The chapter's player (Chapter): the clip the page asked the API for (learn/clips/<id>/, links good for 10 minutes)
// in HlsVideo, fresh links when they have run out, and how far it was watched sent to learn/clips/<id>/progress/ every
// 15 seconds of playing, on pause and at the end (completed), so the app and the website stay in step. HlsVideo takes
// no listeners, and media events do not bubble: they are caught on the way down (capture). Nothing is sent while a
// parent's consent is awaited (the API refuses it; the page says so).
import { useEffect, useRef, useState } from "react";

import { HlsVideo } from "@/components/revision/hls-video";
import { FieldError } from "@/components/ui/field";
import { api, personal } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Clip = components["schemas"]["Clip"];

const EVERY = 15; // seconds of watching between two saves
const EVENTS = ["timeupdate", "pause", "ended"];

export function ChapterPlayer({ clip: first, save }: { clip: Clip; save: boolean }) {
  const [clip, setClip] = useState(first);
  const [unsaved, setUnsaved] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const sentAt = useRef(0);

  useEffect(() => {
    const element = box.current;
    if (!element || !save) return;
    const send = (seconds: number, completed: boolean) => {
      sentAt.current = seconds;
      personal(
        api.POST("/api/v1/learn/clips/{id}/progress/", {
          params: { path: { id: clip.id } },
          body: { seconds_watched: Math.round(seconds), completed },
        }),
      ).then(
        () => setUnsaved(false),
        () => setUnsaved(true),
      );
    };
    const watch = (event: Event) => {
      const video = event.target as HTMLVideoElement;
      if (event.type === "ended") send(video.duration || video.currentTime, true);
      else if (event.type === "pause" ? !video.ended : Math.abs(video.currentTime - sentAt.current) >= EVERY)
        send(video.currentTime, false);
    };
    for (const type of EVENTS) element.addEventListener(type, watch, true);
    return () => {
      for (const type of EVENTS) element.removeEventListener(type, watch, true);
    };
  }, [clip.id, save]);

  const reload = () => {
    personal(api.GET("/api/v1/learn/clips/{id}/", { params: { path: { id: clip.id } } })).then(
      setClip,
      () => undefined,
    );
  };
  return (
    <div ref={box} className="course-player">
      <HlsVideo key={clip.hls_url} clip={clip} reload={reload} />
      {unsaved ? (
        <FieldError role="status" className="mt-2">
          How far you watched could not be saved just now; it is tried again as you watch.
        </FieldError>
      ) : null}
    </div>
  );
}
