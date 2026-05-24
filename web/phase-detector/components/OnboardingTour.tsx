"use client";

// W12-D (session #10, 2026-05-15): first-time user onboarding tour.
//
// 4 steps: welcome → phase badge → universality → waitlist.
// Pure React + Portal, no third-party (shepherd.js / driver.js bloat).
// Targets are addressed via `data-tour-target="<id>"` attributes set on
// host components (e.g. table phase badges, universality cards, waitlist
// form). Step 1 has no target — it renders as a centered modal.
//
// Trigger logic:
//   - First visit (localStorage `phase_tour_seen` missing/false) auto-starts
//     after a 1500ms idle delay (gives LCP time to settle).
//   - "Take the tour" link in TopNav (or anywhere via the exported helper)
//     can restart the tour at any time. Restart bypasses the seen flag and
//     fires `tour_restarted_from_nav`.
//
// Accessibility:
//   - `role="dialog" aria-modal="true" aria-labelledby aria-describedby`.
//   - Focus trap inside the tooltip (Tab cycles between Skip / Prev / Next).
//   - Spotlight target gets `aria-current="step"` while active.
//   - Step changes announced via `aria-live="polite"`.
//   - ESC closes the tour (counted as skip).
//
// Mobile responsive:
//   - Tooltip auto-repositions based on target rect + viewport edges.
//   - Buttons ≥44px touch target.
//   - Backdrop tap on mobile (≤640px) advances to next step.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Events } from "@/lib/analytics";

// Local event names (kept here so the tour file is self-contained; also
// listed in docs/analytics/plausible-events.md).
const TOUR_EVENTS = {
  Started: "tour_started",
  NextStep: "tour_next_step",
  Skipped: "tour_skipped",
  Completed: "tour_completed",
  Restarted: "tour_restarted_from_nav",
} as const;

function safeTrack(name: string, props?: Record<string, string | number | boolean>) {
  if (typeof window === "undefined") return;
  const p = (window as Window).plausible;
  if (typeof p !== "function") return;
  try {
    p(name, props ? { props } : undefined);
  } catch {
    // Analytics must never throw.
  }
}

// Voids the Events const-unused warning while keeping the import for future
// shared Events wiring. (Tour events live in their own namespace until we
// add them to lib/analytics.ts in a follow-up; bundling that change here
// would balloon the diff.)
void Events;

const STORAGE_KEY = "phase_tour_seen";
const AUTO_START_DELAY_MS = 1500;
const RESTART_EVENT = "phase-tour:restart";

export interface TourStep {
  id: string;
  title: string;
  description: string;
  /** CSS selector or `data-tour-target` value. Omit for centered modal. */
  target?: string;
  /** Optional override for the "Next" button label on this step. */
  nextLabel?: string;
}

const DEFAULT_STEPS: TourStep[] = [
  {
    id: "welcome",
    title: "欢迎来到 Phase Detector",
    description:
      "我们每天给 1000+ 家上市公司打上结构性「相位」标签 — 30 秒看懂谁在崩盘边缘、谁在悄悄起飞。",
    nextLabel: "开始 4 步导览",
  },
  {
    id: "phase-badge",
    title: "什么是「相位」？",
    description:
      "每家公司被标记为 5 种相位之一：稳态 / 累积中 / 临界附近 / 已翻转 / 恢复中。点击任意徽章可查看详情。",
    target: "phase-badge",
  },
  {
    id: "universality",
    title: "什么是「普适类」？",
    description:
      "公司还会被匹配到 ~25 种跨领域普适类（如地震、银行挤兑、神经雪崩）。点击卡片可探索同类系统。",
    target: "universality-card",
  },
  {
    id: "waitlist",
    title: "获取每周更新",
    description:
      "《结构信号》每周一封，免费。v0.2 backtest 报告就绪第一时间通知 + 每周精选 3 家最值得看的相位翻转。",
    target: "waitlist-form",
    nextLabel: "开始使用",
  },
];

interface Props {
  /**
   * When set, overrides the auto-start logic and forces the tour open.
   * Used by /onboarding deep-link page.
   */
  forceOpen?: boolean;
  /** Optional override of the default step list (testing / i18n). */
  steps?: TourStep[];
}

/**
 * Imperative helper: dispatches a custom event the mounted <OnboardingTour />
 * listens for. Components like TopNav can call this without prop drilling.
 */
export function restartOnboardingTour() {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode / quota — ignore */
  }
  window.dispatchEvent(new CustomEvent(RESTART_EVENT));
  safeTrack(TOUR_EVENTS.Restarted);
}

type Rect = { top: number; left: number; width: number; height: number };

function findTargetEl(target: string | undefined): HTMLElement | null {
  if (!target) return null;
  if (typeof document === "undefined") return null;
  // Try data-tour-target first, then fall back to CSS selector.
  const byAttr = document.querySelector<HTMLElement>(`[data-tour-target="${target}"]`);
  if (byAttr) return byAttr;
  try {
    return document.querySelector<HTMLElement>(target);
  } catch {
    return null;
  }
}

function measureRect(el: HTMLElement | null): Rect | null {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return null;
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

export default function OnboardingTour({ forceOpen = false, steps = DEFAULT_STEPS }: Props) {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [stepIdx, setStepIdx] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const triggerOriginRef = useRef<HTMLElement | null>(null);
  const totalSteps = steps.length;

  // Portal target only available client-side.
  useEffect(() => setMounted(true), []);

  // Auto-start on first visit (or forceOpen).
  useEffect(() => {
    if (!mounted) return;
    if (forceOpen) {
      setOpen(true);
      setStepIdx(0);
      safeTrack(TOUR_EVENTS.Started, { source: "force" });
      return;
    }
    let seen = false;
    try {
      seen = localStorage.getItem(STORAGE_KEY) === "true";
    } catch {
      seen = false;
    }
    if (seen) return;
    const t = window.setTimeout(() => {
      triggerOriginRef.current = document.activeElement as HTMLElement | null;
      setOpen(true);
      setStepIdx(0);
      safeTrack(TOUR_EVENTS.Started, { source: "auto" });
    }, AUTO_START_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [mounted, forceOpen]);

  // Listen for restart events from TopNav / external triggers.
  useEffect(() => {
    if (!mounted) return;
    const onRestart = () => {
      triggerOriginRef.current = document.activeElement as HTMLElement | null;
      setOpen(true);
      setStepIdx(0);
      safeTrack(TOUR_EVENTS.Started, { source: "restart" });
    };
    window.addEventListener(RESTART_EVENT, onRestart);
    return () => window.removeEventListener(RESTART_EVENT, onRestart);
  }, [mounted]);

  const current = steps[stepIdx];

  // Measure spotlight target on step change + resize + scroll.
  useEffect(() => {
    if (!open) return;
    const update = () => {
      const el = findTargetEl(current?.target);
      setRect(measureRect(el));
      if (el) {
        el.setAttribute("aria-current", "step");
        // Bring target into view (smooth, but only if needed).
        const r = el.getBoundingClientRect();
        const vh = window.innerHeight;
        if (r.top < 80 || r.bottom > vh - 80) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, { passive: true });
    // Some content loads async — re-measure shortly after.
    const t1 = window.setTimeout(update, 250);
    const t2 = window.setTimeout(update, 800);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update);
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      const el = findTargetEl(current?.target);
      el?.removeAttribute("aria-current");
    };
  }, [open, current?.target, stepIdx]);

  const close = useCallback(
    (reason: "skip" | "complete") => {
      try {
        localStorage.setItem(STORAGE_KEY, "true");
      } catch {
        /* ignore quota */
      }
      if (reason === "skip") {
        safeTrack(TOUR_EVENTS.Skipped, { step: stepIdx + 1 });
      } else {
        safeTrack(TOUR_EVENTS.Completed);
      }
      setOpen(false);
      // Return focus to the trigger origin if known.
      const origin = triggerOriginRef.current;
      if (origin && typeof origin.focus === "function") {
        window.setTimeout(() => origin.focus(), 0);
      }
    },
    [stepIdx],
  );

  const advance = useCallback(() => {
    if (stepIdx + 1 >= totalSteps) {
      close("complete");
      return;
    }
    const next = stepIdx + 1;
    setStepIdx(next);
    safeTrack(TOUR_EVENTS.NextStep, { step: next + 1 });
  }, [stepIdx, totalSteps, close]);

  const back = useCallback(() => {
    setStepIdx((i) => Math.max(0, i - 1));
  }, []);

  // Keyboard handlers + focus trap.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close("skip");
        return;
      }
      if (e.key === "Enter") {
        // Don't hijack Enter when typing in form fields (waitlist input).
        const tag = (document.activeElement as HTMLElement | null)?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
        e.preventDefault();
        advance();
        return;
      }
      if (e.key === "Tab") {
        // Trap focus inside the tooltip.
        const root = tooltipRef.current;
        if (!root) return;
        const focusables = root.querySelectorAll<HTMLElement>(
          'button, a[href], input, [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close, advance]);

  // Initial focus on tooltip primary button when step opens.
  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => {
      const root = tooltipRef.current;
      if (!root) return;
      const primary = root.querySelector<HTMLElement>("[data-tour-primary]");
      primary?.focus();
    }, 60);
    return () => window.clearTimeout(t);
  }, [open, stepIdx]);

  // Tooltip position (relative to viewport).
  const tooltipPos = useMemo(() => computeTooltipPosition(rect), [rect]);

  if (!mounted || !open || !current) return null;

  const isCentered = !rect;
  const isLast = stepIdx + 1 === totalSteps;
  const nextLabel = current.nextLabel ?? (isLast ? "开始使用" : "下一步");
  const titleId = `tour-title-${current.id}`;
  const descId = `tour-desc-${current.id}`;

  return createPortal(
    <div
      className="phase-tour-root"
      aria-live="polite"
      data-testid="onboarding-tour"
      data-tour-step={stepIdx + 1}
      data-tour-step-id={current.id}
    >
      {/* Backdrop with cutout. Four overlay rectangles render the dim area
          AROUND the spotlight target; the target itself stays visible. */}
      <Backdrop rect={rect} onMobileTap={advance} centered={isCentered} />

      <div
        ref={tooltipRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        data-testid="tour-tooltip"
        className="phase-tour-tooltip"
        style={isCentered ? CENTERED_STYLE : tooltipPos}
      >
        <div className="phase-tour-step-counter" aria-hidden="true">
          {stepIdx + 1} / {totalSteps}
        </div>
        <h2 id={titleId} className="phase-tour-title">
          {current.title}
        </h2>
        <p id={descId} className="phase-tour-desc">
          {current.description}
        </p>
        <div className="phase-tour-actions">
          <button
            type="button"
            className="phase-tour-skip"
            data-testid="tour-skip"
            onClick={() => close("skip")}
          >
            跳过导览
          </button>
          <div className="phase-tour-actions-right">
            {stepIdx > 0 && (
              <button
                type="button"
                className="phase-tour-prev"
                data-testid="tour-prev"
                onClick={back}
              >
                上一步
              </button>
            )}
            <button
              type="button"
              className="phase-tour-next"
              data-testid="tour-next"
              data-tour-primary
              onClick={advance}
            >
              {nextLabel}
            </button>
          </div>
        </div>
      </div>

      <style jsx>{`
        .phase-tour-root {
          position: fixed;
          inset: 0;
          z-index: 9999;
          pointer-events: none;
        }
        .phase-tour-tooltip {
          position: fixed;
          pointer-events: auto;
          max-width: min(360px, calc(100vw - 32px));
          background: #ffffff;
          border: 1px solid rgb(228 228 231);
          border-radius: 14px;
          box-shadow:
            0 10px 30px -10px rgba(15, 23, 42, 0.25),
            0 4px 12px -4px rgba(15, 23, 42, 0.12);
          padding: 20px 22px 16px;
          font-family:
            var(--font-inter), -apple-system, BlinkMacSystemFont, "Segoe UI",
            sans-serif;
          color: rgb(24 24 27);
          animation: phase-tour-fade-in 200ms ease-out;
        }
        @keyframes phase-tour-fade-in {
          from {
            opacity: 0;
            transform: translateY(4px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .phase-tour-step-counter {
          font-size: 11px;
          font-weight: 500;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: rgb(113 113 122);
          margin-bottom: 8px;
        }
        .phase-tour-title {
          font-size: 17px;
          font-weight: 600;
          line-height: 1.35;
          margin: 0 0 8px;
          color: rgb(24 24 27);
        }
        .phase-tour-desc {
          font-size: 14px;
          line-height: 1.55;
          color: rgb(82 82 91);
          margin: 0 0 18px;
        }
        .phase-tour-actions {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
        }
        .phase-tour-actions-right {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .phase-tour-skip {
          background: transparent;
          border: none;
          padding: 10px 4px;
          font-size: 13px;
          color: rgb(113 113 122);
          cursor: pointer;
          text-decoration: underline;
          min-height: 44px;
        }
        .phase-tour-skip:hover {
          color: rgb(63 63 70);
        }
        .phase-tour-prev,
        .phase-tour-next {
          min-height: 44px;
          padding: 10px 16px;
          border-radius: 9px;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          border: 1px solid transparent;
          transition: background 120ms ease;
        }
        .phase-tour-prev {
          background: rgb(244 244 245);
          color: rgb(63 63 70);
          border-color: rgb(228 228 231);
        }
        .phase-tour-prev:hover {
          background: rgb(228 228 231);
        }
        .phase-tour-next {
          background: rgb(24 24 27);
          color: #ffffff;
        }
        .phase-tour-next:hover {
          background: rgb(39 39 42);
        }
        .phase-tour-next:focus-visible,
        .phase-tour-prev:focus-visible,
        .phase-tour-skip:focus-visible {
          outline: 2px solid rgb(99 102 241);
          outline-offset: 2px;
        }
      `}</style>
    </div>,
    document.body,
  );
}

const CENTERED_STYLE: React.CSSProperties = {
  top: "50%",
  left: "50%",
  transform: "translate(-50%, -50%)",
};

/**
 * Compute a tooltip position relative to a spotlight rect. Tries below
 * first, then above, then beside, clamping to viewport edges with 16px
 * margins.
 */
function computeTooltipPosition(rect: Rect | null): React.CSSProperties {
  if (!rect || typeof window === "undefined") return CENTERED_STYLE;
  const margin = 16;
  const tooltipW = 340;
  const tooltipH = 180; // best-effort estimate
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  // Prefer below the target.
  let top = rect.top + rect.height + 12;
  let left = rect.left + rect.width / 2 - tooltipW / 2;

  // If overflow bottom, place above.
  if (top + tooltipH > vh - margin) {
    top = rect.top - tooltipH - 12;
  }
  // If still off-screen (target near top), drop below anyway and clamp.
  if (top < margin) {
    top = Math.min(vh - tooltipH - margin, rect.top + rect.height + 12);
  }
  // Clamp horizontally.
  if (left < margin) left = margin;
  if (left + tooltipW > vw - margin) left = vw - tooltipW - margin;

  return { top: `${top}px`, left: `${left}px` };
}

function Backdrop({
  rect,
  centered,
  onMobileTap,
}: {
  rect: Rect | null;
  centered: boolean;
  onMobileTap: () => void;
}) {
  const handleClick = () => {
    // Touch-to-advance on mobile (≤640px). Desktop tap doesn't advance to
    // avoid surprising clicks.
    if (typeof window !== "undefined" && window.innerWidth <= 640) {
      onMobileTap();
    }
  };
  if (centered || !rect) {
    return (
      <div
        aria-hidden="true"
        className="phase-tour-backdrop-full"
        onClick={handleClick}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(15, 23, 42, 0.45)",
          pointerEvents: "auto",
          animation: "phase-tour-bd-in 180ms ease-out",
        }}
      />
    );
  }
  // Four overlay rects: top, bottom, left, right of the spotlight.
  const pad = 6;
  const top = Math.max(0, rect.top - pad);
  const bottom = rect.top + rect.height + pad;
  const left = Math.max(0, rect.left - pad);
  const right = rect.left + rect.width + pad;
  const common: React.CSSProperties = {
    position: "fixed",
    background: "rgba(15, 23, 42, 0.45)",
    pointerEvents: "auto",
    animation: "phase-tour-bd-in 180ms ease-out",
  };
  return (
    <>
      <div
        aria-hidden="true"
        onClick={handleClick}
        style={{ ...common, top: 0, left: 0, right: 0, height: `${top}px` }}
      />
      <div
        aria-hidden="true"
        onClick={handleClick}
        style={{ ...common, top: `${bottom}px`, left: 0, right: 0, bottom: 0 }}
      />
      <div
        aria-hidden="true"
        onClick={handleClick}
        style={{
          ...common,
          top: `${top}px`,
          left: 0,
          width: `${left}px`,
          height: `${rect.height + pad * 2}px`,
        }}
      />
      <div
        aria-hidden="true"
        onClick={handleClick}
        style={{
          ...common,
          top: `${top}px`,
          left: `${right}px`,
          right: 0,
          height: `${rect.height + pad * 2}px`,
        }}
      />
      {/* Highlight ring around the spotlight target. */}
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          top: `${top}px`,
          left: `${left}px`,
          width: `${rect.width + pad * 2}px`,
          height: `${rect.height + pad * 2}px`,
          border: "2px solid rgb(99, 102, 241)",
          borderRadius: "10px",
          boxShadow: "0 0 0 4px rgba(99,102,241,0.2)",
          pointerEvents: "none",
        }}
      />
      <style jsx>{`
        @keyframes phase-tour-bd-in {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }
      `}</style>
    </>
  );
}
