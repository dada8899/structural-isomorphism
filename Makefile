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
PACKAGE_PYTHONPATH := $(ROOT)/packages/guarded-llm/src:$(ROOT)/packages/cross-judge/src:$(ROOT)/packages/reject-aware-critic/src:$(ROOT)/packages/soc-pipeline/src
PYTEST := PYTHONPATH=$(PACKAGE_PYTHONPATH) $(PY) -m pytest
BACKEND_PYTEST := PYTHONPATH=$(ROOT)/web/backend:$(PACKAGE_PYTHONPATH) $(PY) -m pytest

FRONTEND_NODE_TESTS := \
	web/frontend/tests/test_analyticsSensitiveRoutes.js \
	web/frontend/tests/test_analyzeTrust.js \
	web/frontend/tests/test_askTrust.js \
	web/frontend/tests/test_buildAnalyzeUrl.js \
	web/frontend/tests/test_historyPrivacy.js \
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
	tests/e2e/test_unified_research_library.py \
	web/tests/e2e/test_thank_you_copy.py

BROWSER_CONTRACT_SECONDARY_WHITESPACE_TESTS := \
	web/tests/e2e/test_secondary_tools_candidate_journeys.py \
	web/tests/e2e/test_whitespace.py

PHASE_REAL_BROWSER_CONTRACT_TESTS := \
	web/tests/e2e/test_phase_auth_real.py

.PHONY: test test-unit test-integration test-e2e test-frontend-node test-browser-contracts test-retrieval-contract test-product-contracts test-release-contracts test-all test-fast openapi-env openapi-generate openapi-check types-check verify-release help

help:
	@echo "Targets:"
	@echo "  test-unit         Run unit tests (offline, < 30s)"
	@echo "  test-integration  Run integration tests (in-process, < 2min)"
	@echo "  test-e2e          Run e2e tests (live network, may be flaky)"
	@echo "  test-frontend-node  Run every vanilla frontend Node contract"
	@echo "  test-browser-contracts  Run the hard browser contract suite"
	@echo "  test-retrieval-contract  Validate retrieval dataset, determinism, and OOS policy"
	@echo "  test-product-contracts  Validate public controls, human-review tooling, and research claims"
	@echo "  test-release-contracts  Run every offline root contract with backend imports enabled"
	@echo "  test-fast         test-unit + test-integration (no network)"
	@echo "  test-all          Everything"
	@echo "  openapi-env       Explicitly create the release-pinned OpenAPI environment"
	@echo "  openapi-generate  Update OpenAPI using release-target backend dependencies"
	@echo "  openapi-check     Check OpenAPI using release-target backend dependencies"
	@echo "  types-check       Regenerate API TypeScript in a temp file and compare exactly"
	@echo "  verify-release    Authoritative offline release gate across backend, packages, retrieval, and Phase"
	@echo "  test              Alias for test-fast"

test: test-fast

test-unit:
	$(PYTEST) v4/tests/sanity -m sanity -q

test-integration:
	$(PYTEST) v4/tests/integration v4/product/d1_phase_detector/tests v4/product/d1_phase_detector/api/tests -q

test-e2e:
	$(PYTEST) tests/e2e -m e2e -v

test-frontend-node:
	@set -eu; for test_file in $(FRONTEND_NODE_TESTS); do node "$$test_file"; done

test-browser-contracts:
	$(PYTEST) $(BROWSER_CONTRACT_SEARCH_ASK_ANALYZE_PHENOMENON_TESTS) -m "e2e and not requires_internet" -v
	$(PYTEST) $(BROWSER_CONTRACT_DISCOVERY_CLASSES_PAPERS_TESTS) -m "e2e and not requires_internet" -v
	$(PYTEST) $(filter tests/e2e/%,$(BROWSER_CONTRACT_LIBRARY_AUTH_REPORTS_FAVORITES_TESTS)) -m "e2e and not requires_internet" -v
	$(PYTEST) $(filter web/tests/e2e/%,$(BROWSER_CONTRACT_LIBRARY_AUTH_REPORTS_FAVORITES_TESTS)) -m "e2e and not requires_internet" -v
	$(PYTEST) $(BROWSER_CONTRACT_SECONDARY_WHITESPACE_TESTS) -m "e2e and not requires_internet" -v
	$(PYTEST) $(PHASE_REAL_BROWSER_CONTRACT_TESTS) -v

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

verify-release:
	$(MAKE) openapi-check
	$(MAKE) types-check
	$(MAKE) test-fast
	cd web/backend && $(BACKEND_PYTEST) -q
	cd packages/guarded-llm && $(PYTEST) tests -q
	cd packages/cross-judge && $(PYTEST) tests -q
	cd packages/reject-aware-critic && $(PYTEST) tests -q
	cd packages/soc-pipeline && $(PYTEST) tests -q -m "not slow"
	$(MAKE) test-retrieval-contract
	$(MAKE) test-release-contracts
	$(MAKE) test-frontend-node
	$(MAKE) test-browser-contracts
	cd web/phase-detector && pnpm lint && pnpm build
