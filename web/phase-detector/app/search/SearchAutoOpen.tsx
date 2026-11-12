"use client";

// W13-E (session #10): client-only auto-opener for /search deep-link.

import { useEffect } from "react";
import { openCommandPalette } from "@/components/CommandPaletteProvider";

export default function SearchAutoOpen() {
  useEffect(() => {
    // Defer one tick so layout mounts the CommandPaletteProvider first.
    const t = setTimeout(() => openCommandPalette("deep-link"), 0);
    return () => clearTimeout(t);
  }, []);
  return null;
}
