import type { Company, EwsResultFull } from "./types";

export function companyFromEws(e: EwsResultFull): Company {
  return {
    ticker: e.ticker,
    name: e.name || e.ticker,
    sector: e.sector ?? "unknown",
    industry: null,
    market_cap_usd_b: null,
    dynamics_family:
      (e.llm_dynamics_family as Company["dynamics_family"]) ?? "mixed_or_unclear",
    critical_point_state: e.phase_state,
    universality_class: null,
    extraction_confidence: e.confidence ?? 0,
    extraction_model: "ews_engine",
    extracted_at: e.as_of ?? null,
    tldr:
      e.llm_tldr ??
      "本 ticker 暂无 LLM 叙述；以下为 EWS 信号读出，数据来源以页面 provenance 标记为准。",
    primary_indicators: null,
    caveats: e.notes ?? null,
  };
}
