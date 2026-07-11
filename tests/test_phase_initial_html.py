from scripts.check_phase_initial_html import CONTRACTS, validate_html


def test_each_contract_accepts_complete_initial_html():
    for path, markers in CONTRACTS.items():
        assert validate_html(path, " ".join(markers)) == []


def test_each_contract_reports_every_missing_marker():
    for path, markers in CONTRACTS.items():
        assert validate_html(path, "") == list(markers)
