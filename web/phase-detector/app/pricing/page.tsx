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
  title: "研究预览 — Phase Detector",
  description:
    "Phase Detector 当前免费开放 597 个 demo ticker 研究快照；付费权益尚未上线。",
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
          先验证研究价值，再开放付费。
        </h1>
        <p className="text-base leading-relaxed text-zinc-600">
          当前展示 597 个 demo ticker 的研究快照。付费、实时价格、API
          权益和团队协作尚未形成可验证闭环，因此暂不接受付款。
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
          研究预览阶段：当前不开放支付
        </h2>
        <p className="text-sm leading-relaxed text-amber-900/85">
          页面中的 Pro 与 Team 是方向说明，不代表已经交付的商品。CTA 只会
          登记研究预览意向，不会创建模拟订单、订阅或扣款。
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
              当前覆盖具体是什么？
            </dt>
            <dd className="mt-1.5 leading-relaxed text-zinc-600">
              当前 EWS 快照包含 597 个 ticker，并明确标记为 demo provenance。
              它用于验证方法和产品体验，不代表实时市场覆盖。
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
              ）。批量访问、数据导出和 API 都仍是规划能力，当前没有付费解锁。
            </dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-900">
              Team 方案现在能购买吗？
            </dt>
            <dd className="mt-1.5 leading-relaxed text-zinc-600">
              不能。团队席位与共享看板仍在规划，当前只登记需求。研究团队可通过{" "}
              <a
                href="mailto:hello@bytedance.city"
                className="underline-offset-2 hover:underline"
              >
                邮件
              </a>
              联系我们提供使用场景，不会产生报价或订单。
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
