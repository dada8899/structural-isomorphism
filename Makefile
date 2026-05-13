PY := .venv/bin/python
PYTEST := $(PY) -m pytest

.PHONY: test test-unit test-integration test-e2e test-all test-fast help

help:
	@echo "Targets:"
	@echo "  test-unit         Run unit tests (offline, < 30s)"
	@echo "  test-integration  Run integration tests (in-process, < 2min)"
	@echo "  test-e2e          Run e2e tests (live network, may be flaky)"
	@echo "  test-fast         test-unit + test-integration (no network)"
	@echo "  test-all          Everything"
	@echo "  test              Alias for test-fast"

test: test-fast

test-unit:
	$(PYTEST) v4/tests/sanity -m sanity -q

test-integration:
	$(PYTEST) v4/tests/integration v4/product/d1_phase_detector/tests v4/product/d1_phase_detector/api/tests -q

test-e2e:
	$(PYTEST) tests/e2e -m e2e -v

test-fast:
	$(PYTEST) -m "not e2e" -q

test-all:
	$(PYTEST) -v
