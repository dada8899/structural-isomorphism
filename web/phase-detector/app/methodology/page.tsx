import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumb } from "@/components/Breadcrumb";
import {
  CPS_EXPLAIN,
  CPS_ICON,
  CPS_LABEL,
  CPS_OPTIONS,
  DYNAMICS_EXPLAIN,
  DYNAMICS_FAMILY_OPTIONS,
  DYNAMICS_LABEL,
} from "@/lib/labels";

export const metadata: Metadata = {
  title: "方法 — Phase Detector",
  description:
    "Phase Detector 的方法论：StructTuple schema、动力学族分类、临界点状态判定、LLM 抽取 pipeline。",
};

const cpsColor = (s: string) =>
  s === "subcritical"
    ? "#059669"
    : s === "near_critical"
      ? "#D97706"
      : s === "supercritical"
        ? "#DC2626"
        : "#18181B";

export default function MethodologyPage() {
  return (
    <article className="mx-auto max-w-3xl">
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
        Phase Detector 的每个标签都来自一套
        <strong className="text-zinc-900">明确的数学分类</strong>。本页解释
        StructTuple schema、5 个动力学族、4 个临界点状态、以及 LLM
        抽取 pipeline。
      </p>

      {/* StructTuple schema */}
      <section className="mb-10">
        <h2 className="mb-3 text-xl font-semibold text-zinc-900">
          1. StructTuple Schema
        </h2>
        <p className="mb-3 text-sm leading-relaxed text-zinc-600">
          每家公司被抽象为一个
          <code className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-xs">
            StructTuple
          </code>
          ，包含以下核心字段（v0.2）：
        </p>
        <ul className="space-y-2 rounded-lg border border-zinc-200 bg-white p-4 text-sm">
          <li>
            <code className="font-mono text-xs text-blue-700">dynamics_family</code>{" "}
            — 动力学族（5 选 1）
          </li>
          <li>
            <code className="font-mono text-xs text-blue-700">
              critical_point_state
            </code>{" "}
            — 临界点状态（4 选 1）
          </li>
          <li>
            <code className="font-mono text-xs text-blue-700">primary_indicators</code>{" "}
            — 决定该判断的关键指标 + 数值
          </li>
          <li>
            <code className="font-mono text-xs text-blue-700">tldr</code> —
            30 秒人话总结
          </li>
          <li>
            <code className="font-mono text-xs text-blue-700">confidence</code>{" "}
            — 抽取置信度（0-1）
          </li>
          <li>
            <code className="font-mono text-xs text-blue-700">caveats</code> —
            已知的不确定性 / 数据缺口
          </li>
        </ul>
        <p className="mt-3 text-xs text-zinc-500">
          完整 schema 见{" "}
          <a
            href="https://github.com/dada8899/structural-isomorphism/blob/main/docs/struct-tuple-v0.2.md"
            target="_blank"
            rel="noopener"
            className="text-blue-600 hover:underline"
          >
            GitHub repo ↗
          </a>
          。
        </p>
      </section>

      {/* Dynamics families */}
      <section className="mb-10">
        <h2 className="mb-3 text-xl font-semibold text-zinc-900">
          2. 5 个动力学族
        </h2>
        <p className="mb-4 text-sm leading-relaxed text-zinc-600">
          基于 Structural Isomorphism C1 unified preprint
          中验证过的 5 个普适类。每个族描述一种「结构性放大 / 切换 / 长尾」机制。
        </p>
        <div className="space-y-3">
          {DYNAMICS_FAMILY_OPTIONS.map((f) => (
            <div
              key={f}
              className="rounded-lg border border-zinc-200 bg-white p-4"
            >
              <div className="mb-1 flex items-baseline gap-2">
                <span className="font-mono text-xs text-blue-700">{f}</span>
                <span className="text-sm font-semibold text-zinc-900">
                  {DYNAMICS_LABEL[f]}
                </span>
              </div>
              <p className="text-sm leading-relaxed text-zinc-600">
                {DYNAMICS_EXPLAIN[f]}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* CPS states */}
      <section className="mb-10">
        <h2 className="mb-3 text-xl font-semibold text-zinc-900">
          3. 4 个临界点状态
        </h2>
        <p className="mb-4 text-sm leading-relaxed text-zinc-600">
          一个动力学系统相对其
          <strong className="text-zinc-900">临界点</strong>
          可以处于以下 4 种状态。每个状态用唯一的图标 + 颜色 + 文字标识
          （WCAG 1.4.1 三重冗余）。
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
                  {CPS_LABEL[s]}{" "}
                  <span className="ml-1 font-mono text-xs text-zinc-400">
                    {s}
                  </span>
                </div>
                <p className="mt-0.5 text-sm leading-relaxed text-zinc-600">
                  {CPS_EXPLAIN[s]}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Pipeline */}
      <section className="mb-10">
        <h2 className="mb-3 text-xl font-semibold text-zinc-900">
          4. LLM 抽取 Pipeline
        </h2>
        <ol className="space-y-2 text-sm leading-relaxed text-zinc-600">
          <li>
            <strong className="text-zinc-900">01 文档收集</strong>：抓取
            10-K + 业绩说明会 + 行业研报（每家约 3-5 份文档）
          </li>
          <li>
            <strong className="text-zinc-900">02 LLM 抽取</strong>：用
            DeepSeek v4-pro（1M 上下文）填入 StructTuple，
            含主要指标和置信度
          </li>
          <li>
            <strong className="text-zinc-900">03 Reviewer 评审</strong>：B3
            ensemble taxonomy reviewer × 3 投票，多数同意才入库
          </li>
          <li>
            <strong className="text-zinc-900">04 Cross-check</strong>
            ：跨公司一致性扫描（同行业相似业务的公司不应得到极端不同的判断）
          </li>
          <li>
            <strong className="text-zinc-900">05 入库</strong>：写入
            screener API，附带 caveats（数据缺口、模型局限）
          </li>
        </ol>
      </section>

      {/* Limitations */}
      <section className="mb-10">
        <h2 className="mb-3 text-xl font-semibold text-zinc-900">
          5. 局限性
        </h2>
        <ul className="ml-5 list-disc space-y-1 text-sm text-zinc-600">
          <li>覆盖范围：当前 100 家公司，长尾未覆盖</li>
          <li>更新频率：每周一次，盘中突发事件不会即时反映</li>
          <li>
            模型偏差：DeepSeek 抽取可能漏抽 / 错抽，请参考 caveats 字段
          </li>
          <li>
            结构判断 ≠ 价格预测：临界点状态描述结构性风险，不是短期价格信号
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
              href="https://structural.bytedance.city/paper/unified-pipeline-v0.2-2026-05-13"
              className="text-blue-600 hover:underline"
            >
              C1 Unified Preprint v0.2 (2026-05-13) — 13 系统统一 pipeline ↗
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
              返回筛选器
            </Link>
          </li>
        </ul>
      </section>
    </article>
  );
}
