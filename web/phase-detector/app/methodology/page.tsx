import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumb } from "@/components/Breadcrumb";
import { PageOpenTracker } from "@/components/PageOpenTracker";
import {
  CPS_EXPLAIN,
  CPS_ICON,
  CPS_LABEL_ZH,
  CPS_OPTIONS,
  DYNAMICS_EXPLAIN,
  DYNAMICS_FAMILY_OPTIONS,
  DYNAMICS_LABEL_ZH,
} from "@/lib/labels";

export const metadata: Metadata = {
  title: "方法 — Phase Detector",
  description:
    "Phase Detector 怎么打分：每家公司归入哪一类、当前在哪个状态、AI 怎么从公开资料里读出来。",
};

const cpsColor = (s: string) =>
  s === "far_from_critical"
    ? "#059669"
    : s === "approaching_critical"
      ? "#D97706"
      : s === "at_critical"
        ? "#DC2626"
        : s === "post_critical_transition"
          ? "#18181B"
          : "#71717A";

export default function MethodologyPage() {
  return (
    <article className="mx-auto max-w-3xl">
      <PageOpenTracker event="methodology_opened" />
      <Breadcrumb
        items={[{ label: "首页", href: "/" }, { label: "方法" }]}
      />

      <h1
        className="serif mb-3 text-3xl font-semibold tracking-tight text-zinc-900 md:text-4xl"
        style={{ fontFamily: "'Noto Serif SC', serif" }}
      >
        方法论
      </h1>
      <p className="mb-8 text-base leading-relaxed text-zinc-600">
        我们给每家公司打两个标签：它属于哪一类共享模式、它现在处在哪个状态。
        下面解释这两个标签怎么来。
      </p>

      {/* What we record per company */}
      <section className="mb-10">
        <h2 className="mb-3 text-xl font-semibold text-zinc-900">
          1. 每家公司记下什么
        </h2>
        <p className="mb-3 text-sm leading-relaxed text-zinc-600">
          我们把每家公司压成一张结构化卡片，包含下面这些字段：
        </p>
        <ul className="space-y-2 rounded-lg border border-zinc-200 bg-white p-4 text-sm">
          <li>
            <strong className="text-zinc-900">共享模式</strong>{" "}
            — 它"怎么动"（5 选 1）
          </li>
          <li>
            <strong className="text-zinc-900">当前状态</strong>{" "}
            — 它现在在哪个阶段（4 选 1）
          </li>
          <li>
            <strong className="text-zinc-900">主要指标</strong>{" "}
            — 支持该判断的关键数据
          </li>
          <li>
            <strong className="text-zinc-900">30 秒一句话总结</strong> —
            说人话的当前定性
          </li>
          <li>
            <strong className="text-zinc-900">置信度</strong>{" "}
            — AI 自报的把握程度（0–1）
          </li>
          <li>
            <strong className="text-zinc-900">注意事项</strong> —
            已知的不确定性、数据缺口
          </li>
        </ul>
        <p className="mt-3 text-xs text-zinc-500">
          完整字段定义见{" "}
          <a
            href="https://github.com/dada8899/structural-isomorphism"
            target="_blank"
            rel="noopener"
            className="text-blue-600 hover:underline"
          >
            GitHub repo ↗
          </a>
          。
        </p>
      </section>

      {/* Five shared patterns */}
      <section className="mb-10">
        <h2 className="mb-3 text-xl font-semibold text-zinc-900">
          2. 9 类共享模式
        </h2>
        <p className="mb-4 text-sm leading-relaxed text-zinc-600">
          我们把公司按"怎么动"归为下面 9 类。这套分类来自跨学科研究——
          地震、神经网络、电网、生态、金融市场都被这套模式解释过。
        </p>
        <div className="space-y-3">
          {DYNAMICS_FAMILY_OPTIONS.map((f) => (
            <div
              key={f}
              className="rounded-lg border border-zinc-200 bg-white p-4"
            >
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-sm font-semibold text-zinc-900">
                  {DYNAMICS_LABEL_ZH[f]}
                </span>
              </div>
              <p className="text-sm leading-relaxed text-zinc-600">
                {DYNAMICS_EXPLAIN[f]}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Four current states */}
      <section className="mb-10">
        <h2 className="mb-3 text-xl font-semibold text-zinc-900">
          3. 5 种当前状态
        </h2>
        <p className="mb-4 text-sm leading-relaxed text-zinc-600">
          每家公司离它的"翻车点"有多远？我们用下面 5 个状态描述（含证据不足时标记的"未知"）。
          每个状态用一个独特图标 + 颜色 + 文字（颜色不是唯一识别方式，色盲也能用）。
        </p>
        <div className="space-y-3">
          {CPS_OPTIONS.map((s) => (
            <div
              key={s}
              className="flex gap-4 rounded-lg border border-zinc-200 bg-white p-4"
            >
              <span
                aria-hidden="true"
                className="select-none text-3xl leading-none"
                style={{ color: cpsColor(s) }}
              >
                {CPS_ICON[s]}
              </span>
              <div>
                <div className="text-sm font-semibold text-zinc-900">
                  {CPS_LABEL_ZH[s]}
                </div>
                <p className="mt-0.5 text-sm leading-relaxed text-zinc-600">
                  {CPS_EXPLAIN[s]}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Pipeline (PR-1: collapsed numbered pipeline to a single paragraph) */}
      <section className="mb-10">
        <h2 className="mb-3 text-xl font-semibold text-zinc-900">
          4. 数据怎么来
        </h2>
        <p className="text-sm leading-relaxed text-zinc-600">
          我们抓取每家公司公开的年报、业绩说明、行业研报，用多个主流 AI 模型读，
          填出上面那张结构化卡片。每个判断由 3 个独立的"审稿 AI"投票，
          多数同意才入库；同行业里业务相近的公司不应该得到差别极大的判断，
          我们也会扫一遍。最终结果附带不确定性说明。
        </p>
      </section>

      {/* Limitations */}
      <section className="mb-10">
        <h2 className="mb-3 text-xl font-semibold text-zinc-900">
          5. 哪些做不到
        </h2>
        <ul className="ml-5 list-disc space-y-1 text-sm text-zinc-600">
          <li>覆盖：当前 100 家公司，长尾尚未覆盖</li>
          <li>频率：每周更新一次，盘中突发事件不会立刻反映</li>
          <li>
            模型偏差：AI 可能漏读或读错，请看每家公司卡片下的"注意事项"
          </li>
          <li>
            结构判断 ≠ 价格预测：当前状态描述的是结构性风险，不是短期涨跌信号
          </li>
        </ul>
      </section>

      <section className="rounded-xl border border-zinc-200 bg-zinc-50 p-5">
        <h3 className="mb-2 text-sm font-semibold text-zinc-900">
          深入阅读
        </h3>
        <ul className="space-y-1 text-sm">
          <li>
            <a
              href="https://beta.structural.bytedance.city/classes"
              className="text-blue-600 hover:underline"
            >
              主站：跨学科同构研究报告 ↗
            </a>
          </li>
          <li>
            <a
              href="https://github.com/dada8899/structural-isomorphism"
              target="_blank"
              rel="noopener"
              className="text-blue-600 hover:underline"
            >
              GitHub Repo ↗
            </a>
          </li>
          <li>
            <Link
              href="/about"
              className="text-blue-600 hover:underline"
            >
              关于本站
            </Link>
          </li>
          <li>
            <Link href="/" className="text-blue-600 hover:underline">
              回到公司表
            </Link>
          </li>
        </ul>
      </section>
    </article>
  );
}
