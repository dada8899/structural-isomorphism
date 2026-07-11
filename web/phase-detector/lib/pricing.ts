// Pricing tiers — source of truth for the frontend. Backend mirrors these
// numbers in web/backend/api/checkout_mock.py:_TIER_PRICING. Keep in sync
// when prices change.
//
// W10-B (session #10): Free / Pro $19 / Team $99 mock pricing. Real Stripe
// integration deferred until PMF signal (target Q3 2026).

export type TierId = "free" | "pro" | "team";
export type Interval = "month" | "year";

export interface PricingTier {
  id: TierId;
  name: string;
  /** Monthly USD price. Annual is monthly × 10 (2 months free). */
  monthly: number;
  /** Short pitch under the price. */
  pitch: string;
  /** Feature checklist — null entries render as a dash (—). */
  features: Array<{ label: string; included: boolean }>;
  /** Visible CTA on the card. */
  cta: string;
  /** Pro is highlighted as "most popular". */
  highlight?: boolean;
}

export const TIERS: PricingTier[] = [
  {
    id: "free",
    name: "Free",
    monthly: 0,
    pitch: "Explore the current 597-ticker demo research snapshot.",
    features: [
      { label: "597 个 demo ticker 研究快照", included: true },
      { label: "状态评分只读访问", included: true },
      { label: "公开 Discord 社群", included: true },
      { label: "周日免费 newsletter", included: true },
      { label: "扩展数据覆盖（规划）", included: false },
      { label: "历史相位翻转 API", included: false },
      { label: "newsletter 抢先看", included: false },
      { label: "Pro 专属 Discord 频道", included: false },
    ],
    cta: "Open research preview",
  },
  {
    id: "pro",
    name: "Pro",
    monthly: 19,
    pitch: "Planned analyst workflow; not yet available for purchase.",
    features: [
      { label: "扩展数据覆盖（规划）", included: true },
      { label: "历史相位翻转 API（规划）", included: true },
      { label: "筛选、告警与导出（规划）", included: true },
      { label: "5 个共享 seat", included: false },
      { label: "API 100K req / mo", included: false },
      { label: "方法论点播", included: false },
    ],
    cta: "Join research preview",
    highlight: true,
  },
  {
    id: "team",
    name: "Team",
    monthly: 99,
    pitch: "Planned team workflow; not yet available for purchase.",
    features: [
      { label: "Pro 所有功能", included: true },
      { label: "5 个共享 seat", included: true },
      { label: "Slack / Discord 优先支持", included: true },
      { label: "API key 100K req / mo", included: true },
      { label: "方法论点播请求", included: true },
      { label: "Custom phase alerts", included: true },
      { label: "白名单 ticker 优先纳入", included: true },
      { label: "季度结构 review 会议", included: true },
    ],
    cta: "Register team interest",
  },
];

/** Annual = monthly × 10 (2 months free). Saves monthly × 2 per year. */
export function annualPrice(tier: PricingTier): number {
  return tier.monthly * 10;
}

/** Dollars saved when going annual vs. paying monthly × 12. */
export function annualSavings(tier: PricingTier): number {
  return tier.monthly * 2;
}

export function getTier(id: TierId): PricingTier | undefined {
  return TIERS.find((t) => t.id === id);
}
