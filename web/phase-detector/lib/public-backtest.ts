import result from "@/public/backtest/result.json";

/** Canonical public NULL-backtest result, derived from the published artifact. */
export const PUBLIC_BACKTEST_P_VALUE = result.p_value;
export const PUBLIC_BACKTEST_P_LABEL = PUBLIC_BACKTEST_P_VALUE.toFixed(10);
