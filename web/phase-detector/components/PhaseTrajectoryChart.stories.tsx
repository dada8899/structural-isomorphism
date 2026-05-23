import type { Meta, StoryObj } from "@storybook/react";
import { PhaseTrajectoryChart } from "./PhaseTrajectoryChart";
import { MOCK_EWS_DETAIL } from "../lib/mock-data";

/**
 * **PhaseTrajectoryChart** — dual-axis line chart for the company detail
 * page. Plots rolling lag-1 autocorrelation (AR1) on the left axis and
 * rolling variance on the right. Trailing Kendall-tau is shown in the
 * legend; both rising = textbook critical-slowing-down warning.
 *
 * 2026-05-23 PD-EWS rewrite: replaces the previous PRNG-synthesized
 * trajectory with the real EWS series produced by
 * `v4/product/d1_phase_detector/ews.py`.
 */
const meta: Meta<typeof PhaseTrajectoryChart> = {
  title: "Visualization/PhaseTrajectoryChart",
  component: PhaseTrajectoryChart,
  parameters: {
    docs: {
      description: {
        component:
          "Real CSD (critical slowing down) signal: rolling AR1 + variance " +
          "of daily log-returns over the trailing year. Both rising together " +
          "is the warning; lone movers are capped at 'yellow' by design.",
      },
    },
    layout: "padded",
  },
};

export default meta;
type Story = StoryObj<typeof PhaseTrajectoryChart>;

export const NvdaAtCritical: Story = {
  args: { ewsDetail: MOCK_EWS_DETAIL["NVDA"], ticker: "NVDA" },
};

export const TslaAtCritical: Story = {
  args: { ewsDetail: MOCK_EWS_DETAIL["TSLA"], ticker: "TSLA" },
};

export const AaplCalm: Story = {
  args: { ewsDetail: MOCK_EWS_DETAIL["AAPL"], ticker: "AAPL" },
};

export const IntcPost: Story = {
  args: { ewsDetail: MOCK_EWS_DETAIL["INTC"], ticker: "INTC" },
  parameters: {
    docs: {
      description: { story: "已翻转 — 尾部窗口内大幅回撤触发 post_critical_transition。" },
    },
  },
};

export const TencentHk: Story = {
  args: { ewsDetail: MOCK_EWS_DETAIL["0700.HK"], ticker: "0700.HK" },
  parameters: {
    docs: {
      description: { story: "港股例子（腾讯 00700.HK），EWS 引擎对港股 ticker 直通。" },
    },
  },
};

export const MeituanHk: Story = {
  args: { ewsDetail: MOCK_EWS_DETAIL["3690.HK"], ticker: "3690.HK" },
};

export const EmptyState: Story = {
  args: { ewsDetail: null, ticker: "WAIT.US" },
  parameters: {
    docs: {
      description: {
        story:
          "Empty state for tickers not yet ingested by the nightly pipeline. " +
          "Replaces the old PRNG-fake fallback with an honest 'data refreshing' notice.",
      },
    },
  },
};
