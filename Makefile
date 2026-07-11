PY := .venv/bin/python
PYTEST := $(PY) -m pytest

.PHONY: test test-unit test-integration test-e2e test-retrieval-contract test-product-contracts test-all test-fast verify-release help

help:
	@echo "Targets:"
	@echo "  test-unit         Run unit tests (offline, < 30s)"
	@echo "  test-integration  Run integration tests (in-process, < 2min)"
	@echo "  test-e2e          Run e2e tests (live network, may be flaky)"
	@echo "  test-retrieval-contract  Validate retrieval dataset, determinism, and OOS policy"
	@echo "  test-product-contracts  Validate public controls, human-review tooling, and research claims"
	@echo "  test-fast         test-unit + test-integration (no network)"
	@echo "  test-all          Everything"
	@echo "  verify-release    Authoritative offline release gate across backend, packages, retrieval, and Phase"
	@echo "  test              Alias for test-fast"

test: test-fast

test-unit:
	$(PYTEST) v4/tests/sanity -m sanity -q

test-integration:
	$(PYTEST) v4/tests/integration v4/product/d1_phase_detector/tests v4/product/d1_phase_detector/api/tests -q

test-e2e:
	$(PYTEST) tests/e2e -m e2e -v

test-retrieval-contract:
	PYTHONPATH=web/backend $(PYTEST) web/backend/tests/test_retrieval_eval_dataset.py -q

test-product-contracts:
	$(PYTEST) tests/test_public_controls.py tests/test_english_review_tool.py tests/test_research_claim_gate.py -q

test-fast:
	$(PYTEST) -m "not e2e" -q

test-all:
	$(PYTEST) -v

verify-release:
	$(MAKE) test-fast
	cd web/backend && ../../$(PYTEST) -q
	cd packages/guarded-llm && ../../$(PYTEST) tests -q
	cd packages/cross-judge && ../../$(PYTEST) tests -q
	cd packages/reject-aware-critic && ../../$(PYTEST) tests -q
	cd packages/soc-pipeline && ../../$(PYTEST) tests -q -m "not slow"
	$(MAKE) test-retrieval-contract
	$(MAKE) test-product-contracts
	cd web/phase-detector && pnpm lint && pnpm build
