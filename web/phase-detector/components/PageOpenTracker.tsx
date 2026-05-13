"use client";

// W8-D: client-side mount-once Plausible event emitter.
// Use this inside an otherwise server-rendered page to fire a custom event
// the first time the page opens in a session. Idempotent: only fires once per mount.

import { useEffect, useRef } from "react";
import { trackEvent, type EventProps } from "@/lib/analytics";

interface Props {
  event: string;
  props?: EventProps;
}

export function PageOpenTracker({ event, props }: Props) {
  const fired = useRef(false);
  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    trackEvent(event, props);
  }, [event, props]);
  return null;
}
