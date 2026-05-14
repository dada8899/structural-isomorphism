"use client";

// W13-E (session #10): mount-once provider for the Cmd+K command palette.
//
// Lives in app/layout.tsx alongside <OnboardingTour /> so the global
// Cmd+K / Ctrl+K shortcut is active everywhere.
//
// Exposes a module-level imperative API (openCommandPalette / closeCommandPalette)
// so any component (TopNav, mobile drawer, /search page) can open the palette
// without prop-drilling or context plumbing.

import { useCallback, useEffect, useState } from "react";
import CommandPalette from "./CommandPalette";

type OpenSource = "shortcut" | "nav-click" | "deep-link";

type Listener = (open: boolean, source: OpenSource) => void;

const listeners: Set<Listener> = new Set();
let isOpen = false;
let lastSource: OpenSource = "shortcut";

function notify() {
  for (const l of listeners) l(isOpen, lastSource);
}

/** Open the palette from any component. */
export function openCommandPalette(source: OpenSource = "nav-click") {
  isOpen = true;
  lastSource = source;
  notify();
}

/** Close the palette. */
export function closeCommandPalette() {
  isOpen = false;
  notify();
}

/** Toggle the palette. */
export function toggleCommandPalette(source: OpenSource = "shortcut") {
  isOpen = !isOpen;
  lastSource = source;
  notify();
}

/** True if the keyboard event happened in a text input — we don't hijack those. */
function isEditingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

export default function CommandPaletteProvider() {
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState<OpenSource>("shortcut");

  useEffect(() => {
    const l: Listener = (next, src) => {
      setOpen(next);
      setSource(src);
    };
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);

  // Global Cmd+K / Ctrl+K shortcut.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onKey = (e: KeyboardEvent) => {
      // Cmd+K (Mac) or Ctrl+K (Win/Linux).
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        // Inside <input> we still want the shortcut to work — but only if
        // the user isn't mid-edit on something else. The Cmd modifier
        // disambiguates this; most browsers' default Ctrl+K is "focus
        // address bar" (Firefox) or no-op (Chrome), so overriding is fine.
        e.preventDefault();
        toggleCommandPalette("shortcut");
        return;
      }
      // Bare `/` opens search — but ONLY outside text inputs.
      if (e.key === "/" && !isEditingTarget(e.target) && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        toggleCommandPalette("shortcut");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onClose = useCallback(() => closeCommandPalette(), []);

  return <CommandPalette open={open} onClose={onClose} source={source} />;
}
