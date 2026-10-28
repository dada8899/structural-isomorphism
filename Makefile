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
	$(BACKEND_PYTEST) tests --ignore=tests/e2e -m "not e2e and not slow and not requires_internet and not requires_llm" -q

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
	cd web/backend && $(BACKEND_PYTEST) tests/test_research_native_browser_service.py -p no:logging -q
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
