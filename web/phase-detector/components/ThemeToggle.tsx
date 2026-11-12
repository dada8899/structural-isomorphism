"use client";

// W13-A (session #10, 2026-05-15): 3-state theme toggle.
//
// Renders a horizontal segmented control: System | Light | Dark.
// Icons-only on mobile; icon + label on sm:+ for clarity.
// All three buttons share a single role=radiogroup so keyboard arrows
// move focus between them (WAI-ARIA radio pattern).
//
// Visual: aligns with TopNav's typography (text-sm, text-zinc-600 default).
// Active state uses the token-backed accent color so dark mode picks the
// right tint automatically.

import { useTheme, type ThemeMode } from "./ThemeProvider";

const OPTIONS: Array<{
  value: ThemeMode;
  label: string;
  icon: JSX.Element;
}> = [
  {
    value: "system",
    label: "系统",
    icon: (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
        <line x1="8" y1="21" x2="16" y2="21" />
        <line x1="12" y1="17" x2="12" y2="21" />
      </svg>
    ),
  },
  {
    value: "light",
    label: "亮",
    icon: (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
      </svg>
    ),
  },
  {
    value: "dark",
    label: "暗",
    icon: (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    ),
  },
];

export default function ThemeToggle({
  className,
  compact = false,
}: {
  className?: string;
  compact?: boolean;
}) {
  const { theme, setTheme } = useTheme();
  return (
    <div
      role="radiogroup"
      aria-label="主题切换"
      data-testid="theme-toggle"
      className={
        "inline-flex items-center gap-0.5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] p-0.5 text-[var(--text-secondary)] " +
        (className ?? "")
      }
    >
      {OPTIONS.map((opt) => {
        const active = theme === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={`切换至${opt.label}主题`}
            data-testid={`theme-toggle-${opt.value}`}
            onClick={() => setTheme(opt.value)}
            className={
              "inline-flex h-7 items-center gap-1 rounded px-2 text-xs transition-colors duration-300 ease-in-out " +
              (active
                ? "bg-[var(--accent)] text-[var(--accent-fg)]"
                : "hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]")
            }
          >
            <span aria-hidden="true">{opt.icon}</span>
            {!compact && (
              <span className="hidden sm:inline">{opt.label}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
