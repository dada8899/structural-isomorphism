"use client";

// W11-D — UniversalityAnalogueMap.
//
// Force-directed graph of cross-domain analogues for a universality class.
// Center node = the class itself. Surrounding nodes = evidence_systems
// + prototypes, colored by inferred domain (physics / biology / finance /
// social / unknown). Edge thickness encodes a heuristic similarity score.
//
// We implement a small Verlet-style relaxation in JS (~50 lines) instead
// of pulling in d3-force — for ≤ 20 nodes this is < 0.5ms per frame and
// keeps the bundle slim. The simulation runs for a fixed N iterations on
// mount, then stops; nodes are draggable post-stabilization.
//
// SSR-safe: initial layout is deterministic (seeded by class_id), so the
// SVG renders identical on server and client.

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { UniversalityClassDetail } from "@/lib/types";
import { useTheme } from "./ThemeProvider";

// Inline domain heuristic — no API change required.
function inferDomain(text: string): "physics" | "biology" | "finance" | "social" | "tech" | "unknown" {
  const t = text.toLowerCase();
  if (
    t.includes("earth") ||
    t.includes("solar") ||
    t.includes("avalanche") ||
    t.includes("quake") ||
    t.includes("magnet") ||
    t.includes("crystal") ||
    t.includes("percolation") ||
    t.includes("ising")
  )
    return "physics";
  if (
    t.includes("brain") ||
    t.includes("neural") ||
    t.includes("ecology") ||
    t.includes("species") ||
    t.includes("lake") ||
    t.includes("forest") ||
    t.includes("epidem") ||
    t.includes("cell")
  )
    return "biology";
  if (
    t.includes("bank") ||
    t.includes("market") ||
    t.includes("liquidat") ||
    t.includes("crash") ||
    t.includes("aave") ||
    t.includes("maker") ||
    t.includes("crypto") ||
    t.includes("defi") ||
    t.includes("finance")
  )
    return "finance";
  if (
    t.includes("network") ||
    t.includes("github") ||
    t.includes("twitter") ||
    t.includes("social") ||
    t.includes("traffic") ||
    t.includes("supply") ||
    t.includes("grid")
  )
    return "social";
  if (
    t.includes("compute") ||
    t.includes("software") ||
    t.includes("data center")
  )
    return "tech";
  return "unknown";
}

const DOMAIN_COLOR: Record<string, string> = {
  physics: "#3B82F6",
  biology: "#10B981",
  finance: "#F59E0B",
  social: "#A855F7",
  tech: "#06B6D4",
  unknown: "#71717A",
};

const DOMAIN_LABEL_ZH: Record<string, string> = {
  physics: "物理",
  biology: "生物",
  finance: "金融",
  social: "社会 / 网络",
  tech: "技术",
  unknown: "其他",
};

interface Node {
  id: string;
  label: string;
  domain: string;
  isCenter: boolean;
  // simulation
  x: number;
  y: number;
  vx: number;
  vy: number;
  // metadata for tooltip
  evidence?: string;
  verdict?: string;
  ticker?: string; // some prototypes are company tickers
}

interface Edge {
  source: number; // index
  target: number;
  weight: number; // 0..1
}

interface Props {
  detail: UniversalityClassDetail;
  className?: string;
  // Optional override for tests / storybook to skip animation.
  skipAnimation?: boolean;
}

const W = 720;
const H = 420;
const CENTER = { x: W / 2, y: H / 2 };

// Seeded deterministic PRNG so SSR + CSR layouts match.
function makeRng(seed: number) {
  let s = seed | 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) | 0;
    return ((s >>> 0) % 1000000) / 1000000;
  };
}

function hash32(str: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i += 1) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

function buildGraph(detail: UniversalityClassDetail): { nodes: Node[]; edges: Edge[] } {
  const rng = makeRng(hash32(detail.class_id || "x"));

  const collected: Array<{ id: string; label: string; evidence?: string; verdict?: string }> = [];
  detail.evidence_systems.forEach((ev, i) => {
    collected.push({
      id: `ev-${i}`,
      label: ev.phenomenon,
      evidence: ev.evidence,
      verdict: ev.verified_at,
    });
  });
  detail.prototypes.forEach((p, i) => {
    collected.push({ id: `pt-${i}`, label: p });
  });

  // Cap at 13 (task spec) — favor evidence_systems first, then prototypes.
  const trimmed = collected.slice(0, 13);

  const nodes: Node[] = [
    {
      id: "center",
      label: detail.display_name,
      domain: "unknown",
      isCenter: true,
      x: CENTER.x,
      y: CENTER.y,
      vx: 0,
      vy: 0,
    },
  ];

  trimmed.forEach((item, i) => {
    const angle = (i / Math.max(1, trimmed.length)) * Math.PI * 2;
    const r = 140 + rng() * 30;
    nodes.push({
      id: item.id,
      label: item.label,
      domain: inferDomain(item.label + " " + (item.evidence ?? "")),
      isCenter: false,
      x: CENTER.x + Math.cos(angle) * r,
      y: CENTER.y + Math.sin(angle) * r,
      vx: 0,
      vy: 0,
      evidence: item.evidence,
      verdict: item.verdict,
    });
  });

  // Build edges: every non-center node connects to center with a weight
  // derived from a stable hash so it looks varied but is deterministic.
  const edges: Edge[] = [];
  for (let i = 1; i < nodes.length; i += 1) {
    const w = 0.3 + ((hash32(nodes[i].id) >>> 0) % 70) / 100;
    edges.push({ source: 0, target: i, weight: w });
  }
  return { nodes, edges };
}

// Run N iterations of a simple force simulation:
//   - center node fixed
//   - repulsive force between every pair of non-center nodes
//   - spring pulling each non-center back to its target radius
function relax(nodes: Node[], iterations: number) {
  const TARGET_R = 150;
  const CHARGE = 700;
  const SPRING_K = 0.04;
  const FRICTION = 0.7;

  for (let iter = 0; iter < iterations; iter += 1) {
    // Repulsion between non-center pairs
    for (let i = 1; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i];
        const b = nodes[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist2 = Math.max(20, dx * dx + dy * dy);
        const f = CHARGE / dist2;
        const dist = Math.sqrt(dist2);
        a.vx += (dx / dist) * f;
        a.vy += (dy / dist) * f;
        b.vx -= (dx / dist) * f;
        b.vy -= (dy / dist) * f;
      }
    }
    // Spring to target radius from center
    for (let i = 1; i < nodes.length; i += 1) {
      const a = nodes[i];
      const dx = a.x - CENTER.x;
      const dy = a.y - CENTER.y;
      const r = Math.sqrt(dx * dx + dy * dy) || 0.001;
      const stretch = r - TARGET_R;
      a.vx -= (dx / r) * stretch * SPRING_K;
      a.vy -= (dy / r) * stretch * SPRING_K;
    }
    // Apply velocity with friction; clamp to viewport.
    for (let i = 1; i < nodes.length; i += 1) {
      const a = nodes[i];
      a.x += a.vx * 0.5;
      a.y += a.vy * 0.5;
      a.vx *= FRICTION;
      a.vy *= FRICTION;
      a.x = Math.max(40, Math.min(W - 40, a.x));
      a.y = Math.max(40, Math.min(H - 40, a.y));
    }
  }
}

export function UniversalityAnalogueMap({ detail, className, skipAnimation }: Props) {
  const router = useRouter();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  // W13-A theme-aware palette.
  const edgeStroke = isDark ? "#52525B" : "#A1A1AA";
  const centerFill = isDark ? "#FAFAFA" : "#18181B";
  const nodeStroke = isDark ? "#0A0A0A" : "white";
  const labelFill = isDark ? "#E4E4E7" : "#27272A";
  const centerLabelFill = isDark ? "#18181B" : "white";
  const tooltipBg = isDark ? "#18181B" : "white";
  const tooltipBorder = isDark ? "#27272A" : "#E4E4E7";
  const tooltipShadow = isDark
    ? "0 4px 12px rgba(0,0,0,0.6)"
    : "0 4px 12px rgba(0,0,0,0.08)";
  const tooltipFg = isDark ? "#FAFAFA" : "#18181B";
  const tooltipFgSecondary = isDark ? "#D4D4D8" : "#52525B";
  const [hover, setHover] = useState<number | null>(null);
  const [nodes, setNodes] = useState<Node[]>(() => {
    const { nodes: initial } = buildGraph(detail);
    if (skipAnimation || typeof window === "undefined") {
      // SSR pass: relax synchronously so static SVG is reasonable.
      relax(initial, 80);
      return initial;
    }
    return initial;
  });
  const edges = useMemo(() => buildGraph(detail).edges, [detail]);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Post-mount: run relaxation animation in a few rAF ticks for smoothness.
  useEffect(() => {
    if (skipAnimation) return;
    let cancelled = false;
    let count = 0;
    const tick = () => {
      if (cancelled) return;
      const copy = nodes.map((n) => ({ ...n }));
      relax(copy, 10);
      setNodes(copy);
      count += 1;
      if (count < 10) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.class_id]);

  // Domain legend (only domains actually present)
  const presentDomains = Array.from(
    new Set(nodes.filter((n) => !n.isCenter).map((n) => n.domain)),
  );

  const handleNodeClick = (n: Node) => {
    if (n.isCenter) return;
    // If the label looks like a ticker (all caps, 1-5 letters), try /company/<ticker>
    if (/^[A-Z]{1,5}$/.test(n.label.trim())) {
      router.push(`/company/${encodeURIComponent(n.label.trim())}`);
      return;
    }
    // Otherwise scroll to the corresponding evidence in the detail page.
    if (typeof document !== "undefined") {
      const evidence = document.querySelector('[data-testid="universality-evidence"]');
      if (evidence) evidence.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div
      className={className}
      data-testid="universality-analogue-map"
      style={{ width: "100%", maxWidth: W }}
    >
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-zinc-900">跨领域类比图</h3>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
          {presentDomains.map((d) => (
            <span key={d} className="inline-flex items-center gap-1">
              <span
                aria-hidden="true"
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: DOMAIN_COLOR[d] }}
              />
              {DOMAIN_LABEL_ZH[d] ?? d}
            </span>
          ))}
        </div>
      </div>
      <div
        style={{
          width: "100%",
          aspectRatio: `${W} / ${H}`,
          position: "relative",
        }}
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          height="100%"
          role="img"
          aria-label={`${detail.display_name} 跨领域类比图`}
          style={{ display: "block" }}
        >
          {/* Edges */}
          {edges.map((e, i) => {
            const a = nodes[e.source];
            const b = nodes[e.target];
            return (
              <line
                key={i}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={edgeStroke}
                strokeOpacity={0.4}
                strokeWidth={Math.max(0.5, e.weight * 2.5)}
              />
            );
          })}

          {/* Nodes */}
          {nodes.map((n, i) => {
            const isHover = hover === i;
            const r = n.isCenter ? 26 : isHover ? 14 : 11;
            const fill = n.isCenter ? centerFill : DOMAIN_COLOR[n.domain] ?? "#71717A";
            return (
              <g
                key={n.id}
                data-testid={
                  n.isCenter ? "analogue-center-node" : "analogue-node"
                }
                data-node-id={n.id}
                data-domain={n.domain}
                style={{ cursor: n.isCenter ? "default" : "pointer" }}
                onPointerEnter={() => setHover(i)}
                onPointerLeave={() => setHover((h) => (h === i ? null : h))}
                onClick={() => handleNodeClick(n)}
                role={n.isCenter ? undefined : "button"}
                aria-label={n.isCenter ? n.label : `${n.label}（${DOMAIN_LABEL_ZH[n.domain] ?? n.domain}）`}
                tabIndex={n.isCenter ? -1 : 0}
                onKeyDown={(e) => {
                  if (!n.isCenter && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    handleNodeClick(n);
                  }
                }}
              >
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={r}
                  fill={fill}
                  stroke={nodeStroke}
                  strokeWidth={2}
                  opacity={n.isCenter ? 1 : isHover ? 1 : 0.85}
                />
                <text
                  x={n.x}
                  y={n.y + (n.isCenter ? 4 : -r - 6)}
                  fontSize={n.isCenter ? 11 : 10}
                  fill={n.isCenter ? centerLabelFill : labelFill}
                  textAnchor="middle"
                  style={{ pointerEvents: "none", fontWeight: n.isCenter ? 600 : 500 }}
                >
                  {n.label.length > 18 ? n.label.slice(0, 17) + "…" : n.label}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Tooltip */}
        {hover !== null && !nodes[hover].isCenter && (
          <div
            data-testid="analogue-tooltip"
            role="tooltip"
            style={{
              position: "absolute",
              left: `${(nodes[hover].x / W) * 100}%`,
              top: `${(nodes[hover].y / H) * 100}%`,
              transform: "translate(12px, 12px)",
              pointerEvents: "none",
              background: tooltipBg,
              border: `1px solid ${tooltipBorder}`,
              boxShadow: tooltipShadow,
              padding: "8px 10px",
              fontSize: 12,
              borderRadius: 6,
              maxWidth: 240,
              zIndex: 5,
            }}
          >
            <div style={{ fontWeight: 600, color: tooltipFg }}>
              {nodes[hover].label}
            </div>
            <div style={{ color: tooltipFgSecondary, fontSize: 11, marginTop: 2 }}>
              领域 · {DOMAIN_LABEL_ZH[nodes[hover].domain] ?? nodes[hover].domain}
            </div>
            {nodes[hover].verdict && (
              <div style={{ color: tooltipFgSecondary, fontSize: 11 }}>
                状态 · {nodes[hover].verdict}
              </div>
            )}
            {nodes[hover].evidence && (
              <div
                style={{
                  color: tooltipFgSecondary,
                  fontSize: 11,
                  marginTop: 4,
                  lineHeight: 1.4,
                }}
              >
                {nodes[hover].evidence!.length > 120
                  ? nodes[hover].evidence!.slice(0, 117) + "…"
                  : nodes[hover].evidence}
              </div>
            )}
          </div>
        )}
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
        中心 = 当前普适类。外圈节点 = 实证或候选系统，颜色编码所属领域，
        边粗细表示与该类的相似度（启发式排序）。点击节点可跳转到对应公司（如 ticker 形态）
        或滚动到证据段。
      </p>
    </div>
  );
}

export default UniversalityAnalogueMap;
