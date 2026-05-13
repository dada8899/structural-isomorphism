# Contributing to structural-isomorphism

Thanks for your interest. This project welcomes contributions from researchers, engineers, students, and anyone curious about cross-domain validation of self-organized criticality.

## Code of Conduct

This project adheres to the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating you agree to uphold its terms.

## Ways to contribute

- Report bugs via [GitHub Issues](https://github.com/dada8899/structural-isomorphism/issues)
- Suggest features or new validation phases
- Improve documentation, tutorials, or translations
- Submit pull requests for bug fixes or features
- Replicate existing phases on new datasets
- Propose adversarial test cases (pre-registered exponent bands)

## Setup local development

```bash
git clone https://github.com/dada8899/structural-isomorphism.git
cd structural-isomorphism
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev,tutorials]
```

Tests:

```bash
pytest v4/tests/sanity -m sanity -v          # unit tests
pytest v4/tests/integration -v               # integration tests
make test-all                                 # full suite (213 tests)
```

## Pull request workflow

1. Fork the repository and create a topic branch: `git checkout -b feat/<short-desc>`
2. Make your changes with clear commit messages following [Conventional Commits](https://www.conventionalcommits.org/)
3. Add or update tests for your changes
4. Run the full test suite locally and ensure it passes
5. Open a PR against `main` with a clear description of what changed and why
6. Address review feedback promptly

## Style

- Python: PEP 8 enforced by `ruff` and `black`. Type hints encouraged
- Commit scope: `feat(soc-pipeline):`, `fix(d1):`, `docs:`, `test:`, `chore:`
- Documentation: `YYYY-MM-DD` date format in markdown
- One semantic change per commit; one feature per PR

## Good first issues

Look for [good-first-issue](https://github.com/dada8899/structural-isomorphism/labels/good-first-issue) labeled issues. Each comes with a brief, acceptance criteria, and effort estimate.

## Reporting research issues

If you spot a methodological problem with a phase verification or paper:

1. Open an issue with the `research` label
2. Cite specific files/lines and the relevant literature
3. We treat scientific concerns at the highest priority

## Questions

- General questions: [GitHub Discussions](https://github.com/dada8899/structural-isomorphism/discussions)
- Maintainer contact: see GOVERNANCE.md

Thanks for helping us build something useful.
