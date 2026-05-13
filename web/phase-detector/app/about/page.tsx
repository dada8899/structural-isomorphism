import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumb } from "@/components/Breadcrumb";

export const metadata: Metadata = {
  title: "关于 — Phase Detector",
  description:
    "Phase Detector 是 Structural Isomorphism 的子产品。用 LLM 抽取 100 家公司的结构动力学族 + 临界点状态。研究预览，非投资建议。",
};

export default function AboutPage() {
  return (
    <article className="mx-auto max-w-3xl">
      <Breadcrumb
        items={[{ label: "首页", href: "/" }, { label: "关于" }]}
      />

      <h1
        className="serif mb-3 text-3xl font-semibold tracking-tight text-zinc-900 md:text-4xl"
        style={{ fontFamily: "'Noto Serif SC', serif" }}
      >
        关于 Phase Detector
      </h1>
      <p className="mb-8 text-base leading-relaxed text-zinc-600">
        Phase Detector 是
        <a
          href="https://structural.bytedance.city"
          target="_blank"
          rel="noopener"
          className="text-blue-600 hover:underline"
        >
          {" "}Structural Isomorphism{" "}
        </a>
        研究项目的子产品（代号 D1）。我们把同一套
        <strong className="text-zinc-900">结构动力学分类</strong>
        应用到金融/商业领域：哪些公司处于
        <strong className="text-zinc-900">临界点附近</strong>？哪些
        已经
        <strong className="text-zinc-900">完成相变</strong>？
      </p>

      <section className="mb-8 space-y-3">
        <h2 className="text-xl font-semibold text-zinc-900">数据来源</h2>
        <p className="text-sm leading-relaxed text-zinc-600">
          当前覆盖 100 家上市公司（NYSE + NASDAQ 大盘 +
          部分中小盘代表）。每家公司的 StructTuple 由 LLM 从其
          10-K 报告 / 业绩说明 / 行业研报中
          <strong>抽取</strong>，再由独立的 reviewer agent
          交叉检查后入库。
        </p>
        <ul className="ml-5 list-disc space-y-1 text-sm text-zinc-600">
          <li>抽取模型：DeepSeek v4-pro（1M 上下文，2026-05-06 切换）</li>
          <li>Schema：StructTuple v0.2（参考 C1 unified preprint）</li>
          <li>评审：B3 ensemble taxonomy reviewer × 3 投票</li>
          <li>数据更新：每周一次（roadmap 中将扩到每日）</li>
        </ul>
      </section>

      <section className="mb-8 space-y-3">
        <h2 className="text-xl font-semibold text-zinc-900">
          这不是投资建议
        </h2>
        <p className="text-sm leading-relaxed text-zinc-600">
          Phase Detector 是
          <strong>研究预览</strong>。所有
          TL;DR、临界点状态、置信度都由 LLM 给出，可能包含错误、过期信息、
          或抽取偏差。
        </p>
        <p className="text-sm leading-relaxed text-zinc-600">
          <strong className="text-red-700">使用须知：</strong>
          请把它当作「跨学科结构同构」的研究工具，
          <strong>不是</strong>投资建议。每条结论请独立核实底层数据；
          对涉及金钱决策的判断请咨询持牌专业人士。
        </p>
      </section>

      <section className="mb-8 space-y-3">
        <h2 className="text-xl font-semibold text-zinc-900">
          学术背景
        </h2>
        <p className="text-sm leading-relaxed text-zinc-600">
          Phase Detector 基于 Structural Isomorphism 项目的核心假设：
          <em>看似无关的现象，在数学结构层面往往同构</em>。该假设已在
          13 个独立系统（地震、神经雪崩、DeFi 清算、湖泊富营养化、
          高速公路相变等）的
          <Link
            href="https://structural.bytedance.city/paper/unified-pipeline-v0.2-2026-05-13"
            className="text-blue-600 hover:underline"
          >
            {" "}339 行统一 pipeline{" "}
          </Link>
          上验证（v0.2 预印本，2026-05-13）。
        </p>
      </section>

      <section className="mb-8 space-y-3">
        <h2 className="text-xl font-semibold text-zinc-900">
          联系 / 反馈
        </h2>
        <ul className="space-y-1 text-sm text-zinc-600">
          <li>
            GitHub：
            <a
              href="https://github.com/dada8899/structural-isomorphism"
              target="_blank"
              rel="noopener"
              className="text-blue-600 hover:underline"
            >
              dada8899/structural-isomorphism ↗
            </a>
          </li>
          <li>
            主站：
            <a
              href="https://structural.bytedance.city"
              target="_blank"
              rel="noopener"
              className="text-blue-600 hover:underline"
            >
              structural.bytedance.city ↗
            </a>
          </li>
          <li>反馈/建议：欢迎在 GitHub 开 issue</li>
        </ul>
      </section>

      <section className="rounded-xl border border-zinc-200 bg-zinc-50 p-5">
        <h3 className="mb-2 text-sm font-semibold text-zinc-900">
          继续探索
        </h3>
        <div className="flex flex-wrap gap-3 text-sm">
          <Link
            href="/methodology"
            className="text-blue-600 hover:underline"
          >
            方法论详解 →
          </Link>
          <Link href="/" className="text-blue-600 hover:underline">
            打开筛选器 →
          </Link>
          <a
            href="https://structural.bytedance.city"
            target="_blank"
            rel="noopener"
            className="text-blue-600 hover:underline"
          >
            访问主站 ↗
          </a>
        </div>
      </section>
    </article>
  );
}
