import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumb } from "@/components/Breadcrumb";
import { PageOpenTracker } from "@/components/PageOpenTracker";
import { PricingTable } from "@/components/PricingTable";
import { Events } from "@/lib/analytics";
import { buildMetadata } from "@/lib/seo";

// W10-B (session #10): pricing page. Free / Pro $19 / Team $99 mock.
// Real Stripe integration deferred until PMF signal — see README in
// /checkout/mock for migration plan.
//
// Design references consulted (per CLAUDE.md "competitors first" rule):
//   - Linear.app/pricing (3-column, billing toggle, "Most popular" badge)
//   - Apple iCloud+ storage tiers (restrained palette, generous whitespace)
//   - Lobehub /pricing (feature parity, no rainbow gradients)
//   - OpenWebUI org page (community vs. team distinction)
//   - Penpot pricing (annual savings inline)
// Anti-patterns avoided: gradient CTAs, glow effects, emoji bullets,
// competing badges.

// W12-B (2026-05-15): canonical + OG image + twitter card added via buildMetadata helper.
export const metadata: Metadata = buildMetadata({
  title: "定价 — Phase Detector",
  description:
    "Free / Pro $19 / Team $99。给分析师、写手、买方团队的结构化股票研究订阅。1000+ ticker 全量访问、API、newsletter 抢先看。",
  path: "/pricing",
  ogImage: "/og/pricing.png",
});

export default function PricingPage() {
  return (
    <article className="mx-auto max-w-5xl">
      <PageOpenTracker event={Events.PricingView} />
      <Breadcrumb items={[{ label: "首页", href: "/" }, { label: "定价" }]} />

      <header className="mx-auto mb-12 max-w-2xl text-center">
        <h1
          className="mb-3 text-3xl font-semibold tracking-tight text-zinc-900 md:text-4xl"
          style={{ fontFamily: "'Noto Serif SC', serif" }}
        >
          为认真的研究付一杯咖啡的价。
        </h1>
        <p className="text-base leading-relaxed text-zinc-600">
          每天免费看 100 家公司的状态评分；想要 1000+ ticker、API
          访问、newsletter 抢先看，升级到 Pro。
        </p>
      </header>

      <PricingTable defaultInterval="month" />

      {/* Real-Stripe disclaimer (PMF gate) */}
      <section
        aria-labelledby="pmf-disclaimer-heading"
        className="mx-auto mt-12 max-w-3xl rounded-xl border border-amber-200 bg-amber-50/60 px-6 py-5"
      >
        <h2
          id="pmf-disclaimer-heading"
          className="mb-1 text-sm font-semibold text-amber-900"
        >
          研究预览阶段：Stripe 接入还在路上
        </h2>
        <p className="text-sm leading-relaxed text-amber-900/85">
          这是一个 mock checkout。当前点击「Start Pro」会进入一个模拟的
          Stripe 结账页，**不会**真扣款。我们在 PMF 信号清晰之前不接入真实
          Stripe（目标 Q3 2026）。但你输入的订阅意向会进入「先于
          Stripe」的 waitlist——真上线时会优先邀请并享首月 50% off。
        </p>
      </section>

      {/* FAQ — short, only the questions that genuinely come up. */}
      <section
        aria-labelledby="faq-heading"
        className="mx-auto mt-16 max-w-3xl"
      >
        <h2
          id="faq-heading"
          className="mb-6 text-xl font-semibold tracking-tight text-zinc-900"
        >
          常见问题
        </h2>
        <dl className="space-y-6 text-sm">
          <div>
            <dt className="font-medium text-zinc-900">
              「100 家」和「1000+」具体指什么？
            </dt>
            <dd className="mt-1.5 leading-relaxed text-zinc-600">
              Free 用户能看 100 家全球大盘股的状态评分（市值 &gt;
              $50B）；Pro 解锁全量 1000+ ticker，含中型股、亚洲市场、
              港股美股双重上市公司。
            </dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-900">
              方法论会公开吗？
            </dt>
            <dd className="mt-1.5 leading-relaxed text-zinc-600">
              方法论页面对所有用户公开（也欢迎 fork 我们的{" "}
              <a
                href="https://github.com/dada8899/structural-isomorphism"
                target="_blank"
                rel="noopener"
                className="underline-offset-2 hover:underline"
              >
                GitHub repo
              </a>
              ）。Pro 解锁的是「批量访问 + 数据导出 + API」，不是把方法藏起来。
            </dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-900">
              Team 套餐的 5 个 seat 怎么算？
            </dt>
            <dd className="mt-1.5 leading-relaxed text-zinc-600">
              每个 seat 一个邮箱、独立登录、共享同一个 Team 看板。超过 5 人
              的团队请通过{" "}
              <a
                href="mailto:hello@bytedance.city"
                className="underline-offset-2 hover:underline"
              >
                邮件
              </a>
              联系我们做 enterprise 报价。
            </dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-900">
              我可以随时取消吗？
            </dt>
            <dd className="mt-1.5 leading-relaxed text-zinc-600">
              当然。真 Stripe 上线后会在账户页提供一键取消，已付期内继续享有
              Pro 功能，下一周期不再续费。研究预览阶段不收费，所以现在加入
              本身也没有锁定成本。
            </dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-900">
              这是投资建议吗？
            </dt>
            <dd className="mt-1.5 leading-relaxed text-zinc-600">
              不是。状态评分是结构动力学的研究输出，不是个股推荐。任何
              交易决策请独立核实数据并咨询持牌顾问。
            </dd>
          </div>
        </dl>
      </section>

      <div className="mt-16 text-center text-sm text-zinc-500">
        还想再读一下方法？看{" "}
        {/* W12-A: axe `link-in-text-block` — inline links inside running text
         * must carry a non-color visual affordance. Switched from
         * hover:underline to always-on underline. */}
        <Link
          href="/methodology"
          className="text-zinc-700 underline underline-offset-2"
        >
          方法论页面
        </Link>{" "}
        或{" "}
        <Link
          href="/about"
          className="text-zinc-700 underline underline-offset-2"
        >
          关于
        </Link>
        。
      </div>
    </article>
  );
}
