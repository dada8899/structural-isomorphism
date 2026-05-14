// W10-C alpha-screener landing: 3-step "How it works" explainer.
//
// Editorial restraint per CLAUDE.md design refs (Bear / Linear). Numbered
// steps with serif step numbers as visual rhythm; body text in sans for
// readability. No icons (visual noise), no hover state (pure exposition).

import Link from "next/link";

const STEPS = [
  {
    n: "01",
    title: "Extract",
    titleZh: "提取结构特征",
    body: "Daily structural features for 1000+ public companies — feedback loops, threshold proximity, network position. Computed from filings, prices, and news flow.",
    bodyZh: "每日提取 1000+ 家公司的结构特征：反馈回路、临界点距离、网络位置。来源：财报 + 价格 + 新闻流。",
  },
  {
    n: "02",
    title: "Classify",
    titleZh: "分类标记",
    body: "A frozen Clauset-grade pipeline tags each company with one of 5 phases. Same math we use to explain bank runs, earthquakes, and grid blackouts — now applied to corporates.",
    bodyZh: "Frozen Clauset 级别的 pipeline 给每家公司打一个 5 状态标签。同一套数学——解释过银行挤兑、地震、电网崩塌——现在套到上市公司上。",
  },
  {
    n: "03",
    title: "Surface",
    titleZh: "翻面前看见",
    body: "You see flips before they're priced in. Or you don't — we publish honest backtests up front so you judge the alpha, not us.",
    bodyZh: "在市场定价前看见翻转。或者根本看不见——我们公开发布 NULL backtest，让你自己判断 alpha，不替你下结论。",
  },
];

export function HowItWorksSteps() {
  return (
    <section
      id="how-it-works"
      aria-labelledby="how-it-works-heading"
      className="mx-auto w-full max-w-5xl px-6 py-20 sm:py-24"
    >
      <div className="mb-12 max-w-2xl">
        <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
          How it works · 三步说清楚
        </p>
        <h2
          id="how-it-works-heading"
          className="text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl"
          style={{ fontFamily: "var(--font-serif), 'Noto Serif SC', serif" }}
        >
          没有黑盒。<br className="hidden sm:inline" />方法、代码、回测全部公开。
        </h2>
      </div>
      <ol className="space-y-12 sm:space-y-14">
        {STEPS.map((s) => (
          <li key={s.n} className="grid grid-cols-1 gap-6 sm:grid-cols-[140px_1fr]">
            <div
              className="select-none font-mono text-5xl font-light leading-none text-indigo-300 sm:text-6xl"
              style={{ fontFeatureSettings: "'tnum'" }}
              aria-hidden="true"
            >
              {s.n}
            </div>
            <div>
              <div className="mb-1 text-sm font-semibold uppercase tracking-wider text-zinc-900">
                {s.title}
                <span className="ml-2 font-normal normal-case tracking-normal text-zinc-500">
                  · {s.titleZh}
                </span>
              </div>
              <p className="text-base leading-relaxed text-zinc-600 sm:text-lg">
                {s.bodyZh}
              </p>
              <p className="mt-1.5 text-sm leading-relaxed text-zinc-500">
                {s.body}
              </p>
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-12 sm:mt-14">
        <Link
          href="/methodology"
          className="inline-flex items-center gap-1 text-sm font-medium text-indigo-700 underline-offset-4 hover:underline"
        >
          完整方法说明 <span aria-hidden="true">→</span>
        </Link>
      </div>
    </section>
  );
}
