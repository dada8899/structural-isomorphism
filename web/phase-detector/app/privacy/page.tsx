// W14-C (session #10, 2026-05-15): privacy policy SSR page.
//
// Mirrors docs/privacy-policy.md but rendered as a first-class Next.js route
// so search engines + linked-from-footer "Privacy" link land somewhere with
// real content (vs. a raw .md served from the docs server).
//
// Why hand-written JSX instead of MDX:
//   • We update this page rarely (legal/compliance, not product).
//   • Avoids pulling in another build dep (next-mdx-remote) for one page.
//   • The .md version stays canonical for diffs; this page references it.
import type { Metadata } from "next";
import Link from "next/link";
import ManageCookiesButton from "@/components/ManageCookiesButton";

export const metadata: Metadata = {
  title: "隐私政策 — Phase Detector",
  description:
    "Phase Detector 隐私政策：我们收集什么、为什么、保留多久、你有什么权利。",
  alternates: { canonical: "https://phase.bytedance.city/privacy" },
};

export default function PrivacyPage() {
  return (
    <article className="prose prose-zinc mx-auto max-w-3xl px-6 py-10 dark:prose-invert">
      <h1>隐私政策</h1>
      <p className="text-sm text-zinc-500">最后更新：2026-05-15</p>

      <p>
        本页是 <strong>Structural Isomorphism</strong> 研究项目相关站点的简明隐私
        说明（{" "}
        <code>structural.bytedance.city</code>、
        <code>phase.bytedance.city</code>、
        <code>beta.structural.bytedance.city</code>）。如有问题或希望删除你的数据，请发邮件至{" "}
        <a href="mailto:riazward110@gmail.com">riazward110@gmail.com</a>。
      </p>

      <h2>我们收集什么</h2>
      <p>仅在获得你同意（或属于站点正常运行所必需）时收集以下数据：</p>
      <ul>
        <li>
          <strong>会话 ID</strong>（本地随机生成，存于 localStorage）—— 用于在
          页面崩溃时把错误日志归到同一次浏览。不绑定身份。
        </li>
        <li>
          <strong>错误报告</strong>（前端崩溃时） —— 错误消息、堆栈、URL（已去除
          查询参数）、User-Agent、时间戳、会话 ID。详见{" "}
          <code>web/backend/api/error_log.py</code>。
        </li>
        <li>
          <strong>邮件订阅</strong>（如果你主动填写） —— 邮箱、来源页面、提交
          时间。
        </li>
        <li>
          <strong>Mock checkout</strong>（如果你在定价页提交虚拟支付）—— 邮箱、
          姓名、卡号末 4 位、所选 tier。仅用于评估付费意愿，不会真实扣款。
        </li>
        <li>
          <strong>分析数据</strong>（仅在你勾选同意后启用）—— Plausible 自托管、
          无 cookie、不存原始 IP、不做跨站追踪。
        </li>
      </ul>

      <h2>为什么收集</h2>
      <ul>
        <li>调试 —— 错误报告帮助我们快速定位前端崩溃</li>
        <li>留存 —— 邮件订阅让你能收到我们的研究更新</li>
        <li>商业准备 —— mock checkout 用来评估 PMF（产品市场契合度）</li>
        <li>改进 —— 分析数据告诉我们哪些页面被使用、被忽视</li>
      </ul>

      <h2>保留多久</h2>
      <ul>
        <li>错误日志：<strong>90 天</strong>，到期后滚动覆盖（详见 error_log.jsonl 的轮转策略）</li>
        <li>邮件订阅：<strong>直到你退订</strong>（每封邮件底部有一键退订链接）</li>
        <li>Mock checkout 记录：<strong>无限期</strong>，作为商业化数据保留；可应申请删除</li>
        <li>Nginx 访问日志：<strong>14 天</strong>，仅用于安全与运维诊断</li>
        <li>Plausible 分析数据：<strong>聚合后无限期</strong>，原始 IP 从不写入磁盘</li>
      </ul>

      <h2>第三方</h2>
      <ul>
        <li>
          <strong>Plausible Analytics</strong>（自托管，隐私友好，无 cookie）——
          见{" "}
          <a
            href="https://plausible.io/data-policy"
            target="_blank"
            rel="noopener noreferrer"
          >
            数据政策
          </a>
          。
        </li>
        <li>
          <strong>Google Fonts</strong>（CDN 字体）—— 在加载字体时会向 Google
          发送请求。
        </li>
        <li>
          <strong>jsDelivr</strong>（KaTeX / Marked.js 等 CDN）——
          可能在 CDN 层记录请求。
        </li>
      </ul>
      <p>
        我们 <strong>不使用</strong> Google Analytics、Facebook Pixel、广告网络、
        会话录制工具。
      </p>

      <h2>你的权利（GDPR / 类似法规）</h2>
      <p>无论你身处何地，你都享有以下权利：</p>
      <ul>
        <li>
          <strong>访问 / 导出</strong>：调用{" "}
          <code>GET /api/privacy/export?email=...</code> 获取我们存储的与你相关
          的所有数据（需邮箱验证）。
        </li>
        <li>
          <strong>删除</strong>：调用{" "}
          <code>DELETE /api/privacy/delete?email=...</code> 删除所有相关记录
          （审计日志会保留删除请求本身，用于合规追踪）。
        </li>
        <li>
          <strong>反对</strong>：你可以拒绝分析 cookie。开启浏览器的 DNT（Do Not
          Track）也会自动关闭分析。
        </li>
        <li>
          <strong>更正</strong>：发邮件告诉我们错误，我们会在 7 天内修正。
        </li>
      </ul>

      <h2>Cookie 与本地存储</h2>
      <p>
        本站使用 localStorage（不是 cookie）存储以下技术状态：主题偏好、
        cookie 同意选择、错误报告会话 ID、新手引导是否已看过。Plausible
        分析<strong>仅在你勾选同意</strong>后加载，且本身不使用 cookie。
      </p>
      <p>
        要修改你的 cookie 偏好，请点击下面的按钮（或任意页面底部 footer 的
        「管理 cookie」链接）：
      </p>
      <p>
        <ManageCookiesButton />
      </p>

      <h2>隐私问题联系方式</h2>
      <p>
        邮件：
        <a href="mailto:riazward110@gmail.com">riazward110@gmail.com</a>
        。本项目为非商业研究项目，没有公司实体，数据控制人即项目维护者。
      </p>

      <hr />
      <p className="text-xs text-zinc-500">
        本页与{" "}
        <Link href="https://github.com/dada8899/structural-isomorphism/blob/main/docs/privacy-policy.md">
          docs/privacy-policy.md
        </Link>{" "}
        同步维护。如二者描述不一致，以本页（更晚更新）为准。
      </p>
    </article>
  );
}
