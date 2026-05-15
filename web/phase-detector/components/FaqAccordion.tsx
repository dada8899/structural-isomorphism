"use client";

// W10-C alpha-screener landing: FAQ accordion.
//
// 7 questions covering the most common evaluation hurdles:
//   1. Is this investment advice?
//   2. How accurate is the phase classification?
//   3. What does "near critical" mean?
//   4. Can I export data?
//   5. When does pricing launch?
//   6. How often does data refresh?
//   7. What's your conflict-of-interest stance?
//
// Plain <details>/<summary> for zero-JS-cost progressive disclosure +
// native a11y (no role/aria juggling needed). We style the open/close arrow
// with CSS so it works without React state.

import Link from "next/link";

interface QA {
  q: string;
  a: React.ReactNode;
}

const QUESTIONS: QA[] = [
  {
    q: "这是投资建议吗？",
    a: (
      <>
        不是。Phase Detector 是<strong>研究预览</strong>——把复杂系统的相变数学套到上市公司上，公开展示我们的看法和回测。
        所有信号<strong>仅供独立研究</strong>，不构成买卖建议、不构成证券推荐、不替代你自己的判断。
        我们公开发布的 NULL backtest（Sharpe lift −0.07, p = 0.57）就说明：alpha 不显著时我们也照实写。
      </>
    ),
  },
  {
    q: "5 状态分类有多准？",
    a: (
      <>
        分类基于一套<strong>frozen pipeline</strong>（每月仅训练校准一次，不日更模型），在 13 个跨领域系统上做过 Clauset 级校验
        （地震、银行挤兑、神经雪崩、电网级联、野火等）。
        在公司域上，extraction_confidence 字段给出每家公司的提取置信度，<code>&lt; 0.6</code> 的我们会标 caveat。
        准确率不是单一数字——
        <Link href="/methodology" className="text-indigo-700 underline-offset-2 hover:underline">
          完整方法说明
        </Link>{" "}
        有 confusion matrix 和每个状态的 precision/recall。
      </>
    ),
  },
  {
    q: '"临界附近"具体是什么意思？',
    a: (
      <>
        临界附近 = <strong>系统接近相变边界但尚未翻转</strong>。在物理上的标志是：
        <em>波动放大</em>（critical slowing down）、<em>反馈开始自我加强</em>、
        <em>对小扰动敏感度上升</em>。
        在公司语境下表现为：业务指标波动周期缩短、关键比率开始钝化、新闻敏感度异常。
        临界点之后系统会跳到另一个吸引子（可能是好结局也可能是崩盘）——我们不预测方向，只标记"已经站在边上"。
      </>
    ),
  },
  {
    q: "可以导出数据吗？",
    a: (
      <>
        Phase 1（当前）：通过 <Link href="/companies" className="text-indigo-700 underline-offset-2 hover:underline">filter UI</Link> 浏览 + 单页查看，开放 read-only JSON API。
        Phase 2（付费版上线后）：CSV 导出、webhook 推送、自定义 watchlist。
        开发者可以现在就直接调 <code className="rounded bg-zinc-100 px-1 py-0.5 text-[12px]">GET /api/screener</code>——code 全开源，结构在{" "}
        <a
          href="https://github.com/dada8899/structural-isomorphism"
          target="_blank"
          rel="noopener"
          className="text-indigo-700 underline-offset-2 hover:underline"
        >
          GitHub
        </a>{" "}
        上。
      </>
    ),
  },
  {
    q: "付费版什么时候上线？",
    a: (
      <>
        当前是<strong>研究预览阶段</strong>——免费、限速、不卖任何东西。
        付费 tier 计划在<strong>v0.2 backtest 通过显著性</strong>之后启动（不通过就不卖，凡是付费版上线一定附独立审计的 Sharpe lift 报告）。
        想第一时间知道？在下方留邮箱，我们只在 v0.2 backtest 报告就绪时发<strong>一封</strong>邮件，不发别的。
      </>
    ),
  },
  {
    q: "数据多久刷新一次？",
    a: (
      <>
        结构特征：<strong>每日 23:00 UTC</strong>（财报、价格、新闻流的隔夜批处理）。
        相位分类：<strong>每周一次</strong>——避免日内噪声触发假翻转。
        遇到极端事件（财报暴雷、并购公告等）会触发<strong>临时重算</strong>，标记为 <code>flash_update</code>。
        最后更新时间显示在每家公司的详情页顶部。
      </>
    ),
  },
  {
    q: "你们有利益冲突吗？",
    a: (
      <>
        利益冲突声明：
        <ol className="ml-5 mt-2 list-decimal space-y-1.5">
          <li>我们<strong>不持有</strong>覆盖列表中任何公司的股票（团队成员个人持仓 &gt; 0.1% 净资产必须申报并从覆盖列表剔除）。</li>
          <li>我们<strong>不接受</strong>来自被覆盖公司的赞助、广告、付费推广。</li>
          <li>我们<strong>不做 market-making</strong>、不做对冲基金、不参与做空报告（这条永久写入治理文件）。</li>
        </ol>
        相位评分以<strong>客观可重现</strong>为目标——任何认为我们的方法或评分有偏的，欢迎在 GitHub Issue 上挑战。
      </>
    ),
  },
];

export function FaqAccordion() {
  return (
    <section
      aria-labelledby="faq-heading"
      className="mx-auto w-full max-w-3xl px-6 py-20 sm:py-24"
    >
      <div className="mb-10">
        <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
          FAQ · 常见问题
        </p>
        <h2
          id="faq-heading"
          className="text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl"
          style={{ fontFamily: "var(--font-serif), 'Noto Serif SC', serif" }}
        >
          先把疑虑摊在台面上。
        </h2>
      </div>
      <ul className="divide-y divide-zinc-200 border-y border-zinc-200">
        {QUESTIONS.map((qa) => (
          <li key={qa.q}>
            <details className="group py-5 sm:py-6" data-testid="faq-item">
              <summary className="flex cursor-pointer list-none items-start justify-between gap-4 text-left">
                <span className="text-base font-medium text-zinc-900 sm:text-lg">
                  {qa.q}
                </span>
                <span
                  className="mt-1 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-zinc-300 text-zinc-500 transition-transform duration-150 group-open:rotate-45 group-open:border-indigo-300 group-open:text-indigo-700"
                  aria-hidden="true"
                >
                  +
                </span>
              </summary>
              <div className="mt-3 max-w-prose text-sm leading-relaxed text-zinc-600 sm:text-base">
                {qa.a}
              </div>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}
