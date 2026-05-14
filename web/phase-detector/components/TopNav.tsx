"use client";

// W6-C: extracted top nav with mobile hamburger.
// Audit § 5 mobile chrome: top nav items wrap onto two lines on 375px
// viewports. Collapse links into a drawer below sm: 640px, keep horizontal
// row on ≥ sm.
// W11-B (session #10): EN | 中 language switcher appended after the link
// row on desktop, inside the drawer on mobile.
// W12-C (session #10): slide-on-scroll-up / off-scroll-down on mobile.
// The sticky header's parent <header> element gets a `data-nav-hidden`
// attribute toggled by useScrollDirection so we can drive the CSS
// transform without breaking the existing layout.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import LanguageSwitcher from "./LanguageSwitcher";
import { restartOnboardingTour } from "./OnboardingTour";
import { openCommandPalette } from "./CommandPaletteProvider";
import ThemeToggle from "./ThemeToggle";
