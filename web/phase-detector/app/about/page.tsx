import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumb } from "@/components/Breadcrumb";
import { PageOpenTracker } from "@/components/PageOpenTracker";

export const metadata: Metadata = {
  title: "关于 — Phase Detector",
  description:
    "Phase Detector 用同一套数学，从地震、银行挤兑等场景延伸到上市公司——每家给一个状态评分。研究预览，不是投资建议。",
};

export default function AboutPage() {
  return (
    <article className="mx-auto max-w-3xl">
      <PageOpenTracker event="about_opened" />
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
        研究项目的子产品。我们把同一套用来解释
        <strong className="text-zinc-900">地震、银行挤兑、电网瘫痪</strong>
        的数学，套到上市公司上：谁正
        <strong className="text-zinc-900">接近翻车点</strong>？谁已经
        <strong className="text-zinc-900">翻完面回不去了</strong>？
      </p>

      <section className="mb-8 space-y-3">
        <h2 className="text-xl font-semibold text-zinc-900">数据怎么来</h2>
        <p className="text-sm leading-relaxed text-zinc-600">
          当前覆盖 100 家上市公司（NYSE + NASDAQ 大盘 +
          部分中小盘代表）。我们读取每家公司的年报、业绩说明、行业研报，
          用主流大模型抽取关键结构，再由几个独立的审稿 AI
          交叉检查后入库。
        </p>
        <ul className="ml-5 list-disc space-y-1 text-sm text-zinc-600">
          <li>抽取：主流大模型，长上下文读取全文</li>
          <li>审稿：多个独立 AI 模型投票，多数同意才入库</li>
          <li>更新：每周一次（未来扩到每日）</li>
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
          <em>看似无关的现象，在数学结构层面往往是同一件事</em>。
          我们在 13 个独立领域跑了同一套代码（地震、神经放电、DeFi 清算、
          湖泊富营养化、高速公路堵车等），用同一套
          <Link
            href="https://structural.bytedance.city"
            className="text-blue-600 hover:underline"
          >
            {" "}研究报告{" "}
          </Link>
          一并发布。
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
            打开公司表 →
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
