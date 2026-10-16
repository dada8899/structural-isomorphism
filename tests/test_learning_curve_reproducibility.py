"""Numerical regression probes for the versioned learning-curve estimator."""
from __future__ import annotations

import csv
import importlib.util
import math
from pathlib import Path
import shutil
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def lc():
    path = ROOT / "packages/soc-pipeline/src/soc_pipeline/learning_curve.py"
    spec = importlib.util.spec_from_file_location("learning_curve_reproducibility", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _narrow_series(model="pythia-2.8b"):
    path = ROOT / "v4/validation/llm-scaling/raw/pythia_checkpoints_combined.csv"
    with path.open() as stream:
        rows = [row for row in csv.DictReader(stream) if row["model"] == model]
    return np.array([float(row["compute_flops"]) for row in rows]), np.array([float(row["loss"]) for row in rows])


@pytest.mark.parametrize("parameters", [(400.0, .155, 1.7), (25.0, .05, .1), (1e6, .3, 2.0)])
def test_wide_range_recovers_known_parameters_and_predictions(lc, parameters):
    compute = np.logspace(14, 24, 40)
    observed = lc.power_law_with_floor(compute, *parameters)
    fit = lc.fit_learning_curve(compute, observed)
    assert fit.error is None
    np.testing.assert_allclose([fit.A, fit.alpha, fit.L_inf], parameters, rtol=1e-6, atol=1e-8)
    np.testing.assert_allclose(lc.power_law_with_floor(compute, fit.A, fit.alpha, fit.L_inf), observed, rtol=1e-10, atol=1e-10)
    assert not fit.extra["fit_diagnostics"]["bound_hit"]


def test_canonical_row_order_is_exact_for_the_narrow_regression(lc):
    compute, observed = _narrow_series()
    order = np.random.default_rng(9).permutation(len(compute))
    reference = lc.fit_learning_curve(compute, observed)
    for permutation in (np.arange(len(compute))[::-1], order):
        assert lc.fit_learning_curve(compute[permutation], observed[permutation]).to_dict() == reference.to_dict()


@pytest.mark.parametrize("direction", [-math.inf, math.inf])
def test_one_ulp_input_perturbation_does_not_reproduce_raw_prefactor_drift(lc, direction):
    compute, observed = _narrow_series()
    reference = lc.fit_learning_curve(compute, observed)
    perturbed = lc.fit_learning_curve(np.nextafter(compute, direction), observed)
    assert reference.error is None and perturbed.error is None
    # Tighter than the unchanged artifact relative tolerance (1e-4).
    np.testing.assert_allclose([perturbed.A, perturbed.alpha, perturbed.L_inf], [reference.A, reference.alpha, reference.L_inf], rtol=1e-6, atol=1e-10)
    np.testing.assert_allclose(lc.power_law_with_floor(compute, perturbed.A, perturbed.alpha, perturbed.L_inf), lc.power_law_with_floor(compute, reference.A, reference.alpha, reference.L_inf), rtol=1e-9, atol=1e-9)


@pytest.mark.parametrize("model", ["pythia-1.4b", "pythia-2.8b"])
def test_narrow_fit_at_original_A_bound_does_not_publish_spurious_standard_errors(lc, model):
    compute, observed = _narrow_series(model)
    fit = lc.fit_learning_curve(compute, observed)
    diagnostic = fit.extra["fit_diagnostics"]
    assert fit.error is None
    assert 1e-12 <= fit.A <= 1e12
    assert diagnostic["original_A_bounds"] == [1e-12, 1e12]
    assert diagnostic["bound_hit"] and "A" in diagnostic["active_bounds"]
    assert diagnostic["parameter_identifiability"] == "weak_or_unestablished"
    assert diagnostic["covariance_status"] == "not_reported_active_bound"
    assert fit.A_se is fit.alpha_se is fit.L_inf_se is None


def test_custom_original_A_bounds_are_not_replaced_by_centered_amplitude_bounds(lc):
    compute = np.logspace(17, 22, 24)
    observed = lc.power_law_with_floor(compute, 400, .155, 1.7)
    fit = lc.fit_learning_curve(compute, observed, A_bounds=(1.0, 10.0))
    assert fit.error is None
    assert 1 <= fit.A <= 10
    assert fit.extra["fit_diagnostics"]["original_A_bounds"] == [1.0, 10.0]


def test_narrow_profile_with_different_valid_initialization_remains_bound_qualified(lc):
    compute, observed = _narrow_series()
    reference = lc.fit_learning_curve(compute, observed)
    alpha0, floor0 = .1, 1.3
    A0 = (observed[0] - floor0) * compute[0] ** alpha0
    alternative = lc.fit_learning_curve(compute, observed, initial_guess=(A0, alpha0, floor0))
    assert alternative.error is None
    np.testing.assert_allclose([alternative.A, alternative.alpha, alternative.L_inf], [reference.A, reference.alpha, reference.L_inf], rtol=1e-6, atol=1e-9)
    assert alternative.extra["fit_diagnostics"]["bound_hit"]


def test_nearly_constant_range_is_not_reported_as_identified(lc):
    compute = 1e20 * (1 + np.linspace(0, 1e-8, 20))
    observed = 2 + np.random.default_rng(5).normal(0, 1e-3, 20)
    fit = lc.fit_learning_curve(compute, observed)
    assert fit.error is None
    diagnostic = fit.extra["fit_diagnostics"]
    assert diagnostic["parameter_identifiability"] == "weak_or_unestablished"
    assert fit.A_se is fit.alpha_se is fit.L_inf_se is None


def test_constant_compute_rejects_the_unidentifiable_domain(lc):
    fit = lc.fit_learning_curve([1e20] * 5, [1, 2, 3, 4, 5])
    assert fit.error is not None and "constant compute" in fit.error


def test_analytic_jacobian_has_an_independent_central_difference_control(lc, monkeypatch):
    original = lc.least_squares
    controls = []
    starts = []

    def capture(fun, initial, **kwargs):
        starts.append(float(initial[1]))
        numerical = np.column_stack([
            (fun(initial + np.eye(3)[index] * 1e-5) - fun(initial - np.eye(3)[index] * 1e-5)) / 2e-5
            for index in range(3)
        ])
        controls.append((kwargs["jac"](initial), numerical))
        assert kwargs["bounds"][0][0] == math.log(1e-12)
        assert kwargs["bounds"][1][0] == math.log(1e12)
        return original(fun, initial, **kwargs)

    monkeypatch.setattr(lc, "least_squares", capture)
    compute = np.logspace(0, 6, 20)
    observed = lc.power_law_with_floor(compute, 400, .155, 1.7)
    fit = lc.fit_learning_curve(compute, observed)
    assert fit.error is None
    assert starts == [.1, .3, .6, 1.0]
    for analytic, numerical in controls:
        np.testing.assert_allclose(analytic, numerical, rtol=1e-5, atol=1e-8)


def test_stable_bound_solution_does_not_remove_the_narrow_profile_ambiguity(lc):
    from scipy.optimize import lsq_linear
    compute, observed = _narrow_series()
    fit = lc.fit_learning_curve(compute, observed)
    reference = lc.power_law_with_floor(compute, fit.A, fit.alpha, fit.L_inf)
    best_sse = float(np.sum((observed - reference) ** 2))
    log_C0 = float(np.mean(np.log(compute)))
    amplitudes = []
    for alpha in (.1, .6):
        scale = math.exp(-alpha * log_C0)
        power = np.exp(-alpha * (np.log(compute) - log_C0))
        result = lsq_linear(np.column_stack((power, np.ones(len(compute)))), observed,
                            bounds=([1e-12 * scale, 0], [1e12 * scale, 10]), tol=1e-12)
        amplitudes.append(result.x[0] / scale)
        sse = float(np.sum((observed - (power * result.x[0] + result.x[1])) ** 2))
        assert abs(sse - best_sse) / best_sse < 1e-4
    assert max(amplitudes) / min(amplitudes) > 1e6
    assert fit.extra["fit_diagnostics"]["parameter_identifiability"] == "weak_or_unestablished"


@pytest.mark.parametrize("bounds", [(0, 10), (-1, 10), (10, 1), (1, math.inf)])
def test_invalid_A_bounds_do_not_enter_the_optimizer(lc, bounds):
    fit = lc.fit_learning_curve([1, 2, 3, 4], [4, 3, 2, 1], A_bounds=bounds)
    assert fit.error is not None and "invalid_fit_domain" in fit.error


def test_derived_artifact_binding_and_pixel_tampering_are_checked(tmp_path, monkeypatch):
    directory = ROOT / "v4/validation/llm-scaling"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("cross_source_reproducibility", directory / "cross_source_alpha_comparison.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not module._assert_generator_environment.__globals__["generator_environment_matches"]():
        pytest.skip("the strict rendering closure is tested in the locked generator environment")
    for name in ("results.json", "results_lambada.json", "results_lambada_v2.json", "cross_source_summary.json", "pythia_12b_cross_source.json"):
        shutil.copyfile(directory / name, tmp_path / name)
    figures = tmp_path / "figures"
    figures.mkdir()
    image_path = figures / "cross_source_alpha.png"
    shutil.copyfile(directory / "figures/cross_source_alpha.png", image_path)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "FIG_DIR", figures)
    module._check_outputs()
    from PIL import Image, PngImagePlugin
    with Image.open(image_path) as original:
        tampered = original.convert("RGBA")
        metadata = PngImagePlugin.PngInfo()
        for name, value in original.text.items():
            metadata.add_text(name, value)
    pixel = tampered.getpixel((0, 0))
    tampered.putpixel((0, 0), ((pixel[0] + 1) % 256, *pixel[1:]))
    tampered.save(image_path, pnginfo=metadata)
    with pytest.raises(RuntimeError, match="locked pixel output"):
        module._check_outputs()


def _load_lambada_consumer(filename):
    path = ROOT / "v4/validation/llm-scaling" / filename
    name = "consumer_" + path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("filename", ["run_validation_lambada.py", "run_validation_lambada_v2.py"])
def test_real_lambada_consumers_render_unavailable_uncertainty_without_touching_source_outputs(
    filename, tmp_path, monkeypatch,
):
    import json
    module = _load_lambada_consumer(filename)
    directory = ROOT / "v4/validation/llm-scaling"
    originals = {name: (directory / name).read_bytes() for name in (
        "results_lambada.json", "summary_lambada.md",
        "results_lambada_v2.json", "summary_lambada_v2.md",
    )}
    results = tmp_path / "results.json"
    summary = tmp_path / "summary.md"
    monkeypatch.setattr(module, "RESULTS_OUT", results)
    monkeypatch.setattr(module, "SUMMARY_OUT", summary)
    module.main()
    payload = json.loads(results.read_text())
    markdown = summary.read_text()
    assert len(payload["per_size_fits"]) == 8
    missing = 0
    for name, fit in payload["per_size_fits"].items():
        line = next(line for line in markdown.splitlines() if line.startswith(f"| {name} |"))
        standard_error_cell = line.split("|")[3].strip()
        assert line.split("|")[6].strip() == f"{fit['R2']:.4f}"
        if fit["alpha_se"] is None:
            missing += 1
            diagnostic = fit["extra"]["fit_diagnostics"]
            assert standard_error_cell.startswith("unavailable (")
            assert diagnostic["covariance_status"] in standard_error_cell
            assert diagnostic["parameter_identifiability"] in standard_error_cell
            for boundary in diagnostic["active_bounds"]:
                assert boundary in standard_error_cell
        else:
            assert standard_error_cell == f"{fit['alpha_se']:.4f}"
    assert missing > 0
    assert '"alpha_se": null' in results.read_text()
    for name, before in originals.items():
        assert (directory / name).read_bytes() == before


@pytest.mark.parametrize("filename", ["run_validation_lambada.py", "run_validation_lambada_v2.py"])
@pytest.mark.parametrize("value, expected", [(.123456, "0.1235"), (0.0, "0.0000")])
def test_lambada_numeric_standard_error_control_is_not_hidden(filename, value, expected):
    module = _load_lambada_consumer(filename)
    assert module._format_standard_error({"alpha_se": value}) == expected


@pytest.mark.parametrize("filename", ["run_validation_lambada.py", "run_validation_lambada_v2.py"])
def test_lambada_render_failure_leaves_both_previous_outputs_intact(
    filename, tmp_path, monkeypatch,
):
    module = _load_lambada_consumer(filename)
    results = tmp_path / "results.json"
    summary = tmp_path / "summary.md"
    results.write_text("previous JSON")
    summary.write_text("previous Markdown")
    monkeypatch.setattr(module, "RESULTS_OUT", results)
    monkeypatch.setattr(module, "SUMMARY_OUT", summary)

    def broken_format(_):
        raise TypeError("forced rendering failure")

    monkeypatch.setattr(module, "_format_standard_error", broken_format)
    with pytest.raises(TypeError, match="forced rendering failure"):
        module.main()
    assert results.read_text() == "previous JSON"
    assert summary.read_text() == "previous Markdown"


@pytest.mark.parametrize("fields, expected", [
    ({"R2": .812345, "r_squared": .1}, .812345),
    ({"R2": 0.0, "r_squared": .7}, 0.0),
    ({"R2": -.25, "r_squared": .7}, -.25),
    ({"r_squared": .456789}, .456789),
])
def test_lambada_v1_R2_rendering_matches_canonical_or_legacy_json(
    fields, expected, tmp_path, monkeypatch,
):
    """Controlled consumer values, not new estimates for the real dataset."""
    import json
    from types import SimpleNamespace
    module = _load_lambada_consumer("run_validation_lambada.py")

    def controlled_fit(*args, **kwargs):
        return SimpleNamespace(alpha=.2, alpha_se=.025, A=10.0, L_inf=1.0, **fields)

    monkeypatch.setattr(module.lc, "fit_learning_curve", controlled_fit)
    results = tmp_path / "results.json"
    summary = tmp_path / "summary.md"
    monkeypatch.setattr(module, "RESULTS_OUT", results)
    monkeypatch.setattr(module, "SUMMARY_OUT", summary)
    module.main()
    payload = json.loads(results.read_text())
    markdown = summary.read_text()
    assert len(payload["per_size_fits"]) == 8
    for name, fit in payload["per_size_fits"].items():
        assert fit.get("R2", fit.get("r_squared")) == expected
        line = next(line for line in markdown.splitlines() if line.startswith(f"| {name} |"))
        assert line.split("|")[6].strip() == f"{expected:.4f}"
        assert line.split("|")[3].strip() == "0.0250"
