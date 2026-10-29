ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PY ?= $(ROOT)/.venv/bin/python
# OpenAPI schema output is Pydantic-version-sensitive. A project-local,
# gitignored release-pinned environment wins for normal local use. An
# explicit `make PY=python ...` (the sanity workflow) always wins instead.
ifeq ($(origin PY),command line)
OPENAPI_PY ?= $(PY)
else
OPENAPI_PY ?= $(if $(wildcard $(ROOT)/.venv-openapi/bin/python),$(ROOT)/.venv-openapi/bin/python,$(PY))
endif
TYPES_PY ?= $(OPENAPI_PY)
# setup-python provides pythonLocation in CI; an explicit parent Python wins
# locally. Child browser services must not guess a checkout-local .venv.
export STRUCTURAL_RELEASE_TEST_PYTHON ?= $(if $(pythonLocation),$(pythonLocation)/bin/python,$(PY))
LLM_SCALING_DIR := $(ROOT)/v4/validation/llm-scaling
LLM_SCALING_PY ?= $(LLM_SCALING_DIR)/.venv/bin/python
PACKAGE_PYTHONPATH := $(ROOT)/packages/guarded-llm/src:$(ROOT)/packages/cross-judge/src:$(ROOT)/packages/reject-aware-critic/src:$(ROOT)/packages/soc-pipeline/src
PYTEST := PYTHONPATH=$(PACKAGE_PYTHONPATH) $(PY) -m pytest
BACKEND_PYTEST := PYTHONPATH=$(ROOT)/web/backend:$(PACKAGE_PYTHONPATH) $(PY) -m pytest

FRONTEND_NODE_TESTS := \
	web/frontend/tests/test_analyticsSensitiveRoutes.js \
	web/frontend/tests/test_analyzeTrust.js \
	web/frontend/tests/test_askTrust.js \
	web/frontend/tests/test_buildAnalyzeUrl.js \
	web/frontend/tests/test_evidenceMethodPlan.js \
	web/frontend/tests/test_financialRegistry.js \
	web/frontend/tests/test_financialScenario.js \
	web/frontend/tests/test_headerScroll.js \
	web/frontend/tests/test_historyPrivacy.js \
	web/frontend/tests/test_historySidebarPerformance.js \
	web/frontend/tests/test_newsletterClosed.js \
	web/frontend/tests/test_privateNavigation.js \
	web/frontend/tests/test_reportTrust.js \
	web/frontend/tests/test_searchBootstrap.js \
	web/frontend/tests/test_searchSynthesisRendering.js \
	web/frontend/tests/test_secondaryToolContracts.js

BROWSER_CONTRACT_SEARCH_ASK_ANALYZE_PHENOMENON_TESTS := \
	tests/e2e/test_search_private_navigation.py \
	tests/e2e/test_phenomenon_evidence_mobile.py

BROWSER_CONTRACT_DISCOVERY_CLASSES_PAPERS_TESTS := \
	tests/e2e/test_discovery_validation_plan.py \
	tests/e2e/test_classes_language_mobile.py \
	tests/e2e/test_papers_public_runtime.py

BROWSER_CONTRACT_LIBRARY_AUTH_REPORTS_FAVORITES_TESTS := \
	tests/e2e/test_full_public_surface.py \
	web/tests/e2e/test_auth_login_bootstrap_privacy.py \
	tests/e2e/test_unified_research_library.py \
	tests/e2e/test_history_sidebar.py \
	web/tests/e2e/test_thank_you_copy.py \
	web/tests/e2e/test_report_share.py \
	web/tests/e2e/test_cross_domain_report_claim.py \
	web/tests/e2e/test_subscriptions_closed.py \
	web/tests/e2e/test_newsletter_e2e.py

BROWSER_CONTRACT_SECONDARY_WHITESPACE_TESTS := \
	web/tests/e2e/test_secondary_tools_candidate_journeys.py \
	web/tests/e2e/test_whitespace.py

FINANCIAL_PREVIEW_BROWSER_CONTRACT_TESTS := \
	web/tests/e2e/test_research_financial_preview_browser.py

FINANCIAL_SCENARIO_BROWSER_CONTRACT_TESTS := \
	web/tests/e2e/test_research_financial_scenario_browser.py

FINANCIAL_REGISTRY_BROWSER_CONTRACT_TESTS := \
	web/tests/e2e/test_research_financial_registry_browser.py

EVIDENCE_METHOD_BROWSER_CONTRACT_TESTS := \
	web/tests/e2e/test_evidence_method_plan_browser.py

PHASE_REAL_BROWSER_CONTRACT_TESTS := \
	web/tests/e2e/test_phase_auth_real.py \
	web/tests/e2e/test_cookie_consent.py

.PHONY: test-financial-scenario-browser-contract test-financial-registry-browser-contract test-evidence-method-browser-contract test-financial-preview-browser-contract test test-unit test-integration test-phase-python-contract test-e2e test-frontend-node test-browser-contracts test-retrieval-contract test-product-contracts test-release-contracts test-all test-fast openapi-env openapi-generate openapi-check types-check python-syntax-check llm-scaling-env llm-scaling-generate llm-scaling-check verify-release help

help:
	@echo "Targets:"
	@echo "  test-unit         Run unit tests (offline, < 30s)"
	@echo "  test-integration  Run integration tests (in-process, < 2min)"
	@echo "  test-phase-python-contract  Run the complete offline Phase Python suites"
	@echo "  test-e2e          Run e2e tests (live network, may be flaky)"
	@echo "  test-frontend-node  Run every vanilla frontend Node contract"
	@echo "  test-browser-contracts  Run the hard browser contract suite"
	@echo "  test-financial-preview-browser-contract  Run all temporary financial CSV preview browser cases"
	@echo "  test-evidence-method-browser-contract  Run all saved-evidence method browser cases"
	@echo "  test-financial-registry-browser-contract  Run all financial registry save and account lifecycle browser cases"
	@echo "  test-financial-scenario-browser-contract  Run all seven financial scenario actual Main browser cases"
	@echo "  test-retrieval-contract  Validate retrieval dataset, determinism, and OOS policy"
	@echo "  test-product-contracts  Validate public controls, human-review tooling, and research claims"
	@echo "  test-release-contracts  Run every offline root contract with backend imports enabled"
	@echo "  test-fast         test-unit + test-integration (no network)"
	@echo "  test-all          Everything"
	@echo "  openapi-env       Explicitly create the release-pinned OpenAPI environment"
	@echo "  openapi-generate  Update OpenAPI using release-target backend dependencies"
	@echo "  openapi-check     Check OpenAPI using release-target backend dependencies"
	@echo "  types-check       Regenerate API TypeScript in a temp file and compare exactly"
	@echo "  python-syntax-check  Compile tracked Python with the release interpreter"
	@echo "  llm-scaling-env  Create the locked Python 3.11 artifact-generator environment"
	@echo "  llm-scaling-generate  Regenerate canonical LLM scaling artifacts"
	@echo "  llm-scaling-check  Check LLM scaling artifacts in the locked environment"
	@echo "  verify-release    Authoritative offline release gate across backend, packages, retrieval, and Phase"
	@echo "  test              Alias for test-fast"

test: test-fast

test-unit:
	$(PYTEST) v4/tests/sanity -m sanity -q

test-integration:
	$(PYTEST) v4/tests/integration v4/product/d1_phase_detector/tests v4/product/d1_phase_detector/api/tests -q

test-phase-python-contract:
	$(PYTEST) v4/product/d1_phase_detector/tests v4/product/d1_phase_detector/api/tests -q

test-e2e:
	$(PYTEST) tests/e2e -m e2e -v

test-frontend-node:
	@set -eu; for test_file in $(FRONTEND_NODE_TESTS); do node "$$test_file"; done

test-browser-contracts:
	$(PYTEST) $(BROWSER_CONTRACT_SEARCH_ASK_ANALYZE_PHENOMENON_TESTS) -m "e2e and not requires_internet" -v
	$(PYTEST) $(BROWSER_CONTRACT_DISCOVERY_CLASSES_PAPERS_TESTS) -m "e2e and not requires_internet" -v
	$(PYTEST) tests/e2e/test_full_public_surface.py web/tests/e2e/test_auth_login_bootstrap_privacy.py -p no:logging -m "e2e and not requires_internet" -v
	$(PYTEST) $(filter-out tests/e2e/test_full_public_surface.py,$(filter tests/e2e/%,$(BROWSER_CONTRACT_LIBRARY_AUTH_REPORTS_FAVORITES_TESTS))) -m "e2e and not requires_internet" -v
	$(PYTEST) $(filter-out web/tests/e2e/test_auth_login_bootstrap_privacy.py,$(filter web/tests/e2e/%,$(BROWSER_CONTRACT_LIBRARY_AUTH_REPORTS_FAVORITES_TESTS))) -m "e2e and not requires_internet" -v
	$(PYTEST) $(BROWSER_CONTRACT_SECONDARY_WHITESPACE_TESTS) -m "e2e and not requires_internet" -v
	$(PYTEST) $(PHASE_REAL_BROWSER_CONTRACT_TESTS) -v

test-financial-preview-browser-contract:
	$(PYTEST) $(FINANCIAL_PREVIEW_BROWSER_CONTRACT_TESTS) -p no:logging -v

test-financial-scenario-browser-contract:
	$(BACKEND_PYTEST) $(FINANCIAL_SCENARIO_BROWSER_CONTRACT_TESTS) --deselect="test_research_financial_scenario_browser.py::test_fin3_actual_main_coverage_three_scenarios_and_twenty_one_points" -p no:logging -v

test-financial-registry-browser-contract:
	$(PYTEST) $(FINANCIAL_REGISTRY_BROWSER_CONTRACT_TESTS) -p no:logging -v

test-evidence-method-browser-contract:
	$(BACKEND_PYTEST) $(EVIDENCE_METHOD_BROWSER_CONTRACT_TESTS) -p no:logging -v

test-retrieval-contract:
	$(BACKEND_PYTEST) web/backend/tests/test_retrieval_eval_dataset.py -q

test-product-contracts:
	$(PYTEST) tests/test_public_controls.py tests/test_english_review_tool.py tests/test_research_claim_gate.py -q

# pytest.ini intentionally limits implicit discovery to the legacy v4 and E2E
# trees.  A release gate must name the root tests explicitly or new product,
# evidence, deployment, and type contracts are silently skipped.  Use the
# backend import path because several root contracts exercise API modules.
test-release-contracts:
	$(BACKEND_PYTEST) tests --ignore=tests/e2e --deselect="tests/test_research_browser.py::test_d1_page_preview_confirm_real_worker_and_private_mobile_records" --deselect="tests/test_research_browser.py::test_d1_page_lost_start_receipt_reload_replays_original_key" --deselect="tests/test_research_browser.py::test_d1_source_link_uses_public_canonical_url_without_provider_reference" --deselect="tests/test_research_browser.py::test_d1_task_switch_clears_old_cards_before_empty_new_records" --deselect="tests/test_research_browser.py::test_d1_input_switch_rejects_late_old_records_and_clears_cards" --deselect="tests/test_research_browser.py::test_d1_closed_unknown_keeps_original_observation_visible" --deselect="tests/test_research_browser.py::test_real_page_revisions_restart_private_access_and_mobile" --deselect="tests/test_research_browser.py::test_real_commit_lost_browser_receipt_reuses_original_key" --deselect="tests/test_research_browser.py::test_nfc_pending_digest_reconciles_after_real_revision_commit_and_reopen" --deselect="tests/test_research_browser.py::test_inflight_form_is_frozen_until_actual_commit_receipt_then_reenabled" --deselect="tests/test_research_browser.py::test_invalid_sso_poison_clears_previously_rendered_research" --deselect="tests/test_research_browser.py::test_account_delete_page_reports_actual_outcome_without_restore_promises[completed]" --deselect="tests/test_research_browser.py::test_account_delete_page_reports_actual_outcome_without_restore_promises[pending]" --deselect="tests/test_research_browser.py::test_account_delete_page_reports_actual_outcome_without_restore_promises[rejected]" --deselect="tests/test_research_browser.py::test_account_delete_page_reports_actual_outcome_without_restore_promises[unknown]" --deselect="tests/test_research_browser.py::test_public_report_page_stops_showing_resource_during_pending_account_cleanup" --deselect="tests/test_research_browser.py::test_c0_page_real_task_worker_money_and_draft_survive_status_refresh" --deselect="tests/test_research_browser.py::test_c0_page_cancel_unknown_reconcile_never_restarts_task" --deselect="tests/test_research_browser.py::test_late_task_start_receipt_does_not_rebind_newer_saved_problem" --deselect="tests/test_research_browser.py::test_task_refresh_never_rebases_other_window_save_base" --deselect="tests/test_research_browser.py::test_task_refresh_never_rebases_other_window_run_base" --deselect="tests/test_research_browser.py::test_late_cancel_receipt_cannot_replace_newer_same_revision_task" --deselect="tests/test_research_browser.py::test_entry_original_draft_kb_and_real_saved_source_chain" --deselect="tests/test_research_browser.py::test_entry_index_real_pagination_invalid_cursor_and_late_receipt" --deselect="tests/test_research_browser.py::test_entry_list_reopen_preserves_unknown_save_and_late_auth_list" --deselect="tests/test_research_browser.py::test_entry_kb_unavailable_is_honest_and_account_switch_clears_private_view" --deselect="tests/test_research_browser.py::test_entry_changed_source_query_rejects_held_real_preview" --deselect="tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[503-list]" --deselect="tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[503-kb]" --deselect="tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[503-reload]" --deselect="tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[500-list]" --deselect="tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[403-list]" --deselect="tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[404-list]" --deselect="tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[409-list]" --deselect="tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[network-list]" --deselect="tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[bad-json-list]" --deselect="tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[bad-user-list]" --deselect="tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[ok-false-list]" --deselect="tests/test_research_browser.py::test_entry_auth_real_401_clears_private_draft_and_stops_chain" --deselect="tests/test_research_browser.py::test_source_reopen_explains_explicit_read_without_losing_draft_or_refetching_provider[viewport0]" --deselect="tests/test_research_browser.py::test_source_reopen_explains_explicit_read_without_losing_draft_or_refetching_provider[viewport1]" --deselect="tests/test_research_browser.py::test_method_result_real_b_typed_http_reopen_restart_and_local_citations[viewport0]" --deselect="tests/test_research_browser.py::test_method_result_real_b_typed_http_reopen_restart_and_local_citations[viewport1]" --deselect="tests/test_research_browser.py::test_method_result_consumes_real_reconcile_view_without_generation[pending]" --deselect="tests/test_research_browser.py::test_method_result_real_bad_b_never_becomes_visible_body[null]" --deselect="tests/test_research_browser.py::test_method_result_cancelled_pending_body_stays_hidden[pending]" --deselect="tests/test_research_browser.py::test_method_result_changed_input_and_late_real_a_cannot_restore_old_body" --deselect="tests/test_research_browser.py::test_method_result_actual_auth503_preserves_draft_but_requires_fresh_read" --deselect="tests/test_research_browser.py::test_method_result_cross_owner_and_source_withdrawal_remove_private_body" --deselect="tests/test_research_browser.py::test_method_view_client_schema_rejects_corruption_of_real_backend_view" --deselect="tests/test_research_browser.py::test_method_result_new_explicit_source_task_clears_current_method_body" --deselect="tests/test_research_browser.py::test_method_result_late_actual_access_error_cannot_clear_new_problem[saved-404]" --deselect="tests/test_research_browser.py::test_method_result_late_actual_access_error_cannot_clear_new_problem[saved-401]" --deselect="tests/test_research_browser.py::test_method_result_late_actual_access_error_cannot_clear_new_problem[draft-404]" --deselect="tests/test_research_browser.py::test_method_result_late_actual_access_error_cannot_clear_new_problem[draft-401]" --deselect="tests/test_research_browser.py::test_method_result_successful_old_write_cannot_revive_revoked_private_view" --deselect="tests/test_research_browser.py::test_method_current_source_unavailable_preserves_problem_and_explains_missing_body[task-refresh]" --deselect="tests/test_research_browser.py::test_method_current_source_unavailable_preserves_problem_and_explains_missing_body[source-refresh]" --deselect="tests/test_research_browser.py::test_history_real_result_original_problem_native_new_tab_restart_and_readonly[viewport0-history-revision]" --deselect="tests/test_research_browser.py::test_history_real_result_original_problem_native_new_tab_restart_and_readonly[viewport0-history-same]" --deselect="tests/test_research_browser.py::test_history_real_result_original_problem_native_new_tab_restart_and_readonly[viewport1-history-revision]" --deselect="tests/test_research_browser.py::test_history_real_result_original_problem_native_new_tab_restart_and_readonly[viewport1-history-same]" --deselect="tests/test_research_browser.py::test_fixed_task_and_history_never_replay_real_pending_source_intent[source-approvals]" --deselect="tests/test_research_browser.py::test_fixed_task_and_history_never_replay_real_pending_source_intent[source-tasks]" --deselect="tests/test_research_browser.py::test_history_real_43_tasks_inclusive_pages_no_gaps_duplicates_or_lost_anchor[history-pages]" --deselect="tests/test_research_browser.py::test_late_real_source_unavailable_200_cannot_overwrite_new_problem[draft]" --deselect="tests/test_research_browser.py::test_late_real_source_unavailable_200_cannot_overwrite_new_problem[saved]" --deselect="tests/test_research_browser.py::test_unavailable_historical_body_preserves_original_readonly_problem_and_navigation[history-revision]" --deselect="tests/test_research_browser.py::test_current_real_cross_owner404_remains_visible_and_clears_private_content" --deselect="tests/test_research_browser.py::test_history_client_validation_rejects_mismatched_task_flags_and_bad_navigation[history-same]" --deselect="tests/test_research_browser.py::test_fixed_current_task_refresh_becomes_historical_with_server_truth[revision]" --deselect="tests/test_research_browser.py::test_fixed_current_task_refresh_becomes_historical_with_server_truth[task]" --deselect="tests/test_research_browser.py::test_invalid_or_ambiguous_task_url_never_falls_back_to_editable_current_problem" --deselect="tests/test_research_browser.py::test_formula_real_ui_save_snapshot_confirm_actual_return_and_reopen[viewport0]" --deselect="tests/test_research_browser.py::test_formula_real_ui_save_snapshot_confirm_actual_return_and_reopen[viewport1]" --deselect="tests/test_research_browser.py::test_formula_empty_structure_is_real_saved_draft_and_not_executable" --deselect="tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[little-0]" --deselect="tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[little-1]" --deselect="tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[mm1-0]" --deselect="tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[mm1-1]" --deselect="tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[thermal-rc-0]" --deselect="tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[thermal-rc-1]" --deselect="tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[local-0]" --deselect="tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[local-1]" --deselect="tests/test_research_browser.py::test_formula_lost_actual_post_receipt_reopens_and_recovers_same_key_ref_without_second_task" --deselect="tests/test_research_browser.py::test_late_actual_formula_post_ack_cannot_replace_new_formula_or_problem[draft]" --deselect="tests/test_research_browser.py::test_late_actual_formula_post_ack_cannot_replace_new_formula_or_problem[saved]" --deselect="tests/test_research_browser.py::test_formula_old_real_post_success_after_logout_cannot_restore_private_results" --deselect="tests/test_research_browser.py::test_formula_explicit_refresh_does_not_mix_another_window_revision_into_old_problem" --deselect="tests/test_research_browser.py::test_formula_real_history_native_tab_original_snapshot_result_time_and_readonly[revision]" --deselect="tests/test_research_browser.py::test_formula_real_history_native_tab_original_snapshot_result_time_and_readonly[new-task]" --deselect="tests/test_research_browser.py::test_formula_fixed_or_historical_view_keeps_genuine_pending_intent_without_any_post[formula-checks]" --deselect="tests/test_research_browser.py::test_formula_fixed_or_historical_view_keeps_genuine_pending_intent_without_any_post[source-approvals]" --deselect="tests/test_research_browser.py::test_formula_fixed_or_historical_view_keeps_genuine_pending_intent_without_any_post[source-tasks]" --deselect="tests/test_research_browser.py::test_formula_late_actual_result_access_error_cannot_clear_new_saved_problem[401]" --deselect="tests/test_research_browser.py::test_formula_late_actual_result_access_error_cannot_clear_new_saved_problem[404]" --deselect="tests/test_research_browser.py::test_formula_actual_auth503_preserves_all_editor_fields_and_real_pending" --deselect="tests/test_research_browser.py::test_formula_real_source_reader_keeps_old_revision_and_stop_policy_but_hides_withdrawn_result" --deselect="tests/test_research_browser.py::test_formula_client_canonical_bounds_and_attestation_guards_from_actual_http_record" --deselect="tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[normal]" --deselect="tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[abort]" --deselect="tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[missing-ref]" --deselect="tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[wrong-digest]" --deselect="tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[wrong-task]" --deselect="tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[wrong-ref]" --deselect="tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[other-real-run]" --deselect="tests/test_research_browser.py::test_formula_ack_metadata401_confirms_current_auth_loss_without_retiring_unknown_key[current-logout]" --deselect="tests/test_research_browser.py::test_formula_ack_metadata401_confirms_current_auth_loss_without_retiring_unknown_key[restored-session]" --deselect="tests/test_research_browser.py::test_formula_ack_metadata401_confirms_current_auth_loss_without_retiring_unknown_key[new-draft]" --deselect="tests/test_research_browser.py::test_formula_ack_metadata401_confirms_current_auth_loss_without_retiring_unknown_key[private-scope-changed]" --deselect="tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[account-switch]" --deselect="tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[same-owner-wrong-task]" --deselect="tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[same-owner-new-draft]" --deselect="tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[restored-owner]" --deselect="tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[late-root-new-draft]" --deselect="tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[late-root-private-scope]" --deselect="tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[credential-conflict]" --deselect="tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[same-owner-dual]" --deselect="tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[restored-conflict]" --deselect="tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[stale-conflict-draft]" --deselect="tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[stale-conflict-private-scope]" --deselect="tests/test_research_browser.py::test_new_research_without_task_selector_keeps_real_create_and_save" --deselect="tests/test_research_browser.py::test_current_main_private_problem_xss_auth503_draft_and_real401_clear" --deselect="tests/test_research_browser.py::test_native_plan_actual_closed_preview_discloses_exact_input_without_confirm_or_model" --deselect="tests/test_research_browser.py::test_native_plan_late_actual_closed_preview_never_replaces_new_draft_or_private_scope[new-draft]" --deselect="tests/test_research_browser.py::test_native_plan_late_actual_closed_preview_never_replaces_new_draft_or_private_scope[logout]" --deselect="tests/test_research_browser.py::test_native_plan_real_https_browser_journey[saved]" --deselect="tests/test_research_browser.py::test_native_plan_real_https_browser_journey[lost-ack]" --deselect="tests/test_research_browser.py::test_native_plan_real_https_browser_journey[late-saved-ack]" --deselect="tests/test_research_browser.py::test_native_plan_real_https_browser_journey[account-switch]" --deselect="tests/test_research_browser.py::test_native_plan_terminal_known_outcome_releases_only_original_intent[invalid-body]" --deselect="tests/test_research_browser.py::test_native_plan_terminal_known_outcome_releases_only_original_intent[saved]" --deselect="tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[not-sent]" --deselect="tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[unknown-usage]" --deselect="tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cleanup-uncertain]" --deselect="tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cancel-before]" --deselect="tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cancel-after]" --deselect="tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[late-B]" --deselect="tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[wrong-ref]" --deselect="tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cross-owner]" --deselect="tests/test_research_browser.py::test_method_draft_manual_editor_starts_blank_and_requires_actual_references" --deselect="tests/test_research_browser.py::test_method_draft_actual_old_source_to_current_manual_draft_and_readonly_history" --deselect="tests/test_research_browser.py::test_method_draft_reads_actual_runtime_plan_lead_without_prefilling_or_execution" --deselect="tests/test_research_browser.py::test_method_draft_real_late_history_keeps_new_editor_and_private_clear[new-editor]" --deselect="tests/test_research_browser.py::test_method_draft_real_late_history_keeps_new_editor_and_private_clear[logout]" --deselect="tests/test_research_browser.py::test_method_draft_plan_reselection_matches_visible_current_choices" --deselect="tests/test_research_browser.py::test_method_draft_formula_picker_distinguishes_same_revision_original_results" --deselect="tests/test_research_browser.py::test_method_draft_actual_main_old_source_new_problem_save_and_reopen" --deselect="tests/test_research_browser.py::test_method_draft_actual_main_conflict_and_unknown_recovery[cas]" --deselect="tests/test_research_browser.py::test_method_draft_actual_main_conflict_and_unknown_recovery[lost-ack]" --deselect="tests/test_research_browser.py::test_method_draft_actual_main_conflict_and_unknown_recovery[lost-get]" --deselect="tests/test_research_browser.py::test_method_draft_actual_main_saved_formula_original_identity_and_outcomes" --deselect="tests/test_research_browser.py::test_method_draft_actual_main_second_catalog_page_preserves_current_form_and_pending" --deselect="tests/test_research_browser.py::test_source_history_actual_main_closed_collection_keeps_existing_readable" -m "not e2e and not slow and not requires_internet and not requires_llm" -q
	$(BACKEND_PYTEST) tests/test_research_browser.py::test_new_research_without_task_selector_keeps_real_create_and_save tests/test_research_browser.py::test_current_main_private_problem_xss_auth503_draft_and_real401_clear tests/test_research_browser.py::test_native_plan_actual_closed_preview_discloses_exact_input_without_confirm_or_model 'tests/test_research_browser.py::test_native_plan_late_actual_closed_preview_never_replaces_new_draft_or_private_scope[new-draft]' 'tests/test_research_browser.py::test_native_plan_late_actual_closed_preview_never_replaces_new_draft_or_private_scope[logout]' 'tests/test_research_browser.py::test_native_plan_terminal_known_outcome_releases_only_original_intent[invalid-body]' 'tests/test_research_browser.py::test_native_plan_terminal_known_outcome_releases_only_original_intent[saved]' 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[not-sent]' 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[unknown-usage]' 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cleanup-uncertain]' 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cancel-before]' 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cancel-after]' 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[late-B]' 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[wrong-ref]' 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cross-owner]' tests/test_research_browser.py::test_method_draft_manual_editor_starts_blank_and_requires_actual_references tests/test_research_browser.py::test_method_draft_actual_old_source_to_current_manual_draft_and_readonly_history tests/test_research_browser.py::test_method_draft_reads_actual_runtime_plan_lead_without_prefilling_or_execution 'tests/test_research_browser.py::test_method_draft_real_late_history_keeps_new_editor_and_private_clear[new-editor]' 'tests/test_research_browser.py::test_method_draft_real_late_history_keeps_new_editor_and_private_clear[logout]' tests/test_research_browser.py::test_method_draft_plan_reselection_matches_visible_current_choices tests/test_research_browser.py::test_method_draft_formula_picker_distinguishes_same_revision_original_results tests/test_research_browser.py::test_method_draft_actual_main_old_source_new_problem_save_and_reopen 'tests/test_research_browser.py::test_method_draft_actual_main_conflict_and_unknown_recovery[cas]' 'tests/test_research_browser.py::test_method_draft_actual_main_conflict_and_unknown_recovery[lost-ack]' 'tests/test_research_browser.py::test_method_draft_actual_main_conflict_and_unknown_recovery[lost-get]' tests/test_research_browser.py::test_method_draft_actual_main_saved_formula_original_identity_and_outcomes tests/test_research_browser.py::test_method_draft_actual_main_second_catalog_page_preserves_current_form_and_pending tests/test_research_browser.py::test_source_history_actual_main_closed_collection_keeps_existing_readable -p no:logging -m "not e2e and not slow and not requires_internet and not requires_llm" -q

test-fast:
	$(PYTEST) -m "not e2e" -q

test-all:
	$(PYTEST) -v

openapi-env:
	uv venv --clear --python 3.11 $(ROOT)/.venv-openapi
	$(ROOT)/.venv-openapi/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 11), sys.version'
	uv pip install --python $(ROOT)/.venv-openapi/bin/python -r $(ROOT)/web/backend/requirements.txt
	uv pip install --python $(ROOT)/.venv-openapi/bin/python -r $(ROOT)/scripts/requirements-types.txt

openapi-generate:
	PYTHONPATH=$(ROOT)/web/backend:$(PACKAGE_PYTHONPATH) $(OPENAPI_PY) $(ROOT)/scripts/openapi_artifact.py --write

openapi-check:
	PYTHONPATH=$(ROOT)/web/backend:$(PACKAGE_PYTHONPATH) $(OPENAPI_PY) $(ROOT)/scripts/openapi_artifact.py --check

types-check:
	PY=$(TYPES_PY) bash scripts/check_ts_types.sh

python-syntax-check:
	$(OPENAPI_PY) -I $(ROOT)/scripts/check_python_syntax.py

llm-scaling-env:
	uv venv --clear --python 3.11 $(LLM_SCALING_DIR)/.venv
	uv pip install --python $(LLM_SCALING_DIR)/.venv/bin/python -r $(LLM_SCALING_DIR)/requirements-generator.txt

llm-scaling-generate:
	$(LLM_SCALING_PY) $(LLM_SCALING_DIR)/run_validation.py --write
	$(LLM_SCALING_PY) $(LLM_SCALING_DIR)/cross_source_alpha_comparison.py --write

llm-scaling-check:
	$(LLM_SCALING_PY) $(LLM_SCALING_DIR)/run_validation.py --check
	$(LLM_SCALING_PY) $(LLM_SCALING_DIR)/cross_source_alpha_comparison.py --check

verify-release:
	$(MAKE) python-syntax-check
	$(MAKE) openapi-check
	$(MAKE) types-check
	$(MAKE) llm-scaling-check
	$(MAKE) test-fast
	cd web/backend && $(BACKEND_PYTEST) --ignore=tests/test_formal_main_admission.py --ignore=tests/test_formal_main_source_supervisor.py --ignore=tests/test_research_financial_import.py --ignore=tests/test_formal_model_startup.py --ignore=tests/acceptance/test_source_history_fixture_current15.py --ignore=tests/test_research_financial_registries.py --ignore=tests/test_research_source_origin_history.py --ignore=tests/test_research_evidence_method_plan.py --ignore=tests/test_research_evidence_method_native.py --ignore=tests/test_plan_runtime_transport.py --ignore=tests/test_research_native_browser_service.py --ignore=tests/test_native_live_grant.py --ignore=tests/test_formal_native_plan_supervisor.py --ignore=tests/test_research_financial_execution_v2.py --ignore=tests/test_research_financial_results_v2.py --ignore=tests/test_source_sec_access_lifecycle.py --ignore=tests/test_source_document_raw_lifecycle.py --ignore=tests/test_formal_main_history_read_borrow.py --ignore=tests/test_source_document_cached_history.py --ignore=tests/test_financial_limit_observer.py --ignore=tests/test_research_method_drafts.py --deselect="web/backend/tests/test_research_native_plan.py::test_native_closed_allows_cost_preview_without_cash_or_funding_and_keeps_saved_question" --deselect="web/backend/tests/test_research_native_plan.py::test_native_actual_http_worker_single_requests_typed_saved_ref_no_cap_as_cash" --deselect="web/backend/tests/test_research_native_plan.py::test_native_preconnect_failure_is_before_consume_releases_reserved_hold" --deselect="web/backend/tests/test_research_native_plan.py::test_native_json_authority_and_foreign_types_cannot_install" --deselect="web/backend/tests/test_research_native_plan.py::test_native13_rows_and_shared_ledger_default_deny_without_scope[ordinary]" --deselect="web/backend/tests/test_research_native_plan.py::test_native13_rows_and_shared_ledger_default_deny_without_scope[private]" --deselect="web/backend/tests/test_research_native_plan.py::test_native_actual_owned_late_return_books_cost_without_reviving_body[cancel]" --deselect="web/backend/tests/test_research_native_plan.py::test_native_actual_owned_late_return_books_cost_without_reviving_body[delete]" --deselect="web/backend/tests/test_research_native_plan.py::test_native_owned_close_failure_keeps_booked_result_and_quarantines_resource" --deselect="web/backend/tests/test_research_native_plan.py::test_native_first_write_ambiguous_never_retries_and_keeps_held" --deselect="web/backend/tests/test_research_native_plan.py::test_native_retired_runtime_permit_cannot_retain_resource_sending_authority" --deselect="web/backend/tests/test_research_native_plan.py::test_review_pending_close_after_real_response_books_and_retires_owned_return" --deselect="web/backend/tests/test_research_native_plan.py::test_review_native_write_rejects_unrelated_or_unproduced_financial_changes[fake]" --deselect="web/backend/tests/test_research_native_plan.py::test_review_native_write_rejects_unrelated_or_unproduced_financial_changes[unrelated_owner]" --deselect="web/backend/tests/test_research_native_plan.py::test_review_native_write_rejects_unrelated_or_unproduced_financial_changes[actual_owner_noop]" --deselect="web/backend/tests/test_research_native_plan.py::test_review_native_write_rejects_unrelated_or_unproduced_financial_changes[money_wrapper_noop]" --deselect="web/backend/tests/test_research_native_plan.py::test_review_retired_native_permit_preview_is_closed_without_reading_balance" --deselect="web/backend/tests/test_research_native_plan.py::test_review_unknown_cleanup_preserves_every_execution_and_financial_field" --deselect="web/backend/tests/test_research_native_plan.py::test_review_funding_owner_binding_preserves_other_registered_accounts_closed_preview" --deselect="web/backend/tests/test_research_native_preowned.py::test_preowned_real_get_socket_close_after_physical_close_is_not_clean" --deselect="web/backend/tests/test_research_native_preowned.py::test_clean_low_balance_keeps_same_resource_for_new_legal_attempt" --deselect="web/backend/tests/test_research_native_preowned.py::test_allocated_connection_failure_is_owned_and_clean_retry_uses_same_resource" --deselect="web/backend/tests/test_research_native_preowned.py::test_all_core_retirements_precede_hook_and_flight_release_after_close_fault" --deselect="web/backend/tests/test_research_native_preowned.py::test_unreturned_allocated_socket_close_failure_keeps_original_error_and_uncertainty" --deselect="web/backend/tests/test_research_native_preowned.py::test_retire_hook_never_accepts_a_status_dto_as_clean" --deselect="web/backend/tests/test_research_native_schema_v13.py::test_real_old12_offline13_preserves_ledger_fixture_result_ref_time_newprocess" --deselect="web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[journal]" --deselect="web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[rebuild]" --deselect="web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[resource]" --deselect="web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[marker]" --deselect="web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[before-commit]" --deselect="web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[after-commit]" --deselect="web/backend/tests/test_research_plan_schema_v12.py::test_real_complete11_to12_same_inode_formula_ref_time_and_old_source_permission" --deselect="web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[journal]" --deselect="web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[rebuild]" --deselect="web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[resource]" --deselect="web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[marker]" --deselect="web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[before-commit]" --deselect="web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[after-commit]" -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_formal_main_admission.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_formal_main_source_supervisor.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_research_financial_import.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_formal_model_startup.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/acceptance/test_source_history_fixture_current15.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_research_financial_registries.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_research_source_origin_history.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_research_evidence_method_plan.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_research_evidence_method_native.py --deselect="web/backend/tests/test_research_evidence_method_native.py::test_actual_http_stop_after_owned_return_keeps_original_fee_without_late_body[delete]" -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_plan_runtime_transport.py --deselect="web/backend/tests/test_plan_runtime_transport.py::test_actual_late_return_original_credential_books_fee_without_restoring_body[cancel]" --deselect="web/backend/tests/test_plan_runtime_transport.py::test_actual_late_return_original_credential_books_fee_without_restoring_body[delete]" --deselect="web/backend/tests/test_plan_runtime_transport.py::test_evidence_runtime_first_socket_entry_is_recorded_once_and_never_refunded[partial]" -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_research_native_browser_service.py --deselect="web/backend/tests/test_research_native_browser_service.py::test_real_authority_birth_failure_can_retry_without_adopting_orphan_resources" -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_native_live_grant.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_formal_native_plan_supervisor.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_research_financial_execution_v2.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_research_financial_results_v2.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_source_sec_access_lifecycle.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_source_document_raw_lifecycle.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_formal_main_history_read_borrow.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_source_document_cached_history.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_financial_limit_observer.py -p no:logging -q
	cd web/backend && $(BACKEND_PYTEST) tests/test_research_method_drafts.py --deselect=web/backend/tests/test_research_method_drafts.py::test_actual_native_plan_lead_is_bound_without_promoting_literature_or_formula -p no:logging -q
	cd packages/guarded-llm && $(PYTEST) tests -q
	cd packages/cross-judge && $(PYTEST) tests -q
	cd packages/reject-aware-critic && $(PYTEST) tests -q
	cd packages/soc-pipeline && $(PYTEST) tests -q -m "not slow"
	$(MAKE) test-retrieval-contract
	$(MAKE) test-release-contracts
	$(MAKE) test-frontend-node
	$(MAKE) test-browser-contracts
	$(MAKE) test-evidence-method-browser-contract
	$(MAKE) test-financial-registry-browser-contract
	$(MAKE) test-financial-scenario-browser-contract
	cd web/phase-detector && pnpm lint && pnpm build
