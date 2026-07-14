import json
import re
import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from scripts.check_public_claims import (
    DEFAULT_INVENTORY,
    ROOT,
    _js_dependency_strings,
    _paths,
    load_inventory,
    validate,
)


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
            r"(?:obey|obeys|follow|follows|run|runs)\s+(?:on\s+)?(?:the\s+)?same\s+(?:law|math(?:ematics)?)",
            r"(?:共用|遵循).{0,12}(?:同一|一)条规律",
            r"(?:规律.{0,24}(?:管着|支配)|跑的?是同一套数学|同一个数学结构)",
            r"share(?:s|d|ing)?\s+the\s+same\s+skeleton.{0,80}transfer",
            r"validated\s+on\s+NGSIM",
            r"subclasses.{0,80}all\s+stand",
            r"corroborating\s+the\s+hypothesis",
            r"to\s+rule\s+out.{0,80}artifact",
            r"都是它",
            r"印证.{0,40}假说",
            r"same\s+thing",
            r"structurally\s+equivalent\s+solutions",
            r"(?:精选发现|curated discoveries?).{0,180}(?:综合(?:得分|评分).{0,32}0\s*[-–]\s*10|composite.{0,32}scores?.{0,24}0\s*[-–]\s*10)",
            r"(?:精选发现|curated discoveries?).{0,220}(?:由\s*(?:Opus|独立\s*AI)|independently\s+assessed\s+by\s+Opus)",
            r"(?<!不是)(?<!并非)(?:三|3)\s*个独立(?:的)?(?:审稿|评审)(?:模型|者)",
            r"(?<!not\s)(?:three|3)\s+independent\s+(?:reviewer\s+models?|reviewers?|review\s+models?)",
            r"(?:correctly\s+rejected\s+(?:all\s+)?four|(?:全部|所有)?四个.{0,16}(?:均|都)?(?:被)?正确拒绝)",
            r"turns?\s+[\"“']?interesting[\"”']?\s+into\s+[\"“']?trustworthy",
            r"(?:就是|构成|证明).{0,16}(?:非平凡的?)?方法论验证|non[- ]trivial\s+(?:methodological|methodology)\s+validation",
            r"(?:各领域)?子类.{0,32}(?:仍然|依然|全部|都)(?:成立|有效).{0,48}真实物理机制|subclasses?.{0,48}(?:still|all)\s+(?:stand|hold).{0,48}real\s+physical\s+mechanism",
            r"(?:已经|早已)?成熟的?(?:工具|解法|方法)(?:已经|足以|可以)?(?:解决|解答|迁移)?",
            r"theoretically\s+(?:should|must)\s+(?:hold|work|exist)|理论上(?:应当|应该|该)成立",
            r"(?:结构上)?(?:几乎)?必然存在|大概率成立",
            r"大概率存在.{0,80}(?:目前|至今).{0,24}(?:没人|没有人).{0,16}(?:验证|研究)",
            r"(?:discoveries?|发现).{0,100}(?:some\s+(?:are\s+)?verified|部分(?:已经|已)?验证)",
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


def test_dynamic_render_helper_chain_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/runtime.js"></script>', encoding="utf-8"
    )
    attacks = {
        "arrow": (
            "const headline = (left, right) => `${left} and ${right} obey the same law.`;\n"
            "const card = (item) => `<p>${headline(item.a, item.b)}</p>`;\n"
            "const render = (items) => {\n"
            '  const host = document.getElementById("cards");\n'
            '  host.innerHTML = items.map(card).join("");\n'
            "};\n"
        ),
        "function expression": (
            "const headline = function(left, right) {\n"
            "  return `${left} and ${right} obey the same law.`;\n"
            "};\n"
            "const render = function(item) {\n"
            '  const host = document.getElementById("cards");\n'
            "  host.innerHTML = headline(item.a, item.b);\n"
            "};\n"
        ),
        "object method": (
            "const renderer = {\n"
            "  headline(left, right) { return `${left} and ${right} obey the same law.`; },\n"
            "  card(item) { return `<p>${this.headline(item.a, item.b)}</p>`; },\n"
            "  render(items) {\n"
            '    const host = document.getElementById("cards");\n'
            '    host.innerHTML = items.map((item) => this.card(item)).join("");\n'
            "  },\n"
            "};\n"
        ),
    }
    for dialect, script in attacks.items():
        (frontend / "assets/js/runtime.js").write_text(script, encoding="utf-8")
        errors = validate(inventory, root)
        assert any("forbidden public claim regex" in error for error in errors), dialect

    # A similarly named diagnostic helper that cannot reach a DOM writer is
    # not public copy; the gate remains selective rather than scanning all JS.
    (frontend / "assets/js/runtime.js").write_text(
        'function diagnosticHeadline() { return "The same law governs both."; }\n'
        "function render() {\n"
        '  const host = document.getElementById("cards");\n'
        '  host.textContent = "Candidate mapping; inspect evidence.";\n'
        "}\n",
        encoding="utf-8",
    )
    assert validate(inventory, root) == []


def test_computed_copy_map_reaching_dom_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/runtime.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/runtime.js").write_text(
        "const COPY = {'safe': 'The same law governs all systems.'};\n"
        "const key = 'safe';\n"
        'const node = document.getElementById("result");\n'
        'node.setAttribute("aria-label", COPY[key]);\n',
        encoding="utf-8",
    )
    errors = validate(inventory, root)
    assert any("forbidden public claim regex" in error for error in errors)


def test_callable_alias_reaching_dom_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/runtime.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/runtime.js").write_text(
        "function headline(value) { return `The same law governs ${value}.`; }\n"
        "function render(value) {\n"
        "  const firstAlias = headline;\n"
        "  const secondAlias = firstAlias;\n"
        '  const host = document.getElementById("result");\n'
        "  host.innerHTML = secondAlias(value);\n"
        "}\n",
        encoding="utf-8",
    )
    assert any(
        "forbidden public claim regex" in error for error in validate(inventory, root)
    )


def test_top_level_callable_alias_reaching_dom_fails_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/runtime.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/runtime.js").write_text(
        "function headline(value) { return `The same law governs ${value}.`; }\n"
        "const firstAlias = headline;\n"
        "const secondAlias = firstAlias;\n"
        'const host = document.getElementById("result");\n'
        'host.innerHTML = secondAlias("systems");\n',
        encoding="utf-8",
    )
    assert any(
        "forbidden public claim regex" in error for error in validate(inventory, root)
    )


def test_callback_argument_propagates_to_dom_sink(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/runtime.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/runtime.js").write_text(
        "function headline(value) { return `The same law governs ${value}.`; }\n"
        "function renderWith(callback, value) {\n"
        '  const host = document.getElementById("result");\n'
        "  host.innerHTML = callback(value);\n"
        "}\n"
        'renderWith(headline, "systems");\n',
        encoding="utf-8",
    )
    assert any(
        "forbidden public claim regex" in error for error in validate(inventory, root)
    )


def test_dom_argument_propagates_to_renderer_sink(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/runtime.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/runtime.js").write_text(
        "function headline(value) { return `The same law governs ${value}.`; }\n"
        "function render(host, value) { host.innerHTML = headline(value); }\n"
        'const host = document.getElementById("result");\n'
        'render(host, "systems");\n',
        encoding="utf-8",
    )
    assert any(
        "forbidden public claim regex" in error for error in validate(inventory, root)
    )


def test_plain_object_inner_html_is_not_a_dom_sink(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/runtime.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/runtime.js").write_text(
        'const record = {}; record.innerHTML = "The same law governs systems.";\n',
        encoding="utf-8",
    )
    assert validate(inventory, root) == []


def test_plain_object_argument_is_not_a_dom_sink(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/runtime.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/runtime.js").write_text(
        "function headline(value) { return `The same law governs ${value}.`; }\n"
        "function render(record, value) { record.innerHTML = headline(value); }\n"
        "const record = {};\n"
        'render(record, "systems");\n',
        encoding="utf-8",
    )
    assert validate(inventory, root) == []


def test_value_flow_dom_receiver_and_generated_css_redteam(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "assets/css").mkdir(parents=True)
    page = frontend / "index.html"
    runtime = frontend / "assets/js/runtime.js"
    page.write_text('<script src="/assets/js/runtime.js"></script>', encoding="utf-8")
    javascript_attacks = (
        'const h=x=>`The same law governs ${x}.`; const a=h; const output=a("systems"); '
        'const host=document.getElementById("x"); host.innerHTML=output;',
        'function h(x){return `The same law governs ${x}.`;} let host; '
        'host=document.getElementById("x"); host.innerHTML=h("systems");',
        'function h(x){return `The same law governs ${x}.`;} '
        'document.getElementById("x").innerHTML=h("systems");',
        'function h(x){return `The same law governs ${x}.`;} '
        'const host=document.getElementById("x"); host.replaceChildren(h("systems"));',
    )
    for attack in javascript_attacks:
        runtime.write_text(attack, encoding="utf-8")
        assert any("forbidden public claim" in error for error in validate(inventory, root)), attack

    runtime.write_text("", encoding="utf-8")
    css_cases = (
        (
            '<style>:root{--claim:"The same law governs systems."}'
            '.claim::before{content:var(--claim)}</style><div class="claim"></div>',
            "",
        ),
        (
            '<style>.claim::before{content:attr(data-claim)}</style>'
            '<div class="claim" data-claim="The same law governs systems."></div>',
            "",
        ),
        (
            '<link rel="stylesheet" href="/assets/css/runtime.css"><div class="claim"></div>',
            ':root{--claim:"The same law governs systems."}.claim::before{content:var(--claim)}',
        ),
    )
    for markup, stylesheet in css_cases:
        page.write_text(markup, encoding="utf-8")
        (frontend / "assets/css/runtime.css").write_text(stylesheet, encoding="utf-8")
        assert any("forbidden public claim" in error for error in validate(inventory, root)), markup

    page.write_text('<script src="/assets/js/runtime.js"></script>', encoding="utf-8")
    runtime.write_text(
        'function h(x){return `The same law governs ${x}.`;}'
        'const host=document.getElementById("public"); host.textContent="Candidate";'
        'function diagnostic(){const host={}; host.innerHTML=h("systems");}',
        encoding="utf-8",
    )
    assert validate(inventory, root) == []


def test_unrelated_qualified_callable_does_not_collide(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    frontend = root / "web/frontend"
    (frontend / "assets/js").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/assets/js/runtime.js"></script>', encoding="utf-8"
    )
    (frontend / "assets/js/runtime.js").write_text(
        "function headline(value) { return `The same law governs ${value}.`; }\n"
        "function render(value) {\n"
        '  const host = document.getElementById("result");\n'
        "  host.innerHTML = externalRenderer.headline(value);\n"
        "}\n",
        encoding="utf-8",
    )
    assert validate(inventory, root) == []


def test_classes_runtime_projects_historical_records_and_derives_counts() -> None:
    source = ROOT / "web/frontend/assets/js/classes.js"
    program = f"""
const fs = require('fs');
const vm = require('vm');
let lang = 'zh';
const window = {{
  i18n: {{ getLang: () => lang, t: (key) => key }},
  __setLang: (value) => {{ lang = value; }},
  addEventListener: () => {{}},
}};
const document = {{ readyState: 'loading', addEventListener: () => {{}}, querySelectorAll: () => [] }};
const context = {{ window, document, console, URLSearchParams }};
const source = fs.readFileSync({json.dumps(str(source))}, 'utf8');
vm.runInNewContext(source + `
  const fixtures = Array.from({{length: 26}}, (_, i) => ({{
    class_id: 'class-' + i,
    name: '候选类', name_en: 'Candidate class',
    domains: ['交通', '生态'], domains_en: ['Traffic', 'Ecology'], n_domains: i % 2 ? 4 : 13,
    size: i + 1,
    curation_source: i < 8 ? 'manual' : i < 23 ? 'llm' : null,
  }}));
  const rawRecord = {{
    target: '候选目标', target_en: 'Candidate target',
    test_method: '可检查方法', test_method_en: 'Checkable method',
    data_source: '记录数据源', data_source_en: 'Recorded dataset',
    sample_size: '84,808 events', sample_size_en: '84,808 events',
    prediction: '首次验证 criticality 确认：b = 1.084 ± 0.005',
    prediction_en: 'First validation confirms criticality: b = 1.084 ± 0.005',
    rationale: '这证明共享机制', rationale_en: 'This proves a shared mechanism',
    status: '✅ 已验证', status_en: 'CONFIRMED',
    paper_target: '目标期刊', paper_target_en: 'Target journal',
    paper_title: 'Strong paper title', paper_url: 'https://example.test/paper',
  }};
  globalThis.__result = {{
    zhHeadlines: fixtures.map(classHeadline),
    zhProjection: publicPredictionView(rawRecord),
    zhHtml: renderPredictions([rawRecord]),
    stats: deriveClassStats(fixtures),
  }};
  window.__setLang('en');
  globalThis.__result.enHeadlines = fixtures.map(classHeadline);
  globalThis.__result.enProjection = publicPredictionView(rawRecord);
  globalThis.__result.enHtml = renderPredictions([rawRecord]);
  window.location = {{ search: '' }};
  window.__classesData = {{ classes: fixtures }};
  allClasses = fixtures;
  manualClasses = fixtures.slice(0, 8);
  llmClasses = fixtures.slice(8, 23);
  unclassifiedClasses = fixtures.slice(23);
  currentFilter = 'manual';
  renderHeroStats = () => {{}};
  renderClassDatasetCopy = () => {{}};
  renderList = (list) => {{ globalThis.__result.rerenderListSize = list.length; }};
  _classesRerender();
  window.location.search = '?id=class-7';
  renderDetail = (item) => {{ globalThis.__result.rerenderDetailId = item.class_id; }};
  showView = () => {{}};
  _classesRerender();
`, context);
process.stdout.write(JSON.stringify(context.__result));
"""
    result = subprocess.run(
        ["node", "-e", program], check=True, capture_output=True, text=True
    )
    rendered = json.loads(result.stdout)
    strong = ("同一条规律", "同一套数学", "same law", "same math", "obey")
    assert all(
        not any(term.casefold() in headline.casefold() for term in strong)
        for headline in rendered["zhHeadlines"] + rendered["enHeadlines"]
    )
    assert all("候选" in value or "待检验" in value or "验证" in value for value in rendered["zhHeadlines"])
    assert all(
        "candidate" in value.casefold()
        or "test" in value.casefold()
        or "not an established law" in value.casefold()
        for value in rendered["enHeadlines"]
    )
    assert set(rendered["zhProjection"]) == {
        "target", "testMethod", "dataSource", "sampleSize", "historicalStatistics",
    }
    assert rendered["zhProjection"]["historicalStatistics"] == ["1.084 ± 0.005"]
    assert rendered["enProjection"]["historicalStatistics"] == ["1.084 ± 0.005"]
    forbidden = (
        "首次验证", "criticality 确认", "这证明共享机制", "目标期刊",
        "first validation", "confirms criticality", "this proves a shared mechanism",
        "target journal", "strong paper title", "confirmed",
    )
    for html_value in (rendered["zhHtml"], rendered["enHtml"]):
        assert not any(term.casefold() in html_value.casefold() for term in forbidden)
    assert rendered["stats"] == {
        "total": 26, "originalQueue": 23, "originalCrossDomain": 23,
        "laterCandidates": 3, "manual": 8, "llm": 15,
        "maxMembers": 26, "maxDomains": 13,
    }
    assert rendered["rerenderListSize"] == 8
    assert rendered["rerenderDetailId"] == "class-7"


def test_classes_real_runtime_json_is_in_claim_closure_and_raw_claims_do_not_render() -> None:
    data_path = ROOT / "web/frontend/assets/data/universality-classes.json"
    source_path = ROOT / "web/frontend/assets/js/classes.js"
    assert "web/frontend/assets/data/universality-classes.json" in set(
        _paths(load_inventory(DEFAULT_INVENTORY), ROOT)
    )
    program = f"""
const fs = require('fs');
const vm = require('vm');
let lang = 'zh';
const window = {{
  i18n: {{ getLang: () => lang, t: (key) => key }},
  addEventListener: () => {{}},
}};
const document = {{ readyState: 'loading', addEventListener: () => {{}} }};
const context = {{ window, document, console, URLSearchParams }};
const source = fs.readFileSync({json.dumps(str(source_path))}, 'utf8');
const data = JSON.parse(fs.readFileSync({json.dumps(str(data_path))}, 'utf8'));
vm.runInNewContext(source + `
  const data = ${{JSON.stringify(data)}};
  const fields = ['prediction', 'rationale', 'status', 'paper_target', 'paper_title'];
  function audit(locale) {{
    lang = locale;
    const html = data.classes.flatMap((item) => item.predictions || []).map((item) => renderPredictions([item])).join('');
    const leaked = [];
    for (const cls of data.classes) {{
      for (const item of cls.predictions || []) {{
        for (const field of fields) {{
          for (const key of [field, field + '_en']) {{
            const value = item[key];
            if (typeof value === 'string' && value.trim() && html.includes(value)) leaked.push([cls.class_id, key, value]);
          }}
        }}
      }}
    }}
    return {{ html, leaked }};
  }}
  globalThis.__result = {{ zh: audit('zh'), en: audit('en') }};
`, context);
process.stdout.write(JSON.stringify(context.__result));
"""
    completed = subprocess.run(
        ["node", "-e", program], check=True, capture_output=True, text=True
    )
    result = json.loads(completed.stdout)
    for locale in ("zh", "en"):
        assert result[locale]["leaked"] == []
        rendered = result[locale]["html"].casefold()
        for marker in (
            "首次验证", "criticality 确认", "目标期刊",
            "first validation", "confirms criticality", "target journal",
        ):
            assert marker.casefold() not in rendered
        assert "uc-pred__boundary" in rendered


def test_current_release_assets_share_one_cache_version() -> None:
    """Every asset changed by this release must invalidate as one unit.

    A prior batch rewrite left Classes loading three generations of JS/data,
    so a warm browser could combine incompatible contracts while clean E2E
    stayed green. Keep the release inventory explicit and verify every public
    reference, including JS-loaded JSON, instead of spot-checking one page.
    """
    frontend = ROOT / "web/frontend"
    release_version = "20260714n2"
    release_date = release_version[:8]
    assert re.fullmatch(r"\d{8}[A-Za-z0-9._-]+", release_version)
    release_assets = {
        "/assets/css/analyze-actions.css",
        "/assets/css/analyze.css",
        "/assets/css/ask.css",
        "/assets/css/classes.css",
        "/assets/css/common.css",
        "/assets/css/diagnose.css",
        "/assets/css/discoveries.css",
        "/assets/css/home.css",
        "/assets/css/newsletter.css",
        "/assets/css/paper.css",
        "/assets/css/papers.css",
        "/assets/css/phenomenon.css",
        "/assets/css/responsive.css",
        "/assets/css/search.css",
        "/assets/css/stress-test.css",
        "/assets/data/i18n/content.json",
        "/assets/data/i18n/ui.json",
        "/assets/data/papers-manifest.json",
        "/assets/js/analytics-consent.js",
        "/assets/js/analyze.js",
        "/assets/js/api.js",
        "/assets/js/apply.js",
        "/assets/js/ask.js",
        "/assets/js/classes.js",
        "/assets/js/connections.js",
        "/assets/js/diagnose.js",
        "/assets/js/discoveries.js",
        "/assets/js/evidence-envelope.js",
        "/assets/js/glossary.js",
        "/assets/js/history-sidebar.js",
        "/assets/js/home.js",
        "/assets/js/i18n.js",
        "/assets/js/insights.js",
        "/assets/js/lint.js",
        "/assets/js/markdown-safe.js",
        "/assets/js/my-reports.js",
        "/assets/js/newsletter.js",
        "/assets/js/paper.js",
        "/assets/js/papers-catalog.js",
        "/assets/js/papers.js",
        "/assets/js/phenomenon.js",
        "/assets/js/report.js",
        "/assets/js/search-bootstrap.js",
        "/assets/js/search.js",
        "/assets/js/secondary-tool-contracts.js",
        "/assets/js/share-card.js",
        "/assets/js/site-chrome.js",
        "/assets/js/stress-test.js",
        "/assets/js/utils.js",
        "/assets/js/utils/buildAnalyzeUrl.js",
        "/assets/js/utils/privateNavigation.js",
        "/assets/js/whitespace.js",
    }
    html_reference_re = re.compile(
        r"(?:href|src)\s*=\s*[\"']"
        r"(/assets/[A-Za-z0-9_./-]+(?:\?[^\"']*)?)[\"']"
    )
    references: dict[str, list[tuple[str, str]]] = {}
    unversioned: list[tuple[str, str]] = []
    current_release_versions: list[tuple[str, str, str]] = []
    sources = sorted(frontend.glob("*.html")) + sorted(
        (frontend / "assets/js").rglob("*.js")
    )
    for source in sources:
        text = source.read_text(encoding="utf-8")
        specifiers = (
            html_reference_re.findall(text)
            if source.suffix == ".html"
            else _js_dependency_strings(text)
        )
        for specifier in specifiers:
            parsed = urlsplit(specifier)
            asset = parsed.path
            versions = parse_qs(parsed.query, keep_blank_values=True).get("v", [])
            if len(versions) != 1 or not versions[0]:
                if asset in release_assets:
                    unversioned.append((str(source.relative_to(ROOT)), asset))
                continue
            version = versions[0]
            references.setdefault(asset, []).append(
                (str(source.relative_to(ROOT)), version)
            )
            if version.startswith(release_date):
                current_release_versions.append(
                    (str(source.relative_to(ROOT)), asset, version)
                )

    missing = sorted(asset for asset in release_assets if asset not in references)
    stale = sorted(
        (source, asset, version)
        for asset in release_assets
        for source, version in references.get(asset, [])
        if version != release_version
    )
    split_release = sorted(
        item for item in current_release_versions if item[2] != release_version
    )
    assert missing == [], f"release assets lack a public versioned reference: {missing}"
    assert unversioned == [], (
        f"release assets have unversioned public references: {sorted(unversioned)}"
    )
    assert stale == [], f"changed assets still use stale cache keys: {stale}"
    assert split_release == [], (
        f"current release cache keys are split across versions: {split_release}"
    )

    manifest = json.loads(
        (frontend / "assets/data/papers-manifest.json").read_text(encoding="utf-8")
    )
    catalog = (frontend / "assets/js/papers-catalog.js").read_text(encoding="utf-8")
    assert manifest["meta"]["asset_version"] == release_version
    assert f"const ASSET_VERSION = '{release_version}';" in catalog


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
        "Traffic and ecology obey the same law.",
        "交通与生态遵循同一条规律。",
        "交通与生态跑的是同一套数学。",
        "放射性衰变、药物浓度和 RLC 振荡都是它。",
        "这个结果印证了亚临界假说。",
        "Three independent reviewer models reached a majority verdict.",
        "三个独立审稿模型多数决定共识。",
        "The pipeline correctly rejected all four controls.",
        "This check turns interesting into trustworthy.",
        "三个模型收敛本身就是非平凡的方法论验证。",
        "各领域子类仍然成立，每个都对应真实物理机制。",
        "这是已经成熟的工具，可以直接解决问题。",
        "这个跨领域关系理论上应该成立。",
        "该结构在目标领域几乎必然存在。",
        "这个模式大概率存在，但目前还没人验证。",
        "The discoveries include some verified matches.",
    )
    for attack in attacks:
        (root / "page.html").write_text(f"{attack} Next: inspect evidence.")
        errors = validate(inventory, root)
        assert any("forbidden public claim regex" in error for error in errors), attack


def test_discovery_uncalibrated_scoring_claims_fail_closed(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    attacks = (
        "精选发现使用深度分析后的综合得分 0-10，由 Opus 独立评估。",
        "Curated Discoveries use composite post-analysis scores (0–10), independently assessed by Opus.",
    )
    for attack in attacks:
        (root / "page.html").write_text(f"{attack} Next: inspect evidence.", encoding="utf-8")
        assert any(
            "forbidden public claim regex" in error for error in validate(inventory, root)
        ), attack


def test_claim_caveat_must_be_adjacent(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    distant = "Candidate systems need testing. " + ("x" * 180) + " They share the same mechanism."
    (root / "page.html").write_text(distant + " Next: inspect evidence.")
    assert any("missing adjacent caveat" in error for error in validate(inventory, root))

    (root / "page.html").write_text(
        "This candidate comparison does not establish a shared mechanism. Next: inspect evidence."
    )
    assert validate(inventory, root) == []

    (root / "page.html").write_text(
        "我们不会把用户反馈写成机制验证。Next: inspect evidence."
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
                "zh": ("候选结构分组", "历史分析字段", "当前加载记录"),
                "en": ("candidate structural groups", "historical analysis fields", "loaded records"),
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
                "zh": ("原队列候选", "不是独立同行评审", "不能验证分类方法"),
                "en": ("original-queue candidates", "not independent peer review", "do not validate"),
            },
            "page.about.scoring.note": {
                "zh": ("不公开未校准", "不把模型意见当作独立评审", "证据缺口", "下一步核查"),
                "en": ("does not publish uncalibrated", "model opinions as independent review", "evidence gaps", "next review step"),
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
    about = (ROOT / "web/frontend/about.html").read_text(encoding="utf-8")
    taxonomy = (ROOT / "web/frontend/taxonomy-v2.html").read_text(encoding="utf-8")
    start_here = (ROOT / "web/frontend/start-here.html").read_text(encoding="utf-8")
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
    assert content["page.about.scoring.note"]["zh"] in about
    for key in (
        "page.methods.l1_desc",
        "page.methods.l3_desc",
        "page.methods.l4_desc",
        "page.methods.b3_p1",
    ):
        assert content[key]["zh"] in methods, key
    for key in (
        "page.taxv2.meta_title",
        "page.taxv2.meta_desc",
        "page.taxv2.lede",
        "page.taxv2.limit_p1",
        "page.taxv2.limit_p2",
        "page.taxv2.limit_p3",
        "page.taxv2.pattern_p1",
        "page.taxv2.pattern_p2",
        "page.taxv2.pattern_p3",
    ):
        assert content[key]["zh"] in taxonomy, key
    for forbidden in (
        "three independent reviewers",
        "no parameter tuning",
        "correctly rejected all four",
        "turns &ldquo;interesting&rdquo; into &ldquo;trustworthy&rdquo;",
        "some verified",
    ):
        assert forbidden not in start_here.casefold()
    assert "three same-vendor configurations" in start_here
    assert "not a list of verified matches" in start_here


def test_runtime_glossary_whitespace_and_search_copy_stays_bounded() -> None:
    glossary = (ROOT / "web/frontend/assets/js/glossary.js").read_text(encoding="utf-8")
    whitespace = (ROOT / "web/frontend/assets/js/whitespace.js").read_text(encoding="utf-8")
    search = (ROOT / "web/frontend/assets/js/search.js").read_text(encoding="utf-8")
    connections = (ROOT / "web/frontend/assets/js/connections.js").read_text(encoding="utf-8")
    for forbidden in (
        "其实是同一回事",
        "共用同一套方程",
        "大事件和小事件遵循同一套规律",
        "都属于相变现象",
    ):
        assert forbidden not in glossary
    for forbidden in (
        "大概率存在",
        "目前还没有人去验证",
        "结构上几乎必然存在",
        "大概率成立",
        "return esc(lead.rationale)",
        "return String(lead.research_question)",
    ):
        assert forbidden not in whitespace
    assert "结构相同的案例" not in search
    assert "同一普适类'" not in connections
    assert "内部候选分类标签相同（非机制证明）" in connections


def test_missing_context_and_readability_contract_fail(tmp_path: Path) -> None:
    root, inventory = _fixture(tmp_path)
    data = json.loads(inventory.read_text())
    data["readability_contract"].pop("restatement_test")
    inventory.write_text(json.dumps(data))
    (root / "page.html").write_text("Plain summary.")
    errors = validate(inventory, root)
    assert any("missing required context" in error for error in errors)
    assert any("readability_contract" in error for error in errors)
