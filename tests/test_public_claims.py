import json
import unicodedata
from pathlib import Path

from scripts.check_public_claims import DEFAULT_INVENTORY, ROOT, _paths, load_inventory, validate


def test_repository_current_public_copy_passes() -> None:
    assert validate(DEFAULT_INVENTORY, ROOT) == []


def test_current_product_surfaces_use_candidate_and_outcome_language() -> None:
    inventory = json.loads(DEFAULT_INVENTORY.read_text(encoding="utf-8"))
    runtime = set(inventory["scope"]["runtime_pages"])
    assert {
        "web/frontend/about.html",
        "web/frontend/tools.html",
        "web/frontend/insights.html",
        "web/frontend/assets/js/insights.js",
    } <= runtime
    assert "39 个已验证" in inventory["forbidden_patterns"]
    assert "已验证同构库" in inventory["forbidden_patterns"]
    assert inventory["forbidden_regex"]


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "page.html").write_text("Plain decision summary. Next: inspect evidence.", encoding="utf-8")
    inventory = {
        "schema_version": "current-public-copy-v1",
        "scope": {"runtime_pages": ["page.html"], "current_documents": [], "excluded_contexts": []},
        "forbidden_patterns": ["verified universal law"],
        "forbidden_regex": [
            r"independent(?:ly)?\s+emerg(?:e|es|ed|ence)",
            r"same\s+law\s+governs",
            r"share(?:s|d|ing)?\s+the\s+same\s+skeleton.{0,80}transfer",
            r"validated\s+on\s+NGSIM",
            r"subclasses.{0,80}all\s+stand",
            r"corroborating\s+the\s+hypothesis",
            r"to\s+rule\s+out.{0,80}artifact",
            r"都是它",
            r"印证.{0,40}假说",
            r"same\s+thing",
            r"structurally\s+equivalent\s+solutions",
        ],
        "adjacent_context_rules": [
            {
                "claim_regex": r"(?:same|shared)\s+mechanism|(?:同一|共同)机制",
                "caveat_regex": r"(?:does|do)\s+not\s+(?:establish|prove)\s+(?:a\s+)?shared\s+mechanism|不能(?:证明|推出)(?:同一|共同)机制",
                "window": 120,
            },
            {
                "claim_regex": r"real[- ]time\s+phase\s+detection|实时.{0,8}状态检测",
                "caveat_regex": r"not\s+real[- ]time|historical|frozen|不是实时|历史|冻结",
                "window": 120,
            },
        ],
        "required_context": [{"path": "page.html", "patterns": ["Next: inspect evidence."]}],
        "context_rules": [{"term": "verified", "allowed": "checksum", "forbidden": "mechanism proof"}],
        "readability_contract": {
            "first_use": "Explain terms.", "two_layers": "Summary then detail.",
            "actionable_states": "Give a next step.", "buttons": "Use user actions.",
            "restatement_test": "State known, uncertain, next."
        },
    }
    path = root / "inventory.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")
    return root, path


def test_forbidden_claim_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    (root / "page.html").write_text("This is a verified universal law. Next: inspect evidence.")
    errors = validate(inventory, root)
    assert any("forbidden public claim" in error for error in errors)


def test_forbidden_claim_variants_fail_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    for claim in ("independently emerged", "independent emergence"):
        (root / "page.html").write_text(f"The pattern shows {claim}. Next: inspect evidence.")
        errors = validate(inventory, root)
        assert any("forbidden public claim regex" in error for error in errors)


def test_rendered_html_and_i18n_attacks_fail_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    attacks = (
        "The <strong>same law</strong> governs all three systems.",
        "The sa<em>me</em> law governs all three systems.",
        "They share the same <em>skeleton</em> and can be transferred.",
    )
    for attack in attacks:
        (root / "page.html").write_text(f"<p>{attack}</p><p>Next: inspect evidence.</p>")
        errors = validate(inventory, root)
        assert any("forbidden public claim regex" in error for error in errors)

    data = json.loads(inventory.read_text())
    data["scope"]["runtime_pages"] = ["copy.json"]
    data["required_context"] = [{"path": "copy.json", "patterns": ["same law"]}]
    inventory.write_text(json.dumps(data))
    (root / "copy.json").write_text(json.dumps({"copy": "The same law governs all systems."}))
    assert any("forbidden public claim regex" in error for error in validate(inventory, root))

    data["required_context"] = [{"path": "copy.json", "patterns": ["same"]}]
    inventory.write_text(json.dumps(data))
    (root / "copy.json").write_text(json.dumps({"a": "The same ", "b": "law governs all systems."}))
    assert any("forbidden public claim regex" in error for error in validate(inventory, root))

    (root / "copy.json").write_text(json.dumps({"a": "The sa", "b": "me law ", "c": "governs all systems."}))
    assert any("forbidden public claim regex" in error for error in validate(inventory, root))

    # Render maps are not limited to a fixed number of adjacent values.
    (root / "copy.json").write_text(json.dumps({
        "a": "The ", "b": "sa", "c": "me ", "d": "la", "e": "w ",
        "f": "governs ", "g": "all ", "h": "systems.",
    }))
    assert any("forbidden public claim regex" in error for error in validate(inventory, root))

    (root / "copy.json").write_text(json.dumps({
        "component": {"segments": ["The ", "same ", "law ", "governs ", "all systems."]}
    }))
    assert any("forbidden public claim regex" in error for error in validate(inventory, root))


def test_unicode_and_hidden_caveat_bypasses_fail_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    attacks = (
        # NFKC compatibility characters must collapse before scanning.
        "Ｔｈｅ ｓａｍｅ ｌａｗ ｇｏｖｅｒｎｓ all systems.",
        # Default-ignorable and soft-hyphen splitters must not break a claim.
        "The sa\u200bme la\u00adw governs all systems.",
        # A visually absent caveat cannot bound a visible claim.
        "<p>They share the same mechanism.<span style='font-size:0'>"
        "They do not establish a shared mechanism.</span></p>",
        "<p>They share the same mechanism.<span style='font-size:0!important'>"
        "They do not establish a shared mechanism.</span></p>",
        "<p>They share the same mechanism.<span style='transform: scale(0)'>"
        "They do not establish a shared mechanism.</span></p>",
        "<p>They share the same mechanism.<span style='position:absolute;left:-9999px'>"
        "They do not establish a shared mechanism.</span></p>",
        # Claim-adjacent caution words are not an explicit denial.
        "<p>Candidate systems share the same mechanism pending publication.</p>",
    )
    for attack in attacks:
        (root / "page.html").write_text("<p>" + attack + "</p><p>Next: inspect evidence.</p>")
        errors = validate(inventory, root)
        assert any(
            marker in error
            for error in errors
            for marker in ("forbidden public claim regex", "missing adjacent caveat")
        ), attack


def test_all_css_and_container_caveat_bypasses_fail_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    wrappers = (
        "style='transform:scaleX(0)'",
        "style='transform:scaleY(.0)'",
        "style='transform:scale3d(1,0,1)'",
        "style='transform:translateX(-9999px)'",
        "style='transform:translate3d(9999px,0,0)'",
        "style='position:fixed;left:-9999px'",
        "style='position:absolute;top:9999px'",
        "style='clip:rect(0,0,0,0)'",
        "style='clip-path:inset(50%)'",
        "style='overflow:hidden;height:.0px'",
        "class='external-css-offscreen'",
        "hidden",
        "aria-hidden='true'",
    )
    for wrapper in wrappers:
        (root / "page.html").write_text(
            "<style>.external-css-offscreen{position:fixed;left:-9999px}</style>"
            "<p>They share the same mechanism.<span " + wrapper + ">"
            "They do not establish a shared mechanism.</span></p>"
            "<p>Next: inspect evidence.</p>"
        )
        assert any("missing adjacent caveat" in error for error in validate(inventory, root)), wrapper


def test_caveat_in_separate_formatting_node_cannot_exempt_claim(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    for tag in ("strong", "em", "code"):
        (root / "page.html").write_text(
            f"<p>They share the same mechanism.<{tag}>"
            f"They do not establish a shared mechanism.</{tag}></p>"
            "<p>Next: inspect evidence.</p>"
        )
        assert any("missing adjacent caveat" in error for error in validate(inventory, root)), tag


def test_claim_split_across_text_nodes_is_unbounded(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    (root / "page.html").write_text(
        "<p>They share the same <em>mechanism</em>.</p>"
        "<p>Next: inspect evidence.</p>"
    )
    assert any("cross-node public claim" in error for error in validate(inventory, root))


def test_public_dependency_closure_finds_nested_js_and_json_claims(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "assets/data").mkdir(parents=True)
    (frontend / "index.html").write_text('<script src="/assets/js/ask.js?v=1"></script>')
    (frontend / "assets/js/ask.js").write_text("fetch('/assets/data/copy.json?v=1')")
    (frontend / "assets/data/copy.json").write_text(json.dumps({"copy": "verified universal law"}))
    errors = validate(inventory, root)
    assert any("assets/data/copy.json" in error for error in errors)


def test_public_dependency_closure_fails_on_missing_local_asset(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text('<script src="/assets/js/missing.js"></script>')
    assert any("missing local dependency" in error for error in validate(inventory, root))


def test_linked_stylesheet_generated_content_claim_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/css").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<link rel="stylesheet" href="/assets/css/runtime.css?v=1">',
        encoding="utf-8",
    )
    (frontend / "assets/css/runtime.css").write_text(
        '.claim::before { content: "The sa" "me law governs all systems."; }',
        encoding="utf-8",
    )
    errors = validate(inventory, root)
    assert any("assets/css/runtime.css" in error for error in errors)


def test_inline_script_dynamic_html_insertion_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script>document.body.insertAdjacentHTML("beforeend", '
        '"<p>The sa<em>me law</em> governs all systems.</p>");</script>',
        encoding="utf-8",
    )
    errors = validate(inventory, root)
    assert any("web/frontend/index.html" in error for error in errors)


def test_inline_script_static_string_concatenation_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script>document.body.textContent = "The sa" + "me law " + '
        '"governs all systems.";</script>',
        encoding="utf-8",
    )
    errors = validate(inventory, root)
    assert any("web/frontend/index.html" in error for error in errors)


def test_linked_javascript_static_string_concatenation_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/runtime.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/runtime.js").write_text(
        'document.body.innerText = "The sa" + "me law " + "governs all systems.";',
        encoding="utf-8",
    )
    errors = validate(inventory, root)
    assert any("assets/js/runtime.js" in error for error in errors)


def test_template_interpolation_render_claim_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script>const qualifier = "same"; '
        'document.body.textContent = `The ${qualifier} law governs all systems.`;</script>',
        encoding="utf-8",
    )
    errors = validate(inventory, root)
    assert any("web/frontend/index.html" in error for error in errors)


def test_internal_javascript_literals_and_console_output_are_not_public_copy(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/internal.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/internal.js").write_text(
        'const fixture = "verified universal law";\n'
        'const diagnostic = "The same law governs all systems.";\n'
        'console.log(fixture, diagnostic);',
        encoding="utf-8",
    )
    assert validate(inventory, root) == []


def test_css_import_url_and_escape_generated_content_fail_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/css/nested").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<link rel="stylesheet" href="/assets/css/root.css">', encoding="utf-8"
    )
    (frontend / "assets/css/root.css").write_text(
        "@import url(nested/claim.css);", encoding="utf-8"
    )
    (frontend / "assets/css/nested/claim.css").write_text(
        '.claim::before { content: "The \\73 ame law governs all systems."; }',
        encoding="utf-8",
    )
    errors = validate(inventory, root)
    assert any("assets/css/nested/claim.css" in error for error in errors)


def test_inline_data_css_is_scanned_but_not_treated_as_local_path(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<link rel="stylesheet" '
        'href="data:text/css,.claim%3A%3Abefore%7Bcontent%3A%22The%20same%20law%20governs%20all%20systems.%22%7D">',
        encoding="utf-8",
    )
    errors = validate(inventory, root)
    assert any("web/frontend/index.html" in error for error in errors)
    assert not any("missing local dependency" in error for error in errors)


def test_dom_append_and_public_attribute_sinks_are_scanned_selectively(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    frontend.mkdir(parents=True)
    cases = (
        'document.body.append("The same law governs all systems.");',
        'const node = document.createElement("div"); node.appendChild(document.createTextNode("The same law governs all systems."));',
        'const node = document.querySelector("#result"); node.setAttribute("aria-label", "The same law governs all systems.");',
        'const node = document.getElementById("result"); node.setAttribute("title", "The same law governs all systems.");',
    )
    for script in cases:
        (frontend / "index.html").write_text(f"<script>{script}</script>", encoding="utf-8")
        assert any("forbidden public claim regex" in error for error in validate(inventory, root)), script
    (frontend / "index.html").write_text(
        '<script>node.setAttribute("data-fixture", "The same law governs all systems.");</script>',
        encoding="utf-8",
    )
    assert validate(inventory, root) == []


def test_dom_like_names_without_dom_provenance_are_not_public_sinks(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text(
        "<script>"
        'error.title = "The same law governs all systems.";'
        'logger.append("The same law governs all systems.");'
        "</script>",
        encoding="utf-8",
    )
    assert validate(inventory, root) == []


def test_unloaded_asset_shaped_fixture_string_does_not_enter_dependency_closure(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/internal.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/internal.js").write_text(
        'const fixture = "fixtures/example.css"; console.log(fixture);',
        encoding="utf-8",
    )
    assert validate(inventory, root) == []


def test_script_and_link_loading_contexts_extend_dependency_closure(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "assets/css").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/loader.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/loader.js").write_text(
        'const script = document.createElement("script"); script.src = "/assets/js/copy.js";\n'
        'const link = document.createElement("link"); link.setAttribute("href", "/assets/css/copy.css");',
        encoding="utf-8",
    )
    (frontend / "assets/js/copy.js").write_text(
        'document.body.textContent = "The same law governs all systems.";', encoding="utf-8"
    )
    (frontend / "assets/css/copy.css").write_text(".safe { color: black; }", encoding="utf-8")
    errors = validate(inventory, root)
    assert any("assets/js/copy.js" in error for error in errors)


def test_asi_static_concatenation_reaching_dom_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text(
        "<script>\n"
        'const claim = "The sa" +\n'
        '  "me law governs all systems."\n'
        "document.body.textContent = claim\n"
        "</script>",
        encoding="utf-8",
    )
    errors = validate(inventory, root)
    assert any("web/frontend/index.html" in error for error in errors)


def test_repository_public_dependency_closure_covers_primary_runtime_scripts() -> None:
    paths = set(_paths(load_inventory(DEFAULT_INVENTORY), ROOT))
    assert {
        "web/frontend/assets/js/search.js",
        "web/frontend/assets/js/analyze.js",
        "web/frontend/assets/js/ask.js",
        "web/frontend/assets/js/report.js",
        "web/frontend/assets/js/i18n.js",
        "web/frontend/assets/data/i18n/content.json",
        "web/frontend/assets/data/i18n/ui.json",
    } <= paths


def test_normalizer_removes_default_ignorables_after_nfkc() -> None:
    from scripts.check_public_claims import _normalize_scan_text
    value = "ｓａ\u034fｍｅ\ufe0f\u00ad"
    assert _normalize_scan_text(value) == "same"
    assert unicodedata.normalize("NFKC", value) != "same"


def test_science_review_claim_variants_fail_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    attacks = (
        "This subclass was validated on NGSIM.",
        "The per-domain subclasses all stand.",
        "The result is corroborating the hypothesis.",
        "We ran controls to rule out methodological artifact.",
        "放射性衰变、药物浓度和 RLC 振荡都是它。",
        "这个结果印证了亚临界假说。",
    )
    for attack in attacks:
        (root / "page.html").write_text(f"{attack} Next: inspect evidence.")
        errors = validate(inventory, root)
        assert any("forbidden public claim regex" in error for error in errors), attack


def test_claim_caveat_must_be_adjacent(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    distant = "Candidate systems need testing. " + ("x" * 180) + " They share the same mechanism."
    (root / "page.html").write_text(distant + " Next: inspect evidence.")
    assert any("missing adjacent caveat" in error for error in validate(inventory, root))

    (root / "page.html").write_text(
        "This candidate comparison does not establish a shared mechanism. Next: inspect evidence."
    )
    assert validate(inventory, root) == []


def test_hidden_or_other_sentence_caveat_cannot_exempt_claim(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    attacks = (
        "<p>They share the same mechanism.<span hidden>This is only a candidate.</span></p>",
        "<p>This is only a candidate. They share the same mechanism.</p>",
        "<p>They share the same mechanism.</p><p>This is only a candidate.</p>",
        "<p>They share the same mechanism.<span style='display:none'>Not proof.</span></p>",
        "<p>They share the same mechanism.<span class='sr-only'>Candidate only.</span></p>",
    )
    for attack in attacks:
        (root / "page.html").write_text(attack + "<p>Next: inspect evidence.</p>")
        assert any("missing adjacent caveat" in error for error in validate(inventory, root)), attack

    data = json.loads(inventory.read_text())
    data["scope"]["runtime_pages"] = ["copy.json"]
    data["required_context"] = [{"path": "copy.json", "patterns": ["shared"]}]
    inventory.write_text(json.dumps(data))
    (root / "copy.json").write_text(json.dumps({
        "a": "They share a shared ", "b": "mechanism", "c": "Candidate only."
    }))
    assert any("cross-node public claim" in error for error in validate(inventory, root))


def test_caveat_must_bind_the_exact_claim_and_visible_attributes_are_scanned(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    (root / "page.html").write_text(
        "<p>A and B share the same mechanism; "
        "C and D do not establish a shared mechanism.</p>"
        "<p>Next: inspect evidence.</p>"
    )
    assert any("missing adjacent caveat" in error for error in validate(inventory, root))

    for attribute in ("aria-label", "title"):
        (root / "page.html").write_text(
            f'<button {attribute}="The same law governs all systems">Safe label</button>'
            "<p>Next: inspect evidence.</p>"
        )
        assert any("forbidden public claim regex" in error for error in validate(inventory, root))


def test_real_time_claim_needs_caveat_in_same_visible_sentence(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    (root / "page.html").write_text(
        "<p>Frozen research demo.</p><p>This is real-time phase detection.</p>"
        "<p>Next: inspect evidence.</p>"
    )
    assert any("missing adjacent caveat" in error for error in validate(inventory, root))
    (root / "page.html").write_text(
        "<p>This is not real-time phase detection; it is a frozen historical demo.</p>"
        "<p>Next: inspect evidence.</p>"
    )
    assert validate(inventory, root) == []


def test_current_i18n_copy_renders_cautious_claims_in_both_languages() -> None:
    content = json.loads((ROOT / "web/frontend/assets/data/i18n/content.json").read_text())
    expected = {
        "page.about.lede": {
            "zh": ("候选", "不等于"),
            "en": ("candidate", "does not establish"),
        },
        "page.about.empirical.phase3": {
            "zh": ("跨协议统计相似", "不能证明"),
            "en": ("cross-protocol statistical similarity", "do not prove"),
        },
        "page.home.usecases.card1.value": {
            "zh": ("历史结果记录", "内部研究稿"),
            "en": ("historical result records", "internal research drafts"),
        },
        "page.methods.pipeline_p2": {
            "zh": ("共享分析模块", "不能声称"),
            "en": ("shared analysis modules", "cannot claim"),
        },
        "page.about.how.v4.role": {
            "zh": ("候选组织器", "不能替", "待独立复现"),
            "en": ("candidate organizer", "cannot validate", "pending independent replication"),
        },
        "page.about.empirical.phase1": {
            "zh": ("历史分析记录", "不能据此确认机制"),
            "en": ("historical analysis", "does not confirm a mechanism"),
        },
        "page.about.empirical.phase2": {
            "zh": ("统计观察", "尚不足以确认"),
            "en": ("statistical observation", "does not establish"),
        },
        "page.about.empirical.phase4": {
            "zh": ("候选观察", "不是", "独立复现"),
            "en": ("candidate observation", "not an independent replication"),
        },
        "page.about.empirical.phase5": {
            "zh": ("有限对照", "不能排除", "待独立复现"),
            "en": ("bounded control", "cannot exclude", "pending independent replication"),
        },
        "page.home.usecases.card2.value": {
            "zh": ("候选", "不是唯一参数", "反例"),
            "en": ("candidate", "not the only parameter", "counterexamples"),
        },
        "page.home.usecases.card3.value": {
            "zh": ("候选", "不证明", "纵向数据"),
            "en": ("candidate", "does not establish", "longitudinal data"),
        },
        "page.search.v2_pairs_sub": {
            "zh": ("候选", "不是独立验证"),
            "en": ("candidates", "not independent validation"),
        },
        "page.phenomenon.same_structure_caption_emphasize": {
            "zh": ("候选骨架", "迁移前需核对"),
            "en": ("candidate skeleton", "transfer requires checks"),
        },
        "page.methods.b3_p3": {
            "zh": ("同厂商", "不是方法论"),
            "en": ("one vendor", "not validation of the methodology"),
        },
        "page.methods.null_p2": {
            "zh": ("探索性", "候选观察", "不能证明"),
            "en": ("exploratory", "candidate observation", "not proof"),
        },
        "page.taxv2.pattern_p3": {
            "zh": ("待检验", "不确认", "独立复现"),
            "en": ("pending tests", "does not confirm", "independent replication"),
        },
        "page.home.tagline": {
            "zh": ("可能", "值得检验"),
            "en": ("may", "worth testing"),
        },
        "page.home.lede": {
            "zh": ("可检验", "方法候选"),
            "en": ("testable", "candidate methods"),
        },
        "page.classes.footnote_l6": {
            "zh": ("合成对照记录", "有限对照", "不能排除"),
            "en": ("synthetic-control record", "bounded control", "cannot exclude"),
        },
        "page.about.next.item4": {
            "zh": ("研究演示", "不是实时检测"),
            "en": ("research demo", "not real-time detection"),
        },
        "page.about.how.v3.role": {
            "zh": ("候选方程骨架", "不是正确率", "领域专家复核"),
            "en": ("candidate equation skeleton", "neither correctness rates", "domain experts must verify"),
        },
        "page.about.how.parallel.p": {
            "zh": ("没有重复", "不足以证明", "不是独立性"),
            "en": ("no duplicate candidate IDs", "does not show", "not a claim of independence"),
        },
        "page.about.how.v4.intro": {
            "zh": ("候选结构组", "不能据此证明", "共同规律"),
            "en": ("candidate structural groups", "does not establish", "common law"),
        },
        "page.home.hero_evidence.caption_3": {
            "zh": ("候选映射", "并不相同"),
            "en": ("candidate SIR-like mapping", "assumptions differ"),
        },
        "page.home.hero_evidence.caption_4": {
            "zh": ("候选模型", "仍需数据检验"),
            "en": ("candidate cusp-catastrophe model", "data must test"),
        },
        "page.classes.meta_desc": {
            "zh": ("候选结构组", "证据缺口", "不是已确认"),
            "en": ("candidate structural groups", "evidence gaps", "not confirmed"),
        },
        "page.classes.footnote_l1": {
            "zh": ("内部评分标签", "不代表正确性", "证据质量"),
            "en": ("internal", "do not establish correctness", "evidence quality"),
        },
        "page.classes.footnote_l3": {
            "zh": ("候选分组", "分类标签", "不等于确认", "共享机制"),
            "en": ("candidate groups", "taxonomy label", "not confirmation", "shared mechanism"),
        },
        "page.classes.footnote_l4": {
            "zh": ("假设草拟", "变量映射", "失败标准"),
            "en": ("hypothesis drafting", "variable mapping", "failure criteria"),
        },
        "page.classes.footnote_l7": {
            "zh": ("同一厂商模型族", "不是独立同行评审", "不能验证分类方法"),
            "en": ("one vendor", "not independent peer review", "do not validate"),
        },
        "page.methods.l3_desc": {
            "zh": ("分类假设", "不等于确认", "共享机制"),
            "en": ("taxonomy hypotheses", "does not confirm", "shared mechanism"),
        },
        "page.methods.l1_desc": {
            "zh": ("内部评分标签", "不代表正确性", "证据质量"),
            "en": ("internal", "do not establish correctness", "evidence quality"),
        },
        "page.methods.l4_desc": {
            "zh": ("草拟", "替代解释", "失败标准"),
            "en": ("draft", "alternative explanations", "failure criteria"),
        },
    }
    for key, locales in expected.items():
        assert set(content[key]) == {"zh", "en"}
        for locale, fragments in locales.items():
            rendered = content[key][locale].casefold()
            assert all(fragment.casefold() in rendered for fragment in fragments)

    about = (ROOT / "web/frontend/about.html").read_text(encoding="utf-8")
    assert "13 份证据强度不一的结果记录" in about
    assert "不能替其他领域完成验证" not in about  # runtime fallback stays concise
    assert "看似无关的现象在数学结构层面往往是同一件事" not in about


def test_static_fallbacks_match_current_zh_i18n_claim_copy() -> None:
    content = json.loads((ROOT / "web/frontend/assets/data/i18n/content.json").read_text())
    classes = (ROOT / "web/frontend/classes.html").read_text(encoding="utf-8")
    methods = (ROOT / "web/frontend/methods.html").read_text(encoding="utf-8")
    for key in (
        "page.classes.hero_eyebrow",
        "page.classes.footnote_l1",
        "page.classes.footnote_l2",
        "page.classes.footnote_l3",
        "page.classes.footnote_l4",
        "page.classes.footnote_l5",
        "page.classes.footnote_l6",
        "page.classes.footnote_l7",
    ):
        assert content[key]["zh"] in classes, key
    for key in (
        "page.methods.l1_desc",
        "page.methods.l3_desc",
        "page.methods.l4_desc",
        "page.methods.b3_p1",
    ):
        assert content[key]["zh"] in methods, key


def test_missing_context_and_readability_contract_fail(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    data = json.loads(inventory.read_text())
    data["readability_contract"].pop("restatement_test")
    inventory.write_text(json.dumps(data))
    (root / "page.html").write_text("Plain summary.")
    errors = validate(inventory, root)
    assert any("missing required context" in error for error in errors)
    assert any("readability_contract" in error for error in errors)
