// W11-B i18n: Chinese-language landing (/zh).
//
// Mirrors app/page.tsx structure; copy is fully translated. Reuses
// ExploreCardsGrid, HowItWorksSteps, TrustSignalsRow, FaqAccordion as-is
// (they already render Chinese-primary copy). Hero swapped for
// LandingHeroZh to keep the EN landing visually unchanged.

import Link from "next/link";
import { LandingHeroZh } from "@/components/LandingHeroZh";
import { ExploreCardsGrid } from "@/components/ExploreCardsGrid";
import { HowItWorksSteps } from "@/components/HowItWorksSteps";
import { TrustSignalsRow } from "@/components/TrustSignalsRow";
import { FaqAccordion } from "@/components/FaqAccordion";
import { WaitlistForm } from "@/components/WaitlistForm";
import { MOCK_COMPANIES } from "@/lib/mock-data";
import type { Company } from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

async function fetchExploreCards(): Promise<Company[]> {
  if (USE_MOCK) {
    const approaching = MOCK_COMPANIES.filter(
      (c) => c.critical_point_state === "approaching_critical",
    ).slice(0, 3);
    const transitioned = MOCK_COMPANIES.filter(
      (c) => c.critical_point_state === "post_critical_transition",
    ).slice(0, 3);
    const out: Company[] = [];
    for (let i = 0; i < 3; i += 1) {
      if (approaching[i]) out.push(approaching[i]);
      if (transitioned[i]) out.push(transitioned[i]);
    }
    return (out.length >= 6 ? out : MOCK_COMPANIES.slice(0, 6)).slice(0, 6);
  }
  try {
    const [approaching, transitioned] = await Promise.all([
      fetch(`${API_BASE}/screener?critical_point_state=approaching_critical&limit=4`, {
        next: { revalidate: 600 },
      })
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => []),
      fetch(`${API_BASE}/screener?critical_point_state=post_critical_transition&limit=4`, {
        next: { revalidate: 600 },
      })
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => []),
    ]);
    const a = Array.isArray(approaching) ? approaching : (approaching?.results ?? []);
    const t = Array.isArray(transitioned) ? transitioned : (transitioned?.results ?? []);
    const out: Company[] = [];
    for (let i = 0; i < 3; i += 1) {
      if (a[i]) out.push(a[i]);
      if (t[i]) out.push(t[i]);
    }
    return out.slice(0, 6);
  } catch {
    return [];
  }
}

export const revalidate = 600;

export default async function LandingPageZh() {
  const cards = await fetchExploreCards();

  return (
    <div className="-mx-6 -my-6 sm:-mx-6">
      <LandingHeroZh />

      {cards.length > 0 ? (
        <ExploreCardsGrid cards={cards} />
      ) : (
        <section className="mx-auto w-full max-w-4xl px-6 py-16 text-center text-sm text-zinc-500">
          正在加载最近翻转的公司…
        </section>
      )}

      <HowItWorksSteps />

      <TrustSignalsRow />

      <section
        aria-labelledby="waitlist-heading-zh"
        className="mx-auto w-full max-w-3xl px-6 py-20 sm:py-24"
      >
        <div className="rounded-3xl border border-zinc-200 bg-gradient-to-br from-white via-white to-indigo-50/40 p-8 sm:p-12">
          <p className="mb-3 text-xs font-medium uppercase tracking-[0.18em] text-indigo-700">
            Newsletter · 每周一封
          </p>
          <h2
            id="waitlist-heading-zh"
            className="mb-3 text-2xl font-semibold tracking-tight text-zinc-900 sm:text-3xl"
            style={{ fontFamily: "var(--font-serif), 'Noto Serif SC', serif" }}
          >
            《结构信号》— 每周一封
          </h2>
          <p className="mb-6 max-w-prose text-sm leading-relaxed text-zinc-600 sm:text-base">
            v0.2 backtest 报告就绪时第一时间通知 + 每周精选 3 家最值得看的相位翻转。
            <strong className="text-zinc-900">不卖广告，不卖列表，不发别的。</strong>
          </p>
          <WaitlistForm
            placement="footer"
            source="phase_detector_landing_zh"
            className="border-0 bg-transparent p-0 shadow-none"
          />
        </div>
      </section>

      <FaqAccordion />

      <section className="mx-auto w-full max-w-4xl px-6 pb-24">
        <Link
          href="https://beta.structural.bytedance.city/classes"
          target="_blank"
          rel="noopener"
          className="block rounded-2xl border border-zinc-200 bg-white px-6 py-6 transition hover:border-indigo-300 hover:bg-indigo-50/30 sm:px-8"
        >
          <span className="mb-1 block text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            姐妹产品 · Sister product
          </span>
          <span className="block text-base text-zinc-900 sm:text-lg">
            想找跨学科的解法？→{" "}
            <strong className="font-semibold">Structural</strong>：把你的难题，换成另一个学科已经解过的题
          </span>
        </Link>
      </section>
    </div>
  );
}

export const metadata = {
  title: "Phase Detector — 每日 1000+ 家上市公司的结构性信号",
  description:
    "每条都是一个假设。每条都附带证据。alpha 是否成立由你判断。1000+ 家上市公司每日结构信号——同一套数学解释过地震、银行挤兑、电网级联。",
};
