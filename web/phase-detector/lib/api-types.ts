/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

/**
 * `answer_done` event payload. `out_of_scope=true` means the
 * retrieval relevance gate failed — frontend should soften the UI.
 */
export interface AnswerDone {
  text: string;
  out_of_scope?: boolean;
  scope_reason?: string | null;
  citations?: string[];
}
/**
 * First SSE event from /api/ask/stream — echoes the rewritten query
 * and the planned downstream steps. Frontend renders this as the
 * 'thinking about: <query>' line.
 */
export interface AskMeta {
  rewritten: string;
  steps?: string[];
}
/**
 * Body for POST /api/ask/stream — Perplexity-like SSE endpoint.
 */
export interface AskRequest {
  query: string;
  lang?: "zh" | "en";
}
export interface AssessRequest {
  query: string;
  lang?: string;
}
/**
 * A bounded hypothesis contract; never a verified-isomorphism claim.
 */
export interface CandidateMapping {
  schema_version: "candidate-mapping-v2";
  evidence_level: "candidate";
  generation_status: "generated" | "fallback";
  structure_name: string;
  formula?: string;
  candidate_rationale: string;
  /**
   * @maxItems 8
   */
  parameter_mapping?:
    | []
    | [MappingParameter]
    | [MappingParameter, MappingParameter]
    | [MappingParameter, MappingParameter, MappingParameter]
    | [MappingParameter, MappingParameter, MappingParameter, MappingParameter]
    | [MappingParameter, MappingParameter, MappingParameter, MappingParameter, MappingParameter]
    | [MappingParameter, MappingParameter, MappingParameter, MappingParameter, MappingParameter, MappingParameter]
    | [
        MappingParameter,
        MappingParameter,
        MappingParameter,
        MappingParameter,
        MappingParameter,
        MappingParameter,
        MappingParameter
      ]
    | [
        MappingParameter,
        MappingParameter,
        MappingParameter,
        MappingParameter,
        MappingParameter,
        MappingParameter,
        MappingParameter,
        MappingParameter
      ];
  /**
   * @minItems 1
   * @maxItems 5
   */
  validation_suggestions:
    | [MappingValidationSuggestion]
    | [MappingValidationSuggestion, MappingValidationSuggestion]
    | [MappingValidationSuggestion, MappingValidationSuggestion, MappingValidationSuggestion]
    | [
        MappingValidationSuggestion,
        MappingValidationSuggestion,
        MappingValidationSuggestion,
        MappingValidationSuggestion
      ]
    | [
        MappingValidationSuggestion,
        MappingValidationSuggestion,
        MappingValidationSuggestion,
        MappingValidationSuggestion,
        MappingValidationSuggestion
      ];
  /**
   * @minItems 1
   * @maxItems 5
   */
  alternative_explanations:
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string];
  /**
   * @minItems 1
   * @maxItems 5
   */
  failure_conditions:
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string];
  why_worth_testing: string;
}
export interface MappingParameter {
  a_term: string;
  a_symbol?: string;
  b_term: string;
  b_symbol?: string;
  note: string;
}
export interface MappingValidationSuggestion {
  title: string;
  description: string;
  scenario: string;
  failure_signal: string;
}
export interface CatalogOrigin {
  kind: "kb_record";
  artifact_id: string;
  record_id: string;
  record_digest: string;
}
/**
 * Legacy development simulator input.
 *
 * Production returns HTTP 410 before recording any submitted fields.
 */
export interface CheckoutBody {
  tier: string;
  interval?: string;
  email: string;
  name?: string | null;
  card_last4?: string | null;
  force_status?: string | null;
}
/**
 * Legacy development-only simulator response.
 *
 * Production returns HTTP 410 and has no checkout or paid entitlement.
 * This type must not be treated as a current billing contract.
 */
export interface CheckoutResponse {
  status: "success" | "declined";
  reason?: "card_declined" | null;
  customer_id?: string | null;
  checkout_session_id?: string | null;
  tier?: ("pro" | "team") | null;
  interval?: ("month" | "year") | null;
  amount_usd?: number | null;
}
export interface CompaniesResponse {
  items?: Company[];
  total?: number;
}
/**
 * A single company row in the screener. Mirrors the inline
 * `Company` shape from `web/phase-detector/lib/types.ts` — listed here
 * so the generated TS file owns the canonical shape.
 */
export interface Company {
  ticker: string;
  name: string;
  sector: string;
  dynamics_family: string;
  critical_point_state: string;
  extraction_confidence: number;
  signals?: string[];
}
/**
 * Cookie-consent record persisted on the client + mirrored on the
 * server when the user opts in. W14-C surface model.
 */
export interface CookieConsent {
  necessary?: boolean;
  analytics?: boolean;
  marketing?: boolean;
  timestamp?: number | null;
}
/**
 * GET /api/daily — a strict preview of the public candidate queue.
 */
export interface DailyResponse {
  date: string;
  lang: "zh" | "en";
  /**
   * @minItems 3
   * @maxItems 3
   */
  discoveries: [DiscoveryCandidate, DiscoveryCandidate, DiscoveryCandidate];
}
export interface DiscoveryCandidate {
  schema_version: "discovery-candidate-v2";
  discovery_id: string;
  candidate_family_id: string;
  family_variant_count: number;
  rank: number;
  tier: "priority_review" | "candidate_pool";
  pipeline?: ("V2" | "V3") | null;
  pair: DiscoveryPair;
  candidate_summary: LocalizedDiscoveryText;
  candidate_equations?: string[];
  candidate_variable_mapping?: {
    [k: string]: string;
  };
  evidence_language: "zh_only" | "not_recorded";
  provenance: DiscoveryProvenance;
  readiness: DiscoveryReadiness;
  validation_plan: DiscoveryValidationPlan;
  analyze_url: string;
  evidence: DiscoveryEvidenceEnvelope;
}
export interface DiscoveryPair {
  a: DiscoveryPairSide;
  b: DiscoveryPairSide;
}
export interface DiscoveryPairSide {
  id: string;
  name: LocalizedDiscoveryText;
  domain: LocalizedDiscoveryText;
}
export interface LocalizedDiscoveryText {
  zh: string;
  en?: string;
}
export interface DiscoveryProvenance {
  status: "not_started" | "incomplete_review";
  recorded_source_count: number;
  independent_review_complete: false;
  systematic_search_recorded: false;
}
export interface DiscoveryReadiness {
  status: "blocked";
  ready_for_preregistration: false;
  blockers: (
    | "source_review"
    | "candidate_equation"
    | "variable_mapping"
    | "dataset_record"
    | "primary_metric"
    | "preregistered_stop_rule"
  )[];
}
export interface DiscoveryValidationPlan {
  status: "draft_requires_user_completion";
  hypothesis: LocalizedDiscoveryText;
  data_needed: LocalizedDiscoveryText;
  baseline: LocalizedDiscoveryText;
  primary_metric: LocalizedDiscoveryText;
  failure_condition: LocalizedDiscoveryText;
  validation_gaps?: DiscoveryValidationGap[];
  preregistered: false;
}
export interface DiscoveryValidationGap {
  gap_id:
    | "source_support_not_reviewed"
    | "candidate_equation_not_recorded"
    | "candidate_equation_not_expert_reviewed"
    | "variable_mapping_not_recorded"
    | "variable_mapping_not_expert_reviewed"
    | "competing_explanations_not_tested"
    | "dataset_and_sampling_not_recorded"
    | "baseline_and_stop_rule_not_preregistered";
  label: LocalizedDiscoveryText;
}
export interface DiscoveryEvidenceEnvelope {
  schema_version: "evidence-envelope-v1";
  evidence_level: "candidate";
  candidate: DiscoveryEvidenceCandidate;
  source: DiscoveryEvidenceSource;
  result: DiscoveryEvidenceResult;
  independence: DiscoveryEvidenceIndependence;
  counterexamples: DiscoveryEvidenceCounterexamples;
  ledger: DiscoveryEvidenceLedger;
}
export interface DiscoveryEvidenceCandidate {
  status: "recorded";
  kind: "discovery_candidate" | "tier2_discovery_candidate";
  label?: string | null;
  score?: null;
}
export interface DiscoveryEvidenceSource {
  status: "not_recorded";
  kind: "not_recorded";
  label?: null;
  url?: null;
  source_review?: null;
}
export interface DiscoveryEvidenceResult {
  status: "not_recorded";
  provenance: "NOT_TESTED";
  verdict: "NOT_TESTED";
  summary?: null;
}
export interface DiscoveryEvidenceIndependence {
  status: "not_recorded";
  kind: "not_recorded";
  summary?: null;
}
export interface DiscoveryEvidenceCounterexamples {
  status: "not_recorded" | "gap_recorded";
  summary?: string | null;
}
export interface DiscoveryEvidenceLedger {
  status: "not_recorded";
  claim_id?: null;
  version?: null;
  recorded_at?: null;
  artifact_sha256?: null;
  url?: null;
}
/**
 * GET /api/discoveries — bounded, fail-closed candidate queue.
 */
export interface DiscoveriesResponse {
  count: number;
  discoveries?: DiscoveryCandidate[];
  tier2_count: number;
  tier2?: DiscoveryCandidate[];
  stats: DiscoveryStats;
}
export interface DiscoveryStats {
  total_candidates: number;
  priority_review: number;
  candidate_pool: number;
  candidate_families: number;
  source_backed: number;
  ready_for_preregistration: number;
}
export interface DiscoveryEvidenceSourceReview {
  reviewer: string;
  reviewed_at: string;
}
export interface DraftExcerptRef {
  excerpt_id: string;
  source_revision: number;
  content_digest: string;
  start: number;
  end: number;
}
export interface DraftFormulaLink {
  result_ref: string;
  metadata: FormulaRunMetadata;
  result_digest: string;
  input_revision: number;
  comparison_scope: "expression" | "equation_form" | "initial_value_problem";
  /**
   * @minItems 1
   * @maxItems 4
   */
  outcomes:
    | [DraftFormulaOutcome]
    | [DraftFormulaOutcome, DraftFormulaOutcome]
    | [DraftFormulaOutcome, DraftFormulaOutcome, DraftFormulaOutcome]
    | [DraftFormulaOutcome, DraftFormulaOutcome, DraftFormulaOutcome, DraftFormulaOutcome];
  execution_attested: boolean;
}
export interface FormulaRunMetadata {
  result_ref: string;
  state: "claimed" | "returned" | "closed" | "interrupted";
  result_available: boolean;
  input_origin: "user_provided";
  formula_digest: string | null;
  formula_result_recorded_at: string | null;
  math_status: null;
  termination_state: "not_attested" | "reaped" | "pending";
  task_completed_means_math_passed: false;
  known_cost_units: 0;
}
export interface DraftFormulaOutcome {
  check_kind: "template" | "dimensions" | "canonical_transform" | "bounded_numeric";
  status: "passed" | "failed" | "inconclusive" | "unsupported" | "resource_limit";
  relation:
    | "algebraic_identity"
    | "conditional_model_equivalence"
    | "local_approximation"
    | "partial_structure"
    | "not_equivalent"
    | "undetermined";
}
export interface DraftSourceSummary {
  excerpt_id: string;
  snapshot_id: string;
  source_id: string;
  source_revision: number;
  content_digest: string;
  raw_digest: string;
  excerpt_digest: string;
  snapshot_digest: string;
  start: number;
  end: number;
  quote: string;
  title: string;
  canonical_url: string;
  licence_basis: string;
  task_id: string;
  attempt: 1;
  input_revision: number;
}
export interface DraftTestPlan {
  question: string;
  measurement: string;
  primary_outcome: string;
  falsification: string;
  stop_rule: string;
}
/**
 * POST /api/errors — accepted/rate_limited/storage_failure envelope.
 *
 * `accepted=true` ⇒ persisted to disk and `stored_at` is set.
 * `accepted=false` ⇒ `reason` is set (`rate_limited` / `storage_failure`).
 */
export interface ErrorAcceptedResponse {
  accepted: boolean;
  stored_at?: string | null;
  reason?: string | null;
  [k: string]: unknown;
}
/**
 * Content-free client error envelope mirrored from the runtime API.
 */
export interface ErrorReportBody {
  message:
    | "ChunkLoadError"
    | "ClientError"
    | "Error"
    | "NetworkError"
    | "RangeError"
    | "ReferenceError"
    | "SyntaxError"
    | "TypeError"
    | "URIError";
  timestamp?: number | null;
  fatal?: boolean;
}
/**
 * GET /api/examples — handpicked example phenomenon pairs.
 *
 * Items are intentionally loose (raw KB rows are reshaped at render
 * time) so we keep `List[Dict[str, Any]]` instead of pinning a strict
 * KB-row shape.
 */
export interface ExamplesResponse {
  examples?: {
    [k: string]: unknown;
  }[];
}
/**
 * GET /api/flags — resolved feature flags + experiment variants.
 */
export interface FlagsResponse {
  flags?: {
    [k: string]: unknown;
  };
  experiments?: {
    [k: string]: unknown;
  };
  variants?: {
    [k: string]: string;
  };
  [k: string]: unknown;
}
export interface FormulaCheckData {
  result_ref: string;
  state: "claimed" | "returned" | "closed" | "interrupted";
  result_available: boolean;
  input_origin: "user_provided";
  formula_digest: string | null;
  formula_result_recorded_at: string | null;
  math_status: null;
  termination_state: "not_attested" | "reaped" | "pending";
  task_completed_means_math_passed: false;
  known_cost_units: 0;
  task_id: string;
}
export interface FormulaCheckEnvelope {
  schema_version: "structure-research-v1";
  contract_revision: "b1-candidate-01";
  data: FormulaCheckRequest;
}
export interface FormulaCheckRequest {
  input_revision: number;
  expected_research_version: number;
  formula_digest: string;
  confirm_formula_input: boolean;
}
export interface FormulaCheckResponse {
  schema_version: "structure-research-v1";
  contract_revision: "b1-candidate-01";
  data: FormulaCheckData;
}
export interface FormulaExecutionProvenance {
  execution_attested: boolean;
  execution_state: "ok" | "unsupported" | "limited" | "memory_limited" | "failed";
  resource_guard: string;
  owned_return_ref: string;
  reaped: true;
  code_version: string;
  full_input_digest: string;
  output_digest: string;
  formula_digest: string;
  problem_digest: string;
  display_AST_confirmation: "user_confirmed_snapshot";
  source_origin: "user_provided";
  source_facts_verified: false;
  mathematics_is_not_real_world_mechanism: true;
}
export interface FormulaPublicObject {}
export interface FormulaResultData {
  metadata: FormulaRunMetadata;
  state: "available" | "unavailable";
  result: {
    [k: string]: unknown;
  } | null;
  provenance?: FormulaExecutionProvenance | null;
}
export interface FormulaResultResponse {
  schema_version: "structure-research-v1";
  contract_revision: "b1-candidate-01";
  data: FormulaResultData;
}
export interface FormulaRevisionDraft {
  input_origin: "user_provided";
  comparison_scope: "expression" | "equation_form" | "initial_value_problem";
  left: FormulaSideDraft;
  right: FormulaSideDraft | null;
  /**
   * @minItems 1
   * @maxItems 4
   */
  requested_checks:
    | ["template" | "dimensions" | "canonical_transform" | "bounded_numeric"]
    | [
        "template" | "dimensions" | "canonical_transform" | "bounded_numeric",
        "template" | "dimensions" | "canonical_transform" | "bounded_numeric"
      ]
    | [
        "template" | "dimensions" | "canonical_transform" | "bounded_numeric",
        "template" | "dimensions" | "canonical_transform" | "bounded_numeric",
        "template" | "dimensions" | "canonical_transform" | "bounded_numeric"
      ]
    | [
        "template" | "dimensions" | "canonical_transform" | "bounded_numeric",
        "template" | "dimensions" | "canonical_transform" | "bounded_numeric",
        "template" | "dimensions" | "canonical_transform" | "bounded_numeric",
        "template" | "dimensions" | "canonical_transform" | "bounded_numeric"
      ];
  /**
   * @maxItems 256
   */
  sample_points: string[];
}
export interface FormulaSideDraft {
  family: "queue_flow" | "first_order_storage" | "local_recovery";
  template_id: "little" | "mm1" | "passive_decay" | "linear_stable";
  original_display: string;
  expression: {
    [k: string]: unknown;
  } | null;
  /**
   * @maxItems 12
   */
  symbols:
    | []
    | [
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ];
  /**
   * @maxItems 24
   */
  assumptions: {
    [k: string]: unknown;
  }[];
  /**
   * @maxItems 1
   */
  initial_conditions:
    | []
    | [
        {
          [k: string]: unknown;
        }
      ];
  /**
   * @maxItems 24
   */
  boundary_conditions: {
    [k: string]: unknown;
  }[];
  /**
   * @maxItems 20
   */
  source_refs?:
    | []
    | [
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ]
    | [
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        },
        {
          [k: string]: unknown;
        }
      ];
  measure_scope: string;
  time_basis?: "s" | "workday" | "from_symbol_units";
}
/**
 * GET /api/health — liveness/deep-probe response.
 */
export interface HealthResponse {
  status?: string;
  kb_size?: number;
  llm_model?: string;
  artifact_id?: string | null;
  embedding_shape?: number[] | null;
  checks?: {
    [k: string]: string;
  } | null;
  /**
   * Deep mode (`?deep=1`) surfaces the query-embedding LRU cache hit rate (Session #17 P2). Values are numeric (int counts + float hit_rate).
   */
  query_cache?: {
    [k: string]: number;
  } | null;
}
/**
 * A single history row returned by GET /api/history.
 */
export interface HistoryRecord {
  id: number;
  query: string;
  kind: string;
  result_summary?: string | null;
  created_at: string;
}
/**
 * Body for POST /api/history — records one user query.
 */
export interface HistoryRecordRequest {
  query: string;
  kind: string;
  result_summary?: {
    [k: string]: unknown;
  } | null;
}
/**
 * GET /api/history response envelope.
 */
export interface HistoryResponse {
  items?: HistoryRecord[];
  total?: number;
}
/**
 * A single retrieved phenomenon card surfaced in `kb_cards` event.
 */
export interface KBCard {
  id: string;
  name: string;
  domain: string;
  score: number;
  snippet?: string | null;
}
export interface MappingRequest {
  a_id: string;
  b_id: string;
  lang?: "zh" | "en";
}
export interface MappingResponse {
  schema_version: "mapping-response-v2";
  from_cache: boolean;
  a: MappingSide;
  b: MappingSide;
  retrieval_similarity: number;
  mapping: CandidateMapping;
}
export interface MappingSide {
  id: string;
  name: string;
  domain: string;
  type_id: string;
  description: string;
  original_query?: string | null;
}
export interface MappingStreamRequest {
  b_id: string;
  a_id?: string | null;
  text_a?: string | null;
  lang?: "zh" | "en";
}
export interface MethodDraftContent {
  schema_version: "structure-research-v1";
  contract_revision: "method-draft-v1";
  request: MethodDraftRequest;
  /**
   * @minItems 1
   * @maxItems 20
   */
  sources:
    | [DraftSourceSummary]
    | [DraftSourceSummary, DraftSourceSummary]
    | [DraftSourceSummary, DraftSourceSummary, DraftSourceSummary]
    | [DraftSourceSummary, DraftSourceSummary, DraftSourceSummary, DraftSourceSummary]
    | [DraftSourceSummary, DraftSourceSummary, DraftSourceSummary, DraftSourceSummary, DraftSourceSummary]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ]
    | [
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary,
        DraftSourceSummary
      ];
  origin: ResolvedPlanOrigin | ResolvedUserOrigin;
  formula: DraftFormulaLink | null;
}
export interface MethodDraftRequest {
  input_revision: number;
  expected_research_version: number;
  /**
   * @minItems 1
   * @maxItems 20
   */
  excerpt_refs:
    | [DraftExcerptRef]
    | [DraftExcerptRef, DraftExcerptRef]
    | [DraftExcerptRef, DraftExcerptRef, DraftExcerptRef]
    | [DraftExcerptRef, DraftExcerptRef, DraftExcerptRef, DraftExcerptRef]
    | [DraftExcerptRef, DraftExcerptRef, DraftExcerptRef, DraftExcerptRef, DraftExcerptRef]
    | [DraftExcerptRef, DraftExcerptRef, DraftExcerptRef, DraftExcerptRef, DraftExcerptRef, DraftExcerptRef]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ]
    | [
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef,
        DraftExcerptRef
      ];
  origin: PlanLeadOrigin | CatalogOrigin | UserMethodOrigin;
  method: string;
  /**
   * @minItems 1
   * @maxItems 20
   */
  mapping:
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  /**
   * @minItems 1
   * @maxItems 20
   */
  nontransferable:
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  /**
   * @minItems 1
   * @maxItems 20
   */
  competing_explanations:
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ]
    | [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string
      ];
  test_plan: DraftTestPlan;
  formula_result_ref?: string | null;
  supersedes_ref?: string | null;
}
export interface PlanLeadOrigin {
  kind: "plan_lead";
  plan_contract: "funded-plan-v1" | "funded-plan-v2";
  result_ref: string;
  candidate_index: number;
  lead_index: number;
}
export interface UserMethodOrigin {
  kind: "user_proposed";
  label: string;
  description: string;
}
export interface ResolvedPlanOrigin {
  kind: "plan_lead";
  plan_contract: "funded-plan-v1" | "funded-plan-v2";
  result_ref: string;
  candidate_index: number;
  lead_index: number;
  label: string;
  lead: string;
  mode: "fixture" | "controlled_fixture" | "native_live";
  producer: "owned-plan-fixture-v1" | "core-controlled-native-v1" | "owned-native-plan-runtime-v1";
  result_digest: string;
  input_revision: number;
  verification: "unverified";
}
export interface ResolvedUserOrigin {
  kind: "user_proposed";
  label: string;
  description: string;
  mode: "user_proposed";
  verification: "unverified";
}
export interface MethodDraftData {
  metadata: MethodDraftMetadata;
  content: MethodDraftContent;
}
export interface MethodDraftMetadata {
  draft_ref: string;
  input_revision: number;
  problem_digest: string;
  research_version_before: number;
  research_version_after: number;
  created_at: string;
  content_digest: string;
  is_historical: boolean;
  origin_kind: "plan_lead" | "kb_record" | "user_proposed";
  validation_status?: "unverified";
  execution_status?: "not_executed";
}
export interface MethodDraftEnvelope {
  schema_version: "structure-research-v1";
  contract_revision: "method-draft-v1";
  data: MethodDraftRequest;
}
export interface MethodDraftHistoryData {
  /**
   * @maxItems 20
   */
  items:
    | []
    | [MethodDraftMetadata]
    | [MethodDraftMetadata, MethodDraftMetadata]
    | [MethodDraftMetadata, MethodDraftMetadata, MethodDraftMetadata]
    | [MethodDraftMetadata, MethodDraftMetadata, MethodDraftMetadata, MethodDraftMetadata]
    | [MethodDraftMetadata, MethodDraftMetadata, MethodDraftMetadata, MethodDraftMetadata, MethodDraftMetadata]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ]
    | [
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata,
        MethodDraftMetadata
      ];
  next_cursor: string | null;
}
export interface MethodDraftHistoryResponse {
  schema_version: "structure-research-v1";
  contract_revision: "method-draft-v1";
  data: MethodDraftHistoryData;
}
export interface MethodDraftResponse {
  schema_version: "structure-research-v1";
  contract_revision: "method-draft-v1";
  data: MethodDraftData;
}
export interface NativePlanConfirmationData {
  task_id: string;
  result_ref: string;
  state: "queued";
  cash_evidence: "not_observed";
  real_model_executed: false;
  recorded_at: null;
}
export interface NativePlanConfirmationEnvelope {
  schema_version: "structure-research-v1";
  contract_revision: "funded-plan-v2";
  data: PlanConfirmationRequest;
}
export interface PlanConfirmationRequest {
  preview_ref: string;
  preview_digest: string;
  request_digest: string;
  expected_research_version: number;
  approved_upper_units: number;
  confirm_outbound: true;
}
export interface NativePlanConfirmationResponse {
  schema_version: "structure-research-v1";
  contract_revision: "funded-plan-v2";
  data: NativePlanConfirmationData;
}
export interface NativePlanPreviewEnvelope {
  schema_version: "structure-research-v1";
  contract_revision: "funded-plan-v2";
  data: PlanPreviewRequest;
}
export interface PlanPreviewRequest {
  input_revision: number;
  expected_research_version: number;
  observation_source: "own_observation";
  declaration_status: "self_declared";
}
export interface NativePlanPreviewResponse {
  schema_version: "structure-research-v1";
  contract_revision: "funded-plan-v2";
  data: NativePlanPreviewView;
}
export interface NativePlanPreviewView {
  preview_ref: string;
  preview_digest: string;
  request_digest: string;
  research_id: string;
  input_revision: number;
  expected_research_version: number;
  exact_input: string;
  purpose: "phenomenon_plan_v1";
  observation_rights: "self_declared";
  state: "awaiting_confirmation" | "funding_closed";
  can_confirm: boolean;
  funding_reason: "FUNDING_CLOSED" | null;
  cash_evidence: "not_observed";
  approved_upper_units: number;
  currency: "CNY";
  scale: 6;
  quote: NativePlanQuote;
  expires_at: number;
  explanation: string;
}
export interface NativePlanQuote {
  protocol: "financial9-native-quote-v1";
  revision: string;
  purpose: "phenomenon_plan_v1";
  provider: "deepseek";
  model: "deepseek-flash";
  declared_model_version: "DeepSeek-V4.1-Flash-1017";
  declaration_observed_on: "2026-10-18";
  currency: "CNY";
  scale: 6;
  peak_input_hit_units_per_million: 40000;
  peak_input_miss_units_per_million: 2000000;
  peak_output_units_per_million: 8000000;
  context_bound: 1048576;
  provider_output_bound: 393216;
  max_output_tokens: 4096;
  approved_upper_units: number;
  codec_digest: string;
  issued_at: number;
  valid_until: number;
  price_source: "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/";
}
export interface NativePlanReadData {
  task_id: string;
  result_ref: string;
  state: "saved" | "failed_insufficient" | "pending_reconciliation" | "cancelled" | "queued" | "generating";
  financial_version: 9;
  execution_mode: ("controlled_fixture" | "native_live") | null;
  real_model_executed: boolean;
  cost_state: "unreserved" | "held" | "upper_booked" | "unknown";
  cleanup_state: "pending" | "clean" | "uncertain";
  safe_code: ("saved" | "body_invalid" | "send_unknown" | "not_sent" | "cancelled" | "access_ended") | null;
  recorded_at: string | null;
  content: NativePlanResult | null;
}
export interface NativePlanResult {
  protocol: "owned-native-plan-result-v2";
  purpose: "phenomenon_plan_v1";
  result_ref: string;
  task_id: string;
  research_id: string;
  input_revision: number;
  input_digest: string;
  request_digest: string;
  consent_digest: string;
  admission_digest: string;
  recorded_at: string;
  execution_mode: "controlled_fixture" | "native_live";
  producer: "core-controlled-native-v1" | "owned-native-plan-runtime-v1";
  real_model_executed: boolean;
  weight_identity_verified: false;
  literature_status: "not_retrieved";
  mathematics_status: "not_checked";
  mechanism_status: "unverified";
  observation_rights: "self_declared";
  query_state: "draft_only";
  automatically_created_sources: 0;
  proposal: PhenomenonPlanCandidate;
}
export interface PhenomenonPlanCandidate {
  summary: string;
  /**
   * @maxItems 3
   */
  candidates:
    [] | [PlanNomination] | [PlanNomination, PlanNomination] | [PlanNomination, PlanNomination, PlanNomination];
  /**
   * @maxItems 5
   */
  query_suggestions:
    | []
    | [PlanQuerySuggestion]
    | [PlanQuerySuggestion, PlanQuerySuggestion]
    | [PlanQuerySuggestion, PlanQuerySuggestion, PlanQuerySuggestion]
    | [PlanQuerySuggestion, PlanQuerySuggestion, PlanQuerySuggestion, PlanQuerySuggestion]
    | [PlanQuerySuggestion, PlanQuerySuggestion, PlanQuerySuggestion, PlanQuerySuggestion, PlanQuerySuggestion];
  /**
   * @minItems 1
   * @maxItems 8
   */
  gaps:
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string];
  /**
   * @maxItems 3
   */
  clarification_questions: [] | [string] | [string, string] | [string, string, string];
}
export interface PlanNomination {
  label: string;
  mechanism_hypothesis: string;
  why_considered: string;
  /**
   * @maxItems 2
   */
  method_leads: [] | [string] | [string, string];
  /**
   * @minItems 1
   * @maxItems 5
   */
  key_unknowns:
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string];
}
export interface PlanQuerySuggestion {
  candidate_index: number | null;
  query: string;
  intent: string;
}
export interface NativePlanReadResponse {
  schema_version: "structure-research-v1";
  contract_revision: "funded-plan-v2";
  data: NativePlanReadData;
}
export interface NativePlanRunMetadata {
  task_id: string;
  result_ref: string;
  state: "saved" | "failed_insufficient" | "pending_reconciliation" | "cancelled" | "queued" | "generating";
  financial_version: 9;
  execution_mode: ("controlled_fixture" | "native_live") | null;
  real_model_executed: boolean;
  cost_state: "unreserved" | "held" | "upper_booked" | "unknown";
  cleanup_state: "pending" | "clean" | "uncertain";
  safe_code: ("saved" | "body_invalid" | "send_unknown" | "not_sent" | "cancelled" | "access_ended") | null;
  recorded_at: string | null;
}
/**
 * GET /api/newsletter/count — current subscriber count (anon-safe).
 */
export interface NewsletterCountResponse {
  count?: number;
}
/**
 * Universality class / phase descriptor.
 */
export interface Phase {
  id: string;
  name: string;
  domain: string;
  description: string;
  company_count?: number;
}
export interface PhasesResponse {
  items?: Phase[];
  total?: number;
}
export interface PhenomenonEvidenceCandidate {
  status: "recorded";
  kind:
    | "phenomenon_kb_record_candidate"
    | "embedding_neighbor_candidate"
    | "shared_type_label_candidate"
    | "v2_model_pair_candidate";
  label: string;
  score?: null;
}
export interface PhenomenonEvidenceCounterexamples {
  status: "gap_recorded";
  summary: string;
}
export interface PhenomenonEvidenceEnvelope {
  schema_version: "evidence-envelope-v1";
  evidence_level: "candidate";
  candidate: PhenomenonEvidenceCandidate;
  source: PhenomenonEvidenceSource;
  result: PhenomenonEvidenceResult;
  independence: PhenomenonEvidenceIndependence;
  counterexamples: PhenomenonEvidenceCounterexamples;
  ledger: PhenomenonEvidenceLedger;
}
export interface PhenomenonEvidenceSource {
  status: "recorded";
  kind: "internal_kb";
  label: string;
  url?: null;
  source_review?: null;
}
export interface PhenomenonEvidenceResult {
  status: "not_recorded" | "recorded";
  provenance: "NOT_TESTED" | "INTERNAL_AI_SCREEN";
  verdict: "NOT_TESTED" | "INCONCLUSIVE";
  summary?: string | null;
}
export interface PhenomenonEvidenceIndependence {
  status: "not_recorded" | "recorded";
  kind: "not_recorded" | "internal";
  summary?: string | null;
}
export interface PhenomenonEvidenceLedger {
  status: "not_recorded";
  claim_id?: null;
  version?: null;
  recorded_at?: null;
  artifact_sha256?: null;
  url?: null;
}
export interface PhenomenonRecord {
  id: string;
  name: string;
  domain: string;
  type_id: string;
  description: string;
  evidence: PhenomenonEvidenceEnvelope;
}
export interface PhenomenonResponse {
  phenomenon: PhenomenonRecord;
  /**
   * @maxItems 8
   */
  similar?:
    | []
    | [PhenomenonSimilarCandidate]
    | [PhenomenonSimilarCandidate, PhenomenonSimilarCandidate]
    | [PhenomenonSimilarCandidate, PhenomenonSimilarCandidate, PhenomenonSimilarCandidate]
    | [PhenomenonSimilarCandidate, PhenomenonSimilarCandidate, PhenomenonSimilarCandidate, PhenomenonSimilarCandidate]
    | [
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate
      ]
    | [
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate
      ]
    | [
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate
      ]
    | [
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate,
        PhenomenonSimilarCandidate
      ];
  /**
   * @maxItems 5
   */
  same_structure?:
    | []
    | [PhenomenonSameStructureCandidate]
    | [PhenomenonSameStructureCandidate, PhenomenonSameStructureCandidate]
    | [PhenomenonSameStructureCandidate, PhenomenonSameStructureCandidate, PhenomenonSameStructureCandidate]
    | [
        PhenomenonSameStructureCandidate,
        PhenomenonSameStructureCandidate,
        PhenomenonSameStructureCandidate,
        PhenomenonSameStructureCandidate
      ]
    | [
        PhenomenonSameStructureCandidate,
        PhenomenonSameStructureCandidate,
        PhenomenonSameStructureCandidate,
        PhenomenonSameStructureCandidate,
        PhenomenonSameStructureCandidate
      ];
  /**
   * @maxItems 20
   */
  v2_pairs?:
    | []
    | [PhenomenonV2Candidate]
    | [PhenomenonV2Candidate, PhenomenonV2Candidate]
    | [PhenomenonV2Candidate, PhenomenonV2Candidate, PhenomenonV2Candidate]
    | [PhenomenonV2Candidate, PhenomenonV2Candidate, PhenomenonV2Candidate, PhenomenonV2Candidate]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ]
    | [
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate,
        PhenomenonV2Candidate
      ];
}
export interface PhenomenonSimilarCandidate {
  id: string;
  name: string;
  domain: string;
  type_id: string;
  description: string;
  retrieval_similarity: number;
  evidence: PhenomenonEvidenceEnvelope;
}
export interface PhenomenonSameStructureCandidate {
  id: string;
  name: string;
  domain: string;
  type_id: string;
  description: string;
  evidence: PhenomenonEvidenceEnvelope;
}
export interface PhenomenonV2Candidate {
  other_id: string;
  other_name: string;
  other_domain: string;
  candidate_reason: string;
  retrieval_similarity: number;
  evidence: PhenomenonEvidenceEnvelope;
}
export interface PlanConfirmationData {
  task_id: string;
  result_ref: string;
  state: "queued";
  funding_state: "approved_not_sent";
  plan_generation_ran: false;
  recorded_at: null;
}
export interface PlanConfirmationEnvelope {
  schema_version: "structure-research-v1";
  contract_revision: "b1-candidate-01";
  data: PlanConfirmationRequest;
}
export interface PlanConfirmationResponse {
  schema_version: "structure-research-v1";
  contract_revision: "funded-plan-v1";
  data: PlanConfirmationData;
}
export interface PlanPreviewEnvelope {
  schema_version: "structure-research-v1";
  contract_revision: "b1-candidate-01";
  data: PlanPreviewRequest;
}
export interface PlanPreviewResponse {
  schema_version: "structure-research-v1";
  contract_revision: "funded-plan-v1";
  data: PlanPreviewView;
}
export interface PlanPreviewView {
  preview_ref: string;
  preview_digest: string;
  request_digest: string;
  research_id: string;
  input_revision: number;
  expected_research_version: number;
  state: "awaiting_confirmation";
  exact_input: string;
  purpose: "phenomenon_plan_v1";
  observation_rights: "self_declared";
  approved_upper_units: number;
  currency: "CNY";
  scale: 6;
  quote: PlanQuote;
  expires_at: number;
  explanation: string;
}
export interface PlanQuote {
  protocol: "financial8-plan-quote-v1";
  revision: string;
  purpose: "phenomenon_plan_v1";
  provider: "deepseek";
  model: "deepseek-flash";
  declared_model_version: "DeepSeek-V4.1-Flash-1017";
  declaration_observed_on: "2026-10-18";
  currency: "CNY";
  scale: 6;
  peak_input_hit_units_per_million: 40000;
  peak_input_miss_units_per_million: 2000000;
  peak_output_units_per_million: 8000000;
  context_bound: 1048576;
  provider_output_bound: 393216;
  max_output_tokens: 4096;
  approved_upper_units: number;
  codec_digest: string;
  issued_at: number;
  valid_until: number;
  price_source: "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/";
}
export interface PlanReadData {
  task_id: string;
  result_ref: string;
  state: "saved" | "failed_insufficient" | "pending_reconciliation" | "cancelled" | "queued" | "generating";
  financial_state: "unreserved" | "held" | "upper_booked" | "unknown";
  safe_code: ("saved" | "body_invalid" | "send_unknown" | "not_sent" | "cancelled" | "access_ended") | null;
  recorded_at: string | null;
  plan_generation_ran: boolean;
  real_model_executed: false;
  execution_mode: "fixture";
  approved_upper_units: number;
  usage: PlanUsage | null;
  content: PlanResult | null;
}
export interface PlanUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  usage_priced_estimate_units: number;
  actual_charge_units: null;
  cost_kind: "upper_booked";
  booked_upper_units: number;
  currency: "CNY";
  scale: 6;
}
export interface PlanResult {
  protocol: "owned-phenomenon-plan-result-v1";
  purpose: "phenomenon_plan_v1";
  result_ref: string;
  task_id: string;
  research_id: string;
  input_revision: number;
  input_digest: string;
  request_digest: string;
  admission_digest: string;
  recorded_at: string;
  execution_mode: "fixture";
  plan_generation_ran: true;
  real_model_executed: false;
  literature_status: "not_retrieved";
  mathematics_status: "not_checked";
  mechanism_status: "unverified";
  observation_rights: "self_declared";
  query_state: "draft_only";
  automatically_created_sources: 0;
  proposal: PhenomenonPlanCandidate;
}
export interface PlanReadResponse {
  schema_version: "structure-research-v1";
  contract_revision: "funded-plan-v1";
  data: PlanReadData;
}
export interface PlanRunMetadata {
  task_id: string;
  result_ref: string;
  state: "saved" | "failed_insufficient" | "pending_reconciliation" | "cancelled" | "queued" | "generating";
  financial_state: "unreserved" | "held" | "upper_booked" | "unknown";
  safe_code: ("saved" | "body_invalid" | "send_unknown" | "not_sent" | "cancelled" | "access_ended") | null;
  recorded_at: string | null;
  plan_generation_ran: boolean;
  real_model_executed: false;
  execution_mode: "fixture";
  approved_upper_units: number;
  usage: PlanUsage | null;
}
/**
 * Legacy development-only query shape for DELETE /api/privacy/delete.
 *
 * A schema-valid production request returns HTTP 410. Constraint-invalid
 * query values return HTTP 422 before the handler. Current authenticated
 * account erasure is ``POST /api/me/delete`` and requires an active session.
 */
export interface PrivacyDeleteRequest {
  email?: string | null;
  code?: string | null;
  session_id?: string | null;
}
/**
 * Legacy development fixture; not the current account-erasure contract.
 *
 * Production returns HTTP 410. Use ``POST /api/me/delete`` for the
 * authenticated account-bound deletion flow.
 */
export interface PrivacyDeleteResponse {
  ok: true;
  deleted_at: string;
  removed: PrivacyRemovalCounts;
  email_confirmation: "sent" | "skipped";
}
/**
 * Per-store removal counts from the retired development fixture.
 */
export interface PrivacyRemovalCounts {
  newsletter_subscribers: number;
  mock_checkouts: number;
  error_log: number;
  structural_fingerprints: number;
  match_requests: number;
  referrals: number;
  connections_messages: number;
  connections_prefs: number;
}
/**
 * Data groups emitted by the retired development export fixture.
 */
export interface PrivacyExportData {
  newsletter_subscribers: {
    [k: string]: unknown;
  }[];
  mock_checkouts: {
    [k: string]: unknown;
  }[];
  error_log: {
    [k: string]: unknown;
  }[];
  structural_fingerprints: {
    [k: string]: unknown;
  }[];
  match_requests: {
    [k: string]: unknown;
  }[];
  referrals: {
    [k: string]: unknown;
  }[];
  connections_messages: {
    [k: string]: unknown;
  }[];
  connections_prefs: {
    [k: string]: unknown;
  }[];
  search_history: {
    [k: string]: unknown;
  }[];
}
/**
 * Legacy development-only query shape for GET /api/privacy/export.
 *
 * A schema-valid production request returns HTTP 410. Constraint-invalid
 * query values return HTTP 422 before the handler. This retired email-code
 * fixture is not an account right or production authentication mechanism;
 * signed-in export is ``GET /api/me/export``.
 */
export interface PrivacyExportRequest {
  email?: string | null;
  code?: string | null;
  session_id?: string | null;
}
/**
 * Legacy development fixture; not the current account-export contract.
 *
 * Production returns HTTP 410. Use ``GET /api/me/export`` for the
 * authenticated account-bound export.
 */
export interface PrivacyExportResponse {
  ok: true;
  exported_at: string;
  email: string | null;
  session_id: string | null;
  data: PrivacyExportData;
}
/**
 * RFC 7807-style error envelope returned by every failing endpoint.
 * Frontend can rely on `type` + `code` being present.
 */
export interface ProblemDetailEnvelope {
  type: string;
  title: string;
  status: number;
  code: string;
  detail?: string | null;
  instance?: string | null;
}
export interface SearchRequest {
  query: string;
  top_k?: number;
  rewrite?: boolean;
  lang?: string;
}
export interface SearchResponse {
  query: string;
  count: number;
  results?: SearchResult[];
}
export interface SearchResult {
  id: string;
  name: string;
  domain: string;
  type_id: string;
  description: string;
  score: number;
}
export interface SubscribeBody {
  email: string;
  source?: string | null;
}
export interface SynthesizeRequest {
  query: string;
  rewritten_query?: string | null;
  results?: {
    [k: string]: unknown;
  }[];
  lang?: string;
}
/**
 * Final verdict assembled from /api/ask/stream — exported for
 * fixtures + Storybook stories so they stay in lockstep with API.
 */
export interface Verdict {
  summary: string;
  confidence: number;
  similar_phenomena?: KBCard[];
  followups?: string[];
}
/**
 * GET /api/version — build & version metadata.
 *
 * Session #16 added `model` + `deployed_at` after the session #15
 * deploy-pipeline incident: dogfood scripts need a single endpoint to
 * fingerprint-check that prod is running the latest code AND that the model
 * variant matches expectations (e.g. `:nitro` vs non-nitro DeepSeek).
 */
export interface VersionResponse {
  semver: string;
  git_sha: string;
  build_date: string;
  python_version: string;
  python_abi: string;
  runtime_id: string;
  requirements_sha256: string;
  installed_freeze_sha256: string;
  fastapi: string;
  pydantic: string;
  starlette: string;
  uvicorn: string;
  env: string;
  /**
   * Model identifier the /api/ask endpoint will use (session #16).
   */
  model: string;
  /**
   * Deploy timestamp, distinct from build_date (image built once, deployed many times). Falls back to build_date if STRUCTURAL_DEPLOYED_AT unset.
   */
  deployed_at: string;
}
/**
 * GET /api/whoami — debug helper reflecting the resolved auth tier.
 */
export interface WhoAmIResponse {
  tier: string;
  api_key_supplied: boolean;
}
