const MAIN_PRODUCT_URL = "https://beta.structural.bytedance.city";

/**
 * Persistent product-boundary disclosure.
 *
 * Phase is a frozen research subproduct, while beta is the canonical
 * Structural product and account entrypoint. Keeping this in RootLayout
 * makes the relationship explicit on every page, including auth states.
 */
export default function ProductBoundary() {
  return (
    <aside
      aria-label="产品层级与研究边界 / Product hierarchy and research limits"
      className="border-b border-indigo-100 bg-indigo-50/70 dark:border-indigo-950 dark:bg-indigo-950/30"
      data-testid="phase-product-boundary"
    >
      <div className="mx-auto flex min-h-[52px] max-w-7xl items-center justify-between gap-3 px-4 py-1 text-[11px] text-zinc-700 xl:hidden dark:text-zinc-300">
        <p className="min-w-0 leading-4">
          <strong className="font-semibold text-zinc-900 dark:text-white">Phase</strong>
          ：冻结快照 · NULL 回测 · 无预测能力
        </p>
        <a
          href={MAIN_PRODUCT_URL}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="返回 Structural 主产品 / Back to main product（新标签页）"
          className="inline-flex min-h-11 shrink-0 items-center rounded-md bg-zinc-900 px-3 py-2 font-semibold text-white hover:bg-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700 dark:bg-white dark:text-zinc-950"
          data-testid="phase-main-product-return-mobile"
        >
          返回主产品 ↗
        </a>
      </div>
      <div className="mx-auto hidden max-w-7xl items-center justify-between gap-4 px-6 py-3 text-xs text-zinc-700 xl:flex dark:text-zinc-300">
        <p className="max-w-3xl leading-5">
          <strong className="font-semibold text-zinc-900 dark:text-white">
            Structural Labs · Phase
          </strong>{" "}
          是冻结的公司结构研究子产品 / is a frozen company-structure research subproduct.
          597 个 demo ticker、公开 NULL 回测，不提供预测能力 / 597 demo tickers,
          published NULL backtest, no predictive capability.
        </p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <a
            href="/methodology"
            className="inline-flex min-h-11 items-center font-medium text-zinc-700 underline decoration-zinc-300 underline-offset-4 hover:text-zinc-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700 dark:text-zinc-300 dark:hover:text-white"
          >
            方法与来源 / Methods &amp; sources
          </a>
          <a
            href={MAIN_PRODUCT_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center rounded-md bg-zinc-900 px-3 py-2 font-semibold text-white hover:bg-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700 dark:bg-white dark:text-zinc-950"
            data-testid="phase-main-product-return"
          >
            返回 Structural 主产品 / Back to main product ↗
          </a>
        </div>
      </div>
    </aside>
  );
}
